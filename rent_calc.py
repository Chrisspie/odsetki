# rent_interest_web_app.py
"""
Aplikacja webowa Streamlit do zarządzania zaległościami czynszowymi i
obliczania odsetek ustawowych za opóźnienie.

Uruchom:
    streamlit run rent_interest_web_app.py

Plik CSV do importu faktur (separator średnik):
    data_płatności;kwota
    2024-01-10;1450.00
    2024-02-10;1450.00
"""
from __future__ import annotations

import streamlit as st
import pandas as pd
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List

# ------------------------------ Dane ---------------------------------------
@dataclass
class Payment:
    date: datetime
    amount: float

@dataclass
class Invoice:
    id: int
    due_date: datetime
    amount: float
    payments: List[Payment] = field(default_factory=list)

# Zweryfikowane stawki (NBP ref + 5,5 p.p.)
INTEREST_RATES = [
    (datetime(2016,1,1),  datetime(2020,3,17), 7.00),
    (datetime(2020,3,18), datetime(2020,4,8),  6.50),
    (datetime(2020,4,9),  datetime(2020,5,28), 6.00),
    (datetime(2020,5,29), datetime(2021,10,6), 5.60),
    (datetime(2021,10,7), datetime(2021,11,3), 6.00),
    (datetime(2021,11,4), datetime(2021,12,7), 6.75),
    (datetime(2021,12,8), datetime(2022,1,4),  7.25),
    (datetime(2022,1,5),  datetime(2022,2,8),  7.75),
    (datetime(2022,2,9),  datetime(2022,3,8),  8.25),
    (datetime(2022,3,9),  datetime(2022,4,5),  9.00),
    (datetime(2022,4,6),  datetime(2022,5,5),  10.00),
    (datetime(2022,5,6),  datetime(2022,6,8),  10.75),
    (datetime(2022,6,9),  datetime(2022,7,6),  11.50),
    (datetime(2022,7,7),  datetime(2022,9,7),  12.00),
    (datetime(2022,9,8),  datetime(2023,9,6),  12.25),
    (datetime(2023,9,7),  datetime(2023,10,3), 11.50),
    (datetime(2023,10,4), datetime(2024,6,5),  11.25),
    (datetime(2024,6,6),  datetime(2100,1,1), 10.75),
]

# --------------------------- Funkcje ---------------------------------------

def detailed_interest_with_payments(
    amount: float,
    due_date: datetime,
    payments: list[Payment],
    stop: datetime,
) -> pd.DataFrame:
    """
    • odsetki liczone OD dnia wymagalności WŁĄCZNIE  
    • do dnia zapłaty WŁĄCZNIE  
    • po wpłacie kapitał pomniejsza się od dnia następnego
    """
    # 1.  sortujemy wpłaty + dokładamy „wirtualny” stop
    payments_sorted = sorted(payments, key=lambda p: p.date)
    payments_sorted.append(Payment(date=stop, amount=0.0))  # zamyka ostatni segment

    rows: list[dict] = []
    principal = amount
    seg_start = due_date                       # obowiązuje już pierwszy dzień
    rate_idx = 0                               # wskaźnik na INTEREST_RATES

    for pay in payments_sorted:                # kolejno po wpłatach
        seg_stop = pay.date                    # wpłata liczona w dniu wpłaty

        # przechodzimy po przedziałach stawek, które nakładają się na (seg_start‑seg_stop)
        while rate_idx < len(INTEREST_RATES) and INTEREST_RATES[rate_idx][1] < seg_start:
            rate_idx += 1
        j = rate_idx
        while j < len(INTEREST_RATES) and INTEREST_RATES[j][0] <= seg_stop:
            r_start, r_end, rate = INTEREST_RATES[j]
            period_from = max(seg_start, r_start)
            period_to   = min(seg_stop, r_end)
            if period_from <= period_to and principal > 0:
                days = (period_to - period_from).days + 1       # obie granice włącznie
                intr = round(principal * rate / 100 * days / 365, 2)
                rows.append({
                    "Okres od": period_from.date(),
                    "Okres do": period_to.date(),
                    "Stawka %": rate,
                    "Dni": days,
                    "Kwota": principal,
                    "Odsetki": intr,
                })
            j += 1

        # pomniejszamy kapitał od dnia PO wpłacie
        principal = max(principal - pay.amount, 0)
        seg_start = pay.date + timedelta(days=1)
        if seg_start > stop:
            break

    return pd.DataFrame(rows)



