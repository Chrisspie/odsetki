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
st.set_page_config(layout="wide")
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
DEFAULT_INTEREST_RATES = [
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

if 'interest_rates' not in st.session_state:
    st.session_state['interest_rates'] = [
        (d1.strftime('%Y-%m-%d'), d2.strftime('%Y-%m-%d'), rate)
        for d1, d2, rate in DEFAULT_INTEREST_RATES
    ]

def parse_date(date_str):
    return datetime.strptime(date_str, '%Y-%m-%d')

def parse_date_flexible(date_str):
    date_str = str(date_str).strip()
    for fmt in ('%Y-%m-%d', '%d.%m.%Y'):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    raise ValueError(f"Nieprawidłowy format daty: {date_str}. Dozwolone: YYYY-MM-DD lub DD.MM.YYYY")

with st.expander('⚙️ Stopy procentowe (edytuj)', expanded=False):
    st.markdown('''Możesz edytować, usuwać lub dodać nowe stopy procentowe.\nZmiany wpływają na wszystkie obliczenia odsetek.''')
    st.markdown("**Od (YYYY-MM-DD) | Do (YYYY-MM-DD) | %**")
    rates = st.session_state['interest_rates']
    remove_idx = None
    edit_idx = None

    # Edycja istniejących
    for idx, (start, stop, rate) in enumerate(rates):
        cols = st.columns([2,2,1,1,1])
        with cols[0]:
            new_start = st.text_input("", value=start, key=f"start_{idx}", label_visibility="collapsed")
        with cols[1]:
            new_stop = st.text_input("", value=stop, key=f"stop_{idx}", label_visibility="collapsed")
        with cols[2]:
            new_rate = st.text_input("", value=str(rate), key=f"rate_{idx}", label_visibility="collapsed")
        with cols[3]:
            if st.button("Zapisz", key=f"save_{idx}"):
                try:
                    # walidacja daty i stopy
                    parse_date(new_start)
                    parse_date(new_stop)
                    float(new_rate)
                    rates[idx] = (new_start, new_stop, float(new_rate))
                    st.success(f"Zmieniono stopę {idx+1}")
                except Exception as e:
                    st.error(f"Błąd: {e}")
        with cols[4]:
            if st.button("Usuń", key=f"del_{idx}"):
                remove_idx = idx
    if remove_idx is not None:
        rates.pop(remove_idx)
        st.experimental_rerun()

    st.markdown("---")
    st.markdown("**Dodaj nową stopę**")
    with st.form("add_rate"):
        col1, col2, col3 = st.columns([2,2,1])
        new_start = col1.text_input("", value="", key="new_start", label_visibility="collapsed")
        new_stop = col2.text_input("", value="", key="new_stop", label_visibility="collapsed")
        new_rate = col3.text_input("", value="", key="new_rate", label_visibility="collapsed")
        submitted = st.form_submit_button("Dodaj")
        if submitted:
            try:
                parse_date(new_start)
                parse_date(new_stop)
                rate_val = float(new_rate)
                rates.append((new_start, new_stop, rate_val))
                st.success("Dodano nową stopę")
                st.experimental_rerun()
            except Exception as e:
                st.error(f"Błąd: {e}")

# Funkcja do pobierania stawek w formacie do obliczeń

def get_interest_rates():
    rates = [
        (parse_date(start), parse_date(stop), float(rate) / 100 if float(rate) > 20 else float(rate))
        for start, stop, rate in st.session_state['interest_rates']
    ]
    validate_interest_rate_ranges(rates)
    return sorted(rates, key=lambda r: r[0])

# --------------------------- Funkcje ---------------------------------------
def validate_interest_rate_ranges(rates: list[tuple[datetime, datetime, float]]):
    """Rzuca ValueError przy:
    • nachodzących się przedziałach,
    • lukach > 1 dzień między sąsiednimi przedziałami,
    • odwróconych datach w pojedynczym przedziale.
    """
    rates_sorted = sorted(rates, key=lambda r: r[0])
    for i, (start, stop, _) in enumerate(rates_sorted):
        if start > stop:
            raise ValueError(
                f"Przedział {i+1}: data 'od' ({start.date()}) jest późniejsza niż 'do' ({stop.date()})")

        if i > 0:
            prev_start, prev_stop, _ = rates_sorted[i - 1]
            # nachodzenie się
            if start <= prev_stop:
                raise ValueError(
                    f"Przedziały {i} i {i+1} nachodzą się: {prev_stop.date()} / {start.date()}")
            # luka
            if (start - prev_stop).days > 1:
                raise ValueError(
                    f"Luka między przedziałami {i} i {i+1}: {prev_stop.date()} → {start.date()}")
                    
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
    seg_start = due_date
    interest_rates = get_interest_rates()
    for pay in payments_sorted:
        seg_end = min(pay.date, stop)
        if seg_start > seg_end:
            seg_start = seg_end
        # 2. rozbijamy segment na okresy stawek procentowych
        rate_idx = 0
        while rate_idx < len(interest_rates) and interest_rates[rate_idx][1] < seg_start:
            rate_idx += 1
        period_from = seg_start
        j = rate_idx
        while j < len(interest_rates):
            rate_start, rate_end, rate = interest_rates[j]
            if rate_start > seg_end:
                break
            period_from = max(rate_start, seg_start)    
            period_to = min(rate_end, seg_end)
            days = (period_to - period_from).days + 1
            if days > 0:
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
                    if not termin or termin.lower() == 'nan':
                        raise ValueError(f"Brak daty w kolumnie 'termin' w wierszu {idx+2} (typ: faktura)")
                    inv = Invoice(id=id_fakt, due_date=parse_date_flexible(termin), amount=amt)
                    invoices[id_fakt] = inv

                elif typ == "wplata":
                    data_wpl = str(row.get("termin", "")).strip()
                    kwota_wpl = float(str(row.get("kwota_faktury", "0")).replace(",", "."))
                    if not data_wpl or data_wpl.lower() == 'nan':
                        raise ValueError(f"Brak daty w kolumnie 'termin' w wierszu {idx+2} (typ: wplata)")
                    payments.append((id_fakt, Payment(date=parse_date_flexible(data_wpl), amount=kwota_wpl)))

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

# --- PODSUMOWANIE ---
total_interest = inv_df["Odsetki"].sum() if not inv_df.empty else 0.0
total_due = (inv_df["Kwota"].sum() - inv_df["Wpłaty"].sum()) if not inv_df.empty else 0.0

st.markdown(f"""
<div style='display:flex;gap:2em;margin-bottom:1em;'>
  <div style='background:#f8f8e7;padding:1em 2em;border-radius:10px;border:1.5px solid #ffd700;'>
    <b>💰 Suma odsetek:</b><br><span style='font-size:1.3em;color:#b58900'>{total_interest:,.2f} zł</span>
  </div>
  <div style='background:#e7f8e7;padding:1em 2em;border-radius:10px;border:1.5px solid #4caf50;'>
    <b>🧾 Pozostało do zapłaty:</b><br><span style='font-size:1.3em;color:#388e3c'>{total_due:,.2f} zł</span>
  </div>
</div>
""", unsafe_allow_html=True)

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

# === Sekcja szczegółów wybranej faktury ===

# Separator wizualny (np. cienka linia lub kolorowy pasek)
st.markdown("""
    <hr style='border: none; border-top: 3px solid #dbe4ee; margin: 2em 0 2em 0;'>
""", unsafe_allow_html=True)


cols = st.columns([1,1], gap="large")

with cols[0]:
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

with cols[1]:
    st.markdown("### 🧮 Szczegółowe naliczenie")
    calc_df = detailed_interest_with_payments(
        inv.amount,
        inv.due_date,
        sorted(inv.payments, key=lambda p: p.date),
        datetime.today()
    )
    st.dataframe(calc_df, use_container_width=True)
    st.download_button(
        "⬇️ Pobierz szczegóły (CSV)",
        data=calc_df.to_csv(index=False, sep=";").encode("utf-8"),
        file_name=f"odsetki_faktura_{inv.id}.csv",
        mime="text/csv",
    )

st.markdown("</div>", unsafe_allow_html=True)

# --- Floating note at bottom right ---
st.markdown(
    """
    <style>
    .coded-by-note {
        position: fixed;
        bottom: 18px;
        right: 28px;
        background: #fffbe7;
        color: #222;
        padding: 8px 20px;
        border-radius: 10px;
        font-size: 1.05em;
        font-weight: bold;
        z-index: 99999;
        box-shadow: 0 4px 16px rgba(0,0,0,0.13);
        border: 2px solid #ffd700;
        pointer-events: none;
        user-select: none;
        opacity: 0.98;
    }
    </style>
    <div class="coded-by-note">Coded by Krzysztof Pietrowicz</div>
    """,
    unsafe_allow_html=True
)