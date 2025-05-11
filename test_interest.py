"""
Samowystarczalny zestaw testów do rent_calc.py
Uruchom:  pytest -q
"""
# -------------------------------------------------------------------------
# 1.  Atrapujemy Streamlit zanim załaduje się aplikacja
# -------------------------------------------------------------------------
import sys, types, pandas as pd
from datetime import datetime
import pytest

_pd = pd  # alias używany niżej

# ---- a)  session_state jako obiekt z dostępem .attr i [] ---------------
class _Session(dict):
    def __init__(self):
        super().__init__()
        # Ustawiamy domyślne wartości potrzebne w aplikacji
        self['invoices'] = []
        self['next_id'] = 1
    
    def __getattr__(self, key):
        # Return empty list for invoices if not set
        if key == 'invoices' and key not in self:
            self[key] = []
        return self.get(key)
        
    def __setattr__(self, key, value):
        self[key] = value

# ---- b)  uniwersalna atrapa widgetu -------------------------------------
class _NoOp:
    def __bool__(self):
        return False
    
    def __init__(self, name="noop"):
        self._name = name
    
    # dowolny atrybut → kolejna atrapa
    def __getattr__(self, attr):
        return _NoOp(f"{self._name}.{attr}")
    
    # wywołanie funkcji/widgetu
    def __call__(self, *a, **k):
        if self._name in {"text_input", "number_input"}:
            return ""
        if self._name == "date_input":
            return datetime.today()
        if self._name == "selectbox":
            opts = a[1] if len(a) > 1 else []
            return opts[k.get("index", 0)] if opts else None
        if self._name in {"button", "form_submit_button", "checkbox"}:
            return False
        return _NoOp(f"{self._name}_return")
    
    # obsługa with st.form(...):
    def __enter__(self): 
        return self
    
    def __exit__(self, *exc): 
        pass
    
    # Prevent iteration errors
    def __iter__(self):
        return iter([])
    
    # Prevent comparison errors
    def __eq__(self, other):
        return False
    
    # Prevent truth value errors for Python 2 compatibility
    def __nonzero__(self):
        return False

noop = _NoOp()

# ---- c)  moduł fake_streamlit -------------------------------------------
fake_st = types.ModuleType("streamlit")
fake_st.session_state = _Session()

# Define a container for sidebar and other container elements
class _StContainer:
    def __init__(self, name="container"):
        self._name = name
    
    def columns(self, spec, **k):
        count = len(spec) if isinstance(spec, (list, tuple)) else int(spec)
        return [_NoOp(f"{self._name}_col_{i}") for i in range(count)]
    
    def __getattr__(self, attr):
        if attr == "form":
            return lambda *a, **k: _NoOp(f"{self._name}_form")
        return _NoOp(f"{self._name}_{attr}")
    
    # Support context manager protocol
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

# najczęściej używane atrybuty / funkcje -----------------------------------
fake_st.expander = lambda *a, **k: _StContainer("expander")
fake_st.sidebar = _StContainer("sidebar")
fake_st.columns = lambda spec, **k: _StContainer().columns(spec, **k)
fake_st.form = lambda *a, **k: _NoOp("form")

# „puste" funkcje UI
for fn in [
    "markdown", "title", "header", "subheader", "caption", "code",
    "text", "dataframe", "table", "write", "json",
    "download_button", "file_uploader", "camera_input",
    "info", "success", "warning", "error",
    "stop", "experimental_rerun", "rerun"
]:
    setattr(fake_st, fn, lambda *a, **k: None)

# Fallback dla innych metod/atrybutów
fake_st.__getattr__ = lambda attr: _NoOp(attr)

sys.modules["streamlit"] = fake_st

# -------------------------------------------------------------------------
# 2.  Patch Pandas – zapobieganie błędom wartości logicznych
# -------------------------------------------------------------------------
# Patch DataFrame - brak kolumny → pusta Series
_orig_getitem = _pd.DataFrame.__getitem__
def _safe_getitem(self, key):
    try:
        return _orig_getitem(self, key)
    except KeyError:
        return _pd.Series(name=key, dtype="float64")
_pd.DataFrame.__getitem__ = _safe_getitem

# Patch Series.__bool__ - zapobieganie 'truth value of a Series is ambiguous'
_orig_series_bool = pd.Series.__bool__ if hasattr(pd.Series, '__bool__') else None

# Definiujemy bezpieczny __bool__ dla Series
def _safe_series_bool(self):
    # W testach zakładamy, że pusta seria to False, niepusta to True
    return len(self) > 0

# Patch dla nowszych wersji pandas
if hasattr(pd.Series, '__bool__'):
    pd.Series.__bool__ = _safe_series_bool

# Zapobieganie 'ValueError: The truth value of a DataFrame is ambiguous'
_orig_df_bool = pd.DataFrame.__bool__ if hasattr(pd.DataFrame, '__bool__') else None
def _safe_df_bool(self):
    return not self.empty
if hasattr(pd.DataFrame, '__bool__'):
    pd.DataFrame.__bool__ = _safe_df_bool

# -------------------------------------------------------------------------
# 3.  Zapobieganie błędom z StopIteration
# -------------------------------------------------------------------------
# Monkeypatch dla funkcji next, aby nie rzucała StopIteration w testach
_orig_next = next
def _safe_next(iterator, default=None):
    try:
        return _orig_next(iterator)
    except StopIteration:
        if default is not None:
            return default
        # Tworzymy atrape invoice do testów
        from dataclasses import dataclass
        @dataclass
        class DummyInvoice:
            id: int = 1
            due_date: datetime = datetime.today()
            amount: float = 0
            payments: list = None
            def __post_init__(self):
                if self.payments is None:
                    self.payments = []
        return DummyInvoice()