def calculate_total_interest(invoice: Invoice) -> float:
    if invoice.amount == 0:
        return 0.0
    df = detailed_interest_with_payments(
        invoice.amount,
        invoice.due_date,
        sorted(invoice.payments, key=lambda p: p.date),
        datetime.today()
    )
    return df["Odsetki"].sum() if not df.empty else 0.0

# --------------------------- Stan aplikacji --------------------------------
if "invoices" not in st.session_state:
    st.session_state.invoices: List[Invoice] = []
    st.session_state.next_id = 1

# --------------------------- UI --------------------------------------------
st.title("💸 Kalkulator odsetek czynszowych")

# ---------- Sidebar --------------------------------------------------------
st.sidebar.header("➕ Dodaj pojedynczą fakturę")
with st.sidebar.form("add_inv"):
    inv_date = st.date_input("Termin płatności", value=datetime.today())
    inv_amount_str = st.text_input("Kwota (zł)", value="", key="add_inv_amt")
    inv_amount = None
    inv_amt_error = False
    if inv_amount_str:
        try:
            inv_amount = float(inv_amount_str.replace(",", "."))
        except ValueError:
            inv_amt_error = True
    if st.form_submit_button("Zapisz"):
        if inv_amt_error or inv_amount is None or inv_amount <= 0:
            st.error("Podaj poprawną kwotę (liczba większa od zera, np. 105,44 lub 105.44)")
        else:
            st.session_state.invoices.append(
                Invoice(id=st.session_state.next_id,
                        due_date=datetime.combine(inv_date, datetime.min.time()),
                        amount=inv_amount)
            )
            st.session_state.next_id += 1
            st.success("Faktura dodana")
            st.rerun()

st.sidebar.markdown("---")

# --- ZAPIS/WCZYTANIE STANU FAKTUR I WPŁAT ---
st.sidebar.header("💾 Zapis/Wczytanie stanu (CSV)")
import io

def export_invoices_payments():
    rows = []
    for inv in st.session_state.invoices:
        rows.append({
            "typ": "faktura",
            "id_faktury": inv.id,
            "termin": inv.due_date.strftime("%Y-%m-%d"),
            "kwota_faktury": inv.amount,
            "data_wplaty": "",
            "kwota_wplaty": ""
        })
        for pay in inv.payments:
            rows.append({
                "typ": "wplata",
                "id_faktury": inv.id,
                "termin": "",
                "kwota_faktury": "",
                "data_wplaty": pay.date.strftime("%Y-%m-%d"),
                "kwota_wplaty": pay.amount
            })
    df = pd.DataFrame(rows)
    return df.to_csv(index=False, sep=";", encoding="utf-8")

csv_data = export_invoices_payments()
col_save, col_load = st.sidebar.columns([1,1])
with col_save:
    st.download_button(
        "⬇️ Zapisz stan (CSV)",
        data=csv_data.encode("utf-8"),
        file_name="faktury_wplaty.csv",
        mime="text/csv",
    )
with col_load:
    load_file = st.file_uploader("Wczytaj CSV", type=["csv"], key="load_state")
    if 'csv_loaded' not in st.session_state:
        st.session_state['csv_loaded'] = False
    if load_file is not None and not st.session_state['csv_loaded']:
        try:
            df = pd.read_csv(load_file, sep=";")
            invoices = {}
            payments = []
            for idx, row in df.iterrows():
                typ = str(row.get("typ", "")).strip().lower()
                id_fakt = int(row.get("id_faktury", 0))
                if typ == "faktura":
                    termin = str(row.get("termin", "")).strip()
                    amt = float(str(row.get("kwota_faktury", "0")).replace(",", "."))
                    inv = Invoice(id=id_fakt, due_date=datetime.strptime(termin, "%Y-%m-%d"), amount=amt)
                    invoices[id_fakt] = inv
                elif typ == "wplata":
                    data_wpl = str(row.get("data_wplaty", "")).strip()
                    kwota_wpl = float(str(row.get("kwota_wplaty", "0")).replace(",", "."))
                    payments.append((id_fakt, Payment(date=datetime.strptime(data_wpl, "%Y-%m-%d"), amount=kwota_wpl)))
            # Assign payments to invoices
            for id_fakt, pay in payments:
                if id_fakt in invoices:
                    invoices[id_fakt].payments.append(pay)
            # Replace session state
            st.session_state.invoices = list(invoices.values())
            st.session_state.next_id = max(invoices.keys(), default=0) + 1
            st.session_state['csv_loaded'] = True
            st.success("Stan wczytany!")
            st.rerun()
        except Exception as e:
            st.error(f"Błąd wczytywania stanu: {e}")
    if st.session_state['csv_loaded']:
        if st.button("Wczytaj inny plik CSV"):
            st.session_state['csv_loaded'] = False
            st.experimental_rerun()

