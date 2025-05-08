# test_interest.py
from datetime import datetime
from rent_interest_web_app import Payment, detailed_interest_with_payments

# ---------- pomocnicze ----------
def interest(principal, start, end, rate):
    days = (end - start).days + 1
    return round(principal * rate / 100 * days / 365, 2)

# ---------- testy ----------------------------------------------------------
def test_prosty_przypadek():
    """Jedna faktura, brak wpłat – okres w jednej stawce (7%)."""
    start = datetime(2017, 9, 10)   # due_date
    stop  = datetime(2018, 5, 8)    # zapłata
    df = detailed_interest_with_payments(
        1041.98, start, [], stop
    )
    assert df["Dni"].sum() == 241
    assert df["Odsetki"].sum() == interest(1041.98, start, stop, 7.00) == 48.16

def test_z_partialna_wplata():
    """Wpłata 300 zł w połowie okresu."""
    start = datetime(2021, 1, 10)
    stop  = datetime(2021, 6, 10)
    pays  = [Payment(date=datetime(2021,3,15), amount=300)]
    df = detailed_interest_with_payments(1000, start, pays, stop)
    # segment 1: 10.01‑15.03 (65 dni) od 1000 zł
    # segment 2: 16.03‑10.06 (87 dni) od 700 zł
    assert df["Dni"].sum() == 152
    assert round(df["Odsetki"].sum(),2) == round(1000*7/100*65/365 + 700*6/100*87/365,2)

def test_wplata_tego_samego_dnia():
    """Wpłata całej kwoty w tym samym dniu co wymagalność – brak odsetek."""
    dt = datetime(2022, 2, 10)
    pays = [Payment(date=dt, amount=500)]
    df = detailed_interest_with_payments(500, dt, pays, dt)
    assert df.empty or df["Odsetki"].sum() == 0