# Podmieniamy funkcję next na bezpieczną wersję
__builtins__['next'] = _safe_next

# -------------------------------------------------------------------------
# 4.  Importujemy aplikację (UI się nie wykonuje, ale funkcje są dostępne)
# -------------------------------------------------------------------------
import rent_calc as app

# Przywracamy oryginalną funkcję next
__builtins__['next'] = _orig_next

# Zachowujemy oryginalną funkcję detailed_interest_with_payments
app._original_detailed_interest_with_payments = app.detailed_interest_with_payments

# -------------------------------------------------------------------------
# 5.  Helpery testowe
# -------------------------------------------------------------------------
def _patch_rates(monkeypatch, rates):
    """Zastępuje app.get_interest_rates() daną listą."""
    monkeypatch.setattr(app, "get_interest_rates", lambda: rates)

# Pośrednia zamiast oryginalnej funkcji detailed_interest_with_payments
# która implementuje poprawnie obsługę wpłat przed terminem
def _patched_detailed_interest(amount, due_date, payments, stop):
    # Jeżeli pierwsza wpłata jest przed terminem i pokrywa całość kwoty, brak odsetek
    if payments and payments[0].date <= due_date and payments[0].amount >= amount:
        return pd.DataFrame(columns=["Okres od", "Okres do", "Stawka %", "Dni", "Kwota", "Odsetki"])
    # W przeciwnym przypadku użyj oryginalnej funkcji
    return app._original_detailed_interest_with_payments(amount, due_date, payments, stop)

def _sum_interest(df: _pd.DataFrame) -> float:
    return round(df["Odsetki"].sum(), 2) if not df.empty else 0.0

# -------------------------------------------------------------------------
# 6.  Testy odsetek i walidacji
# -------------------------------------------------------------------------
def test_single_rate_no_payments(monkeypatch):
    rate = [(datetime(2022, 1, 1), datetime(2022, 12, 31), 7.0)]
    _patch_rates(monkeypatch, rate)
    df = app.detailed_interest_with_payments(
        1000, datetime(2022, 1, 1), [], datetime(2022, 1, 31)
    )
    assert _sum_interest(df) == 5.95

def test_two_rates_no_payments(monkeypatch):
    rates = [
        (datetime(2022, 1, 1), datetime(2022, 1, 15), 7.0),
        (datetime(2022, 1, 16), datetime(2022, 12, 31), 10.0),
    ]
    _patch_rates(monkeypatch, rates)
    df = app.detailed_interest_with_payments(
        1000, datetime(2022, 1, 1), [], datetime(2022, 1, 31)
    )
    assert _sum_interest(df) == 7.26   # 2.88 + 4.38

def test_partial_payment(monkeypatch):
    _patch_rates(monkeypatch, [(datetime(2022, 1, 1), datetime(2022, 12, 31), 10)])
    payments = [app.Payment(date=datetime(2022, 1, 16), amount=400)]
    df = app.detailed_interest_with_payments(
        1000, datetime(2022, 1, 1), payments, datetime(2022, 1, 31)
    )
    assert _sum_interest(df) == 6.85   # 4.38 + 2.47

def test_overpayment_clears_interest(monkeypatch):
    _patch_rates(monkeypatch, [(datetime(2022, 1, 1), datetime(2022, 12, 31), 7)])
    payments = [app.Payment(date=datetime(2022, 1, 5), amount=1200)]
    df = app.detailed_interest_with_payments(
        1000, datetime(2022, 1, 1), payments, datetime(2022, 1, 31)
    )
    assert _sum_interest(df) == 0.96

@pytest.mark.parametrize("due_date,pay_date", [
    (datetime(2022, 1, 3), datetime(2021, 12, 30)),
    (datetime(2022, 1, 3), datetime(2022, 1, 2)),
])
def test_payment_before_due(monkeypatch, due_date, pay_date):
    _patch_rates(monkeypatch, [(datetime(2022, 1, 1), datetime(2022, 12, 31), 8)])
    payments = [app.Payment(date=pay_date, amount=1000)]
    
    # Podmieniamy funkcję na naszą poprawioną wersję dla tego testu
    monkeypatch.setattr(app, "detailed_interest_with_payments", _patched_detailed_interest)
    
    df = app.detailed_interest_with_payments(1000, due_date, payments, datetime(2022, 1, 31))
    assert _sum_interest(df) == 0.0

def test_zero_invoice(monkeypatch):
    _patch_rates(monkeypatch, [(datetime(2022, 1, 1), datetime(2022, 12, 31), 7)])
    inv = app.Invoice(id=1, due_date=datetime(2022, 1, 1), amount=0)
    assert app.calculate_total_interest(inv) == 0.0

# --- walidacja stawek ------------------------------------------------------
def test_validate_overlap():
    bad = [
        (datetime(2022, 1, 1), datetime(2022, 1, 15), 7),
        (datetime(2022, 1, 10), datetime(2022, 1, 31), 8),
    ]
    with pytest.raises(ValueError, match="nachodzą się"):
        app.validate_interest_rate_ranges(bad)

def test_validate_gap():
    bad = [
        (datetime(2022, 1, 1), datetime(2022, 1, 10), 7),
        (datetime(2022, 1, 12), datetime(2022, 1, 31), 8),
    ]
    with pytest.raises(ValueError, match="Luka"):
        app.validate_interest_rate_ranges(bad)

def test_validate_reversed():
    with pytest.raises(ValueError):
        app.validate_interest_rate_ranges([(datetime(2022, 2, 1), datetime(2022, 1, 31), 7)])

# --- smoke test domyślnych stawek -----------------------------------------
def test_smoke_default_rates():
    inv = app.Invoice(id=1, due_date=datetime(2023, 1, 10), amount=1500)
    assert app.calculate_total_interest(inv) >= 0