st.sidebar.markdown("---")

st.sidebar.header("📥 Import faktur z CSV")
st.sidebar.info("Oczekiwany format: YYYY-MM-DD;kwota\nNp.: 2017-09-10;1041.98")
uploaded = st.sidebar.file_uploader("Wybierz plik CSV (data;kwota)", type=["csv"])
if uploaded is not None:
    try:
        df_csv = pd.read_csv(uploaded, sep=";", header=None, names=["date","amount"])
        preview = []
        added = 0
        for idx, row in df_csv.iterrows():
            date_str = str(row["date"]).strip()
            amt_str = str(row["amount"]).replace(",", ".").strip()
            try:
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                amt = float(amt_str)
                preview.append({"Data": dt.date(), "Kwota": amt})
            except Exception:
                st.warning(f"Nieprawidłowy wiersz (linia {idx+1}): {row.to_list()}")
        if preview:
            st.sidebar.write("Podgląd importu:")
            st.sidebar.dataframe(pd.DataFrame(preview))
            if st.sidebar.button("Importuj powyższe faktury"):
                for row in preview:
                    st.session_state.invoices.append(
                        Invoice(id=st.session_state.next_id,
                                due_date=datetime.combine(row["Data"], datetime.min.time()),
                                amount=row["Kwota"])
                    )
                    st.session_state.next_id += 1
                    added += 1
                st.sidebar.success(f"Zaimportowano {added} faktur.")
                st.rerun()
        else:
            st.sidebar.warning("Brak poprawnych danych do importu.")
    except Exception as e:
        st.sidebar.error(f"Błąd wczytywania CSV: {e}")

# ---------- Lista faktur ---------------------------------------------------
inv_df = pd.DataFrame([
    {
        "ID": i.id,
        "Termin": i.due_date.date(),
        "Kwota": i.amount,
        "Wpłaty": sum(p.amount for p in i.payments),
        "Odsetki": calculate_total_interest(i)
    }
    for i in st.session_state.invoices
])

st.subheader("📑 Faktury")
st.dataframe(inv_df, use_container_width=True)

if inv_df.empty:
    st.stop()

selected_id = st.selectbox("Wybierz fakturę (ID)", inv_df["ID"], index=0)
inv = next(i for i in st.session_state.invoices if i.id == selected_id)

# ---------- Edycja i kasowanie faktur --------------------------------------
st.sidebar.markdown("---")
st.sidebar.header(f"📝 Edytuj/Kasuj fakturę {inv.id}")

with st.sidebar.form(f"edit_inv_{inv.id}"):
    new_due_date = st.date_input("Nowy termin płatności", value=inv.due_date.date(), key=f"edit_due_{inv.id}")
    new_amount_str = st.text_input("Nowa kwota (zł)", value=str(inv.amount).replace(".", ","), key=f"edit_amt_{inv.id}")
    new_amount = None
    new_amt_error = False
    if new_amount_str:
        try:
            new_amount = float(new_amount_str.replace(",", "."))
        except ValueError:
            new_amt_error = True
    if st.form_submit_button("Zapisz zmiany"):
        if new_amt_error or new_amount is None or new_amount <= 0:
            st.error("Podaj poprawną kwotę (liczba większa od zera, np. 105,44 lub 105.44)")
        else:
            inv.due_date = datetime.combine(new_due_date, datetime.min.time())
            inv.amount = new_amount
            st.success("Zmieniono dane faktury.")
            st.rerun()
    if st.form_submit_button("Usuń fakturę"):
        st.session_state.invoices = [i for i in st.session_state.invoices if i.id != inv.id]
        st.success("Faktura usunięta.")
        st.rerun()

# ---------- Płatności ------------------------------------------------------
st.markdown(f"### 💰 Płatności — faktura **{inv.id}** (termin {inv.due_date.date()})")

# Edycja i kasowanie pojedynczych wpłat
if inv.payments:
    for idx, p in enumerate(inv.payments):
        col1, col2, col3 = st.columns([2,2,1])
        with col1:
            st.write(p.date.date())
        with col2:
            st.write(p.amount)
        with col3:
            if st.button("Edytuj", key=f"edit_pay_{inv.id}_{idx}"):
                st.session_state[f"edit_pay_idx_{inv.id}"] = idx
            if st.button("Usuń", key=f"del_pay_{inv.id}_{idx}"):
                inv.payments.pop(idx)
                st.rerun()
        # Edycja wpłaty
        if st.session_state.get(f"edit_pay_idx_{inv.id}") == idx:
            with st.container():
                st.markdown("""
                <div style='background-color: #f3f6fa; border-radius: 8px; padding: 1em; border: 1px solid #dbe4ee; margin-bottom: 1em;'>
                <b>✏️ Edycja wpłaty</b>
                """, unsafe_allow_html=True)
                with st.form(f"form_edit_pay_{inv.id}_{idx}"):
                    new_p_date = st.date_input("Data wpłaty", value=p.date.date(), key=f"edit_pd_{inv.id}_{idx}")
                    new_p_amt_str = st.text_input("Kwota wpłaty (zł)", value=str(p.amount).replace(".", ","), key=f"edit_pa_{inv.id}_{idx}")
                    new_p_amt = None
                    new_p_amt_error = False
                    if new_p_amt_str:
                        try:
                            new_p_amt = float(new_p_amt_str.replace(",", "."))
                        except ValueError:
                            new_p_amt_error = True
                    if st.form_submit_button("Zapisz zmiany"):
                        if new_p_amt_error or new_p_amt is None or new_p_amt <= 0:
                            st.error("Podaj poprawną kwotę (liczba większa od zera, np. 105,44 lub 105.44)")
                        else:
                            inv.payments[idx] = Payment(date=datetime.combine(new_p_date, datetime.min.time()), amount=new_p_amt)
                            st.session_state.pop(f"edit_pay_idx_{inv.id}")
                            st.rerun()
                    if st.form_submit_button("Anuluj"):
                        st.session_state.pop(f"edit_pay_idx_{inv.id}")
                st.markdown("</div>", unsafe_allow_html=True)
else:
    st.info("Brak wpłat.")

with st.form(f"pay_form_{inv.id}"):
    pay_date = st.date_input("Data wpłaty", value=datetime.today(), key=f"pd_{inv.id}")
    pay_amt_str = st.text_input("Kwota wpłaty (zł)", value="", key=f"pa_{inv.id}")
    pay_amt = None
    pay_amt_error = False
    if pay_amt_str:
        try:
            pay_amt = float(pay_amt_str.replace(",", "."))
        except ValueError:
            pay_amt_error = True
    if st.form_submit_button("Dodaj wpłatę"):
        if pay_amt_error or pay_amt is None or pay_amt <= 0:
            st.error("Podaj poprawną kwotę (liczba większa od zera, np. 105,44 lub 105.44)")
        else:
            inv.payments.append(Payment(date=datetime.combine(pay_date, datetime.min.time()), amount=pay_amt))
            st.rerun()

# ---------- Szczegółowe odsetki -------------------------------------------
st.markdown("### 🧮 Szczegółowe naliczenie")

calc_df = detailed_interest_with_payments(
    inv.amount,
    inv.due_date,
    sorted(inv.payments, key=lambda p: p.date),
    datetime.today()
)

st.dataframe(calc_df, use_container_width=True)

# opcjonalny eksport CSV
st.download_button(
    "⬇️ Pobierz szczegóły (CSV)",
    data=calc_df.to_csv(index=False, sep=";").encode("utf-8"),
    file_name=f"odsetki_faktura_{inv.id}.csv",
    mime="text/csv",
)