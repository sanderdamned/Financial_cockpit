import io
import hashlib
from datetime import date, timedelta
from datetime import date

import pandas as pd
import streamlit as st
from supabase import create_client

from categorization import (
    CATEGORIES,
    INCOME_CATEGORIES,
    EXPENSE_CATEGORIES,
)

from database import Database

from ui_helpers import (
    euro,
    without_transfers,
    is_transfer_series,
    render_transaction_metrics,
)

from financial_engine import (
    prepare_transactions,
    detect_transfer_transactions,
    detect_recurring_transactions,
    calculate_monthly_metrics,
    calculate_month_forecast,
    calculate_budget_status,
    calculate_financial_health,
    calculate_safe_to_spend,
    calculate_monthly_recurring_cost,
    calculate_yearly_recurring_cost,
    calculate_monthly_recurring_income,
)


# ============================================================
# CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="Financial Cockpit",
    page_icon="💰",
    layout="wide",
)


# ============================================================
# DATE / PERIOD HELPERS
# ============================================================

DUTCH_MONTHS = {
    1: "januari",
    2: "februari",
    3: "maart",
    4: "april",
    5: "mei",
    6: "juni",
    7: "juli",
    8: "augustus",
    9: "september",
    10: "oktober",
    11: "november",
    12: "december",
}


def today():
    """
    Geeft de actuele datum terug.

    Gebruik van date.today() zorgt ervoor dat de datum
    automatisch iedere dag opnieuw correct wordt bepaald.
    """
    return date.today()


def current_period():
    """Geeft de huidige maand als pandas Period terug."""
    return pd.Period(today(), freq="M")


def current_year():
    """Geeft het huidige kalenderjaar terug."""
    return today().year


def format_period(period):
    """Nederlandse weergave van een maandperiode."""
    period = pd.Period(period, freq="M")

    label = (
        f"{DUTCH_MONTHS[period.month]} "
        f"{period.year}"
    )

    current = current_period()

    if period == current:
        return f"{label} — huidige maand"

    if period > current:
        return f"{label} — forecast"

    return label


def format_year(year):
    """Jaarweergave."""
    year = int(year)

    if year == current_year():
        return f"{year} — huidig jaar"

    if year > current_year():
        return f"{year} — forecast"

    return str(year)


def available_month_periods(
    transactions,
    months_forward=12,
    months_backward=12,
):
    """
    Maak een volledige lijst met maanden rondom vandaag.

    Belangrijk:
    maanden hoeven NIET in de transactiedatabase te bestaan.

    Hierdoor kan bijvoorbeeld september 2026 t/m september 2027
    geselecteerd worden terwijl september 2027 nog geen transacties
    bevat.
    """

    current = current_period()

    start = current - months_backward
    end = current + months_forward

    periods = []

    for offset in range(
        (end - start).n + 1
    ):
        periods.append(
            start + offset
        )

    # Voeg historische transactiemaanden toe die buiten de standaard
    # 12-maandsrange vallen.
    if transactions is not None:
        try:
            df = (
                transactions
                if isinstance(
                    transactions,
                    pd.DataFrame,
                )
                else pd.DataFrame(transactions)
            )

            if (
                not df.empty
                and "date" in df.columns
            ):
                dates = pd.to_datetime(
                    df["date"],
                    errors="coerce",
                ).dropna()

                historical_periods = (
                    dates
                    .dt.to_period("M")
                    .unique()
                    .tolist()
                )

                periods.extend(
                    historical_periods
                )
        except Exception:
            pass

    return sorted(
        set(periods),
        reverse=True,
    )


def month_selector(
    transactions,
    key,
    months_forward=12,
    months_backward=12,
):
    """
    Universele maandselector voor het dashboard en budgetten.

    Geeft altijd toekomstige maanden weer.
    """

    periods = available_month_periods(
        transactions,
        months_forward=months_forward,
        months_backward=months_backward,
    )

    if not periods:
        periods = [current_period()]

    current = current_period()

    default_index = (
        periods.index(current)
        if current in periods
        else 0
    )

    return st.selectbox(
        "📅 Maand",
        periods,
        index=default_index,
        format_func=format_period,
        key=key,
    )


def available_years(transactions):
    """
    Geeft alle geïmporteerde jaren terug plus het huidige jaar
    en het komende jaar.
    """

    years = {
        current_year(),
        current_year() + 1,
    }

    if transactions is not None:
        try:
            df = (
                transactions
                if isinstance(
                    transactions,
                    pd.DataFrame,
                )
                else pd.DataFrame(transactions)
            )

            if (
                not df.empty
                and "date" in df.columns
            ):
                dates = pd.to_datetime(
                    df["date"],
                    errors="coerce",
                ).dropna()

                years.update(
                    dates.dt.year.astype(int).tolist()
                )
        except Exception:
            pass

    return sorted(
        years,
        reverse=True,
    )


# ============================================================
# YEAR CALCULATIONS
# ============================================================

def calculate_year_actuals(
    transactions,
    year,
):
    """
    Bereken de werkelijke cijfers voor een volledig kalenderjaar.
    """

    year = int(year)

    if transactions is None:
        return {
            "income": 0.0,
            "expenses": 0.0,
            "net": 0.0,
        }

    try:
        df = (
            transactions
            if isinstance(
                transactions,
                pd.DataFrame,
            )
            else pd.DataFrame(transactions)
        )

        if df.empty:
            return {
                "income": 0.0,
                "expenses": 0.0,
                "net": 0.0,
            }

        df = prepare_transactions(df)

        if df.empty:
            return {
                "income": 0.0,
                "expenses": 0.0,
                "net": 0.0,
            }

        df = df[
            df["date"].dt.year == year
        ].copy()

        if df.empty:
            return {
                "income": 0.0,
                "expenses": 0.0,
                "net": 0.0,
            }

        try:
            df = without_transfers(df)
        except Exception:
            pass

        income = df.loc[
            df["flow"] == "Inkomst",
            "amount",
        ].sum()

        expenses = df.loc[
            df["flow"] == "Uitgave",
            "amount",
        ].abs().sum()

        return {
            "income": float(income),
            "expenses": float(expenses),
            "net": float(
                income - expenses
            ),
        }

    except Exception:
        return {
            "income": 0.0,
            "expenses": 0.0,
            "net": 0.0,
        }


def calculate_year_forecast(
    transactions,
    recurring_rows,
    budgets,
    year,
):
    """
    Bereken forecast voor alle 12 maanden van een jaar.

    Voor:
    - historische maanden: werkelijke cijfers
    - huidige maand: werkelijke cijfers
    - toekomstige maanden: forecast

    Voor een volledig toekomstig jaar worden alle 12 maanden
    als forecast berekend.
    """

    year = int(year)
    current = current_period()

    monthly = []

    for month in range(1, 13):

        period = pd.Period(
            f"{year}-{month:02d}",
            freq="M",
        )

        # --------------------------------------------
        # HISTORICAL / CURRENT
        # --------------------------------------------

        if period <= current:

            metrics = calculate_monthly_metrics(
                transactions,
                period,
                exclude_internal_transfers=True,
            )

            monthly.append(
                {
                    "month": period,
                    "income": float(
                        metrics.get(
                            "income",
                            0,
                        )
                    ),
                    "expenses": float(
                        metrics.get(
                            "expenses",
                            0,
                        )
                    ),
                    "net": float(
                        metrics.get(
                            "net",
                            0,
                        )
                    ),
                    "type": "Actual",
                }
            )

        # --------------------------------------------
        # FUTURE
        # --------------------------------------------

        else:

            forecast = calculate_month_forecast(
                transactions,
                period,
                recurring_rows,
                budgets,
            )

            monthly.append(
                {
                    "month": period,
                    "income": float(
                        forecast.get(
                            "projected_income",
                            0,
                        )
                    ),
                    "expenses": float(
                        forecast.get(
                            "projected_expenses",
                            0,
                        )
                    ),
                    "net": float(
                        forecast.get(
                            "projected_net",
                            0,
                        )
                    ),
                    "type": "Forecast",
                }
            )

    return pd.DataFrame(monthly)


def calculate_full_year_forecast(
    transactions,
    recurring_rows,
    budgets,
    year,
):
    """
    Volledige forecast van een toekomstig kalenderjaar.

    Dit is bewust een aparte functie zodat een volledig toekomstig
    jaar niet per ongeluk werkelijke transacties van een ander jaar
    gebruikt.
    """

    year = int(year)

    rows = []

    for month in range(1, 13):

        period = pd.Period(
            f"{year}-{month:02d}",
            freq="M",
        )

        forecast = calculate_month_forecast(
            transactions,
            period,
            recurring_rows,
            budgets,
        )

        rows.append(
            {
                "month": period,
                "income": float(
                    forecast.get(
                        "projected_income",
                        0,
                    )
                ),
                "expenses": float(
                    forecast.get(
                        "projected_expenses",
                        0,
                    )
                ),
                "net": float(
                    forecast.get(
                        "projected_net",
                        0,
                    )
                ),
                "type": "Forecast",
            }
        )

    return pd.DataFrame(rows)


# ============================================================
# SUPABASE
# ============================================================

@st.cache_resource
def get_supabase():

    return create_client(
        st.secrets["SUPABASE_URL"],
        st.secrets["SUPABASE_KEY"],
    )


supabase = get_supabase()


# ============================================================
# DATABASE
# ============================================================

def load_merchant_category_rules(
    user_id,
):
    """Load persistent merchant -> category rules."""

    try:

        result = (
            supabase
            .table("merchant_category_rules")
            .select("*")
            .eq(
                "user_id",
                user_id,
            )
            .order("merchant")
            .execute()
        )

        return {
            str(row["merchant"])
            .lower()
            .strip(): row["category"]
            for row in (
                result.data or []
            )
            if row.get("merchant")
        }

    except Exception as e:

        st.error(
            f"❌ Categorieregels konden niet "
            f"worden geladen: {e}"
        )

        return {}


def save_merchant_category_rule(
    user_id,
    merchant,
    category,
):

    merchant = (
        str(merchant)
        .strip()
        .lower()
    )

    if not merchant:
        return None

    try:

        result = (
            supabase
            .table("merchant_category_rules")
            .upsert(
                {
                    "user_id": user_id,
                    "merchant": merchant,
                    "category": category,
                    "updated_at":
                        pd.Timestamp.utcnow()
                        .isoformat(),
                },
                on_conflict=(
                    "user_id,merchant"
                ),
            )
            .execute()
        )

        return result.data or []

    except Exception as e:

        st.error(
            f"❌ Categorieregel kon niet "
            f"worden opgeslagen: {e}"
        )

        return None


def delete_merchant_category_rule(
    user_id,
    merchant,
):

    merchant = (
        str(merchant)
        .strip()
        .lower()
    )

    try:

        result = (
            supabase
            .table("merchant_category_rules")
            .delete()
            .eq(
                "user_id",
                user_id,
            )
            .eq(
                "merchant",
                merchant,
            )
            .execute()
        )

        return result.data or []

    except Exception as e:

        st.error(
            f"❌ Categorieregel kon niet "
            f"worden verwijderd: {e}"
        )

        return None


def update_transactions_for_merchant(
    user_id,
    merchant,
    category,
    flow=None,
):

    merchant = (
        str(merchant)
        .strip()
        .lower()
    )

    try:

        query = (
            supabase
            .table("transactions")
            .update({"category": category})
            .eq("user_id", user_id)
            .ilike("merchant", merchant)
        )
        if flow is not None:
            query = query.eq("flow", flow)
        result = query.execute()

        return result.data or []

    except Exception as e:

        st.error(
            f"❌ Bestaande transacties konden "
            f"niet worden bijgewerkt: {e}"
        )

        return None


def load_accounts(user_id):

    try:

        result = (
            supabase
            .table("accounts")
            .select("*")
            .eq(
                "user_id",
                user_id,
            )
            .order("created_at")
            .execute()
        )

        return result.data or []

    except Exception as e:

        st.error(
            f"❌ Rekeningen konden niet "
            f"worden geladen: {e}"
        )

        return []


# ============================================================
# DATABASE — TRANSACTIONS
# ============================================================

def _load_transactions_paginated(user_id, account_id=None, page_size=1000):
    """Fetch matching transactions in pages to avoid PostgREST row limits."""
    rows = []
    start = 0

    while True:
        query = (
            supabase
            .table("transactions")
            .select("*")
            .eq("user_id", user_id)
            .order("date", desc=True)
            .range(start, start + page_size - 1)
        )

        if account_id is not None:
            query = query.eq("account_id", account_id)

        page = query.execute().data or []
        rows.extend(page)

        if len(page) < page_size:
            break

        start += page_size

    return rows


def load_transactions(user_id, account_id):
    try:
        return _load_transactions_paginated(user_id, account_id)
    except Exception as e:
        st.error(f"❌ Transacties konden niet worden geladen: {e}")
        return []


def load_all_transactions(user_id):
    try:
        return _load_transactions_paginated(user_id)
    except Exception as e:
        st.error(f"❌ Alle transacties konden niet worden geladen: {e}")
        return []

def load_budgets(user_id):

    try:

        result = (
            supabase
            .table("budgets")
            .select("*")
            .eq(
                "user_id",
                user_id,
            )
            .order("category")
            .execute()
        )

        return result.data or []

    except Exception as e:

        st.error(
            f"❌ Budgetten konden niet "
            f"worden geladen: {e}"
        )

        return []


def save_budget(
    user_id,
    category,
    planned_amount,
    budget_type="monthly",
    period_months=1,
):
    """Save an editable budget and its monthly-normalized equivalent."""
    try:
        amount = max(0.0, float(planned_amount or 0))
        budget_type = str(budget_type or "monthly")
        if budget_type == "annual":
            months = 12
        elif budget_type == "periodic":
            months = max(1, int(period_months or 1))
        else:
            months = 1

        monthly_limit = amount / months
        payload = {
            "user_id": user_id,
            "category": category,
            "monthly_limit": monthly_limit,
            "planned_amount": amount,
            "budget_type": budget_type,
            "period_months": months,
        }
        return (
            supabase.table("budgets")
            .upsert(payload, on_conflict="user_id,category")
            .execute().data
        )
    except Exception as e:
        st.error(f"❌ Budget kon niet worden opgeslagen: {e}")
        return None


# ============================================================
# DATABASE — FINANCIAL GOALS AND PERIOD BUDGET PLANS
# ============================================================

def load_financial_goals(user_id):
    try:
        return (
            supabase.table("financial_goals")
            .select("*").eq("user_id", user_id)
            .order("target_date").execute().data or []
        )
    except Exception as e:
        st.error(f"❌ Spaardoelen konden niet worden geladen. Controleer of de SQL-migratie is uitgevoerd: {e}")
        return []


def save_financial_goal(user_id, values):
    try:
        payload = dict(values)
        payload["user_id"] = user_id
        return supabase.table("financial_goals").insert(payload).execute().data
    except Exception as e:
        st.error(f"❌ Spaardoel kon niet worden opgeslagen: {e}")
        return None


def load_budget_plans(user_id):
    try:
        return (
            supabase.table("budget_plans").select("*")
            .eq("user_id", user_id).order("period_start")
            .order("category").execute().data or []
        )
    except Exception as e:
        st.error(f"❌ Budgetplanning kon niet worden geladen. Controleer of de SQL-migratie is uitgevoerd: {e}")
        return []


def save_budget_plan(user_id, values):
    try:
        payload = dict(values)
        payload["user_id"] = user_id
        return supabase.table("budget_plans").insert(payload).execute().data
    except Exception as e:
        st.error(f"❌ Budgetvoorstel kon niet worden opgeslagen: {e}")
        return None


# ============================================================
# DATABASE — RECURRING
# ============================================================

def load_recurring_transactions(
    user_id,
    account_id,
):

    try:

        result = (
            supabase
            .table("recurring_transactions")
            .select("*")
            .eq(
                "user_id",
                user_id,
            )
            .eq(
                "account_id",
                account_id,
            )
            .order(
                "next_occurrence"
            )
            .execute()
        )

        return result.data or []

    except Exception as e:

        st.error(
            f"❌ Terugkerende transacties "
            f"konden niet worden geladen: {e}"
        )

        return []


# ============================================================
# RECURRING DATABASE
# ============================================================

def save_recurring_transactions(
    user_id,
    account_id,
    recurring_transactions,
):

    if not recurring_transactions:
        return []

    records = []

    for recurring in recurring_transactions:

        records.append(
            {
                "user_id": user_id,
                "account_id": account_id,
                "merchant":
                    recurring.get(
                        "merchant",
                        "Onbekend",
                    ),
                "category":
                    recurring.get(
                        "category",
                        "Overig",
                    ),
                "frequency":
                    recurring.get(
                        "frequency",
                        "Onbekend",
                    ),
                "expected_amount":
                    float(
                        recurring.get(
                            "expected_amount",
                            0,
                        )
                        or 0
                    ),
                "last_occurrence":
                    recurring.get(
                        "last_occurrence"
                    ),
                "next_occurrence":
                    recurring.get(
                        "next_occurrence"
                    ),
                "active": True,

                # Nieuwe recurring metadata
                "reliability":
                    recurring.get(
                        "reliability",
                        "Hoog",
                    ),

                "is_one_time_large":
                    bool(
                        recurring.get(
                            "is_one_time_large",
                            False,
                        )
                    ),
            }
        )

    try:

        result = (
            supabase
            .table("recurring_transactions")
            .upsert(
                records,
                on_conflict=(
                    "user_id,"
                    "account_id,"
                    "merchant"
                ),
            )
            .execute()
        )

        return result.data or []

    except Exception as e:

        st.error(
            f"❌ Terugkerende betalingen "
            f"konden niet worden opgeslagen: {e}"
        )

        return []


def update_recurring_active(
    recurring_id,
    active,
):

    try:

        return (
            supabase
            .table("recurring_transactions")
            .update(
                {
                    "active": active
                }
            )
            .eq(
                "id",
                recurring_id,
            )
            .execute()
            .data
        )

    except Exception as e:

        st.error(
            f"❌ Status kon niet "
            f"worden gewijzigd: {e}"
        )

        return None


def delete_recurring_transaction(
    recurring_id,
):

    try:

        return (
            supabase
            .table("recurring_transactions")
            .delete()
            .eq(
                "id",
                recurring_id,
            )
            .execute()
            .data
        )

    except Exception as e:

        st.error(
            f"❌ Terugkerende transactie "
            f"kon niet worden verwijderd: {e}"
        )

        return None


# ============================================================
# ING CSV HELPERS
# ============================================================

def detect_csv_separator(
    raw_bytes,
):

    sample = raw_bytes[:10000]

    try:
        text = sample.decode(
            "utf-8-sig"
        )
    except UnicodeDecodeError:
        try:
            text = sample.decode(
                "cp1252"
            )
        except UnicodeDecodeError:
            text = sample.decode(
                "latin-1"
            )

    candidates = [
        ";",
        ",",
        "\t",
    ]

    counts = {
        separator:
            text.count(separator)
        for separator in candidates
    }

    return max(
        counts,
        key=counts.get,
    )


def read_csv_with_encoding(
    uploaded_file,
):

    raw_bytes = uploaded_file.getvalue()

    separator = detect_csv_separator(
        raw_bytes
    )

    encodings = [
        "utf-8-sig",
        "utf-8",
        "cp1252",
        "latin-1",
    ]

    last_error = None

    for encoding in encodings:

        try:

            return pd.read_csv(
                io.BytesIO(raw_bytes),
                sep=separator,
                encoding=encoding,
                dtype=str,
            )

        except Exception as e:

            last_error = e

    raise last_error


def normalize_column_name(
    value,
):

    return (
        str(value)
        .strip()
        .lower()
        .replace("\ufeff", "")
    )


def find_csv_column(
    df,
    candidates,
):

    normalized = {
        normalize_column_name(column):
            column
        for column in df.columns
    }

    for candidate in candidates:

        key = normalize_column_name(
            candidate
        )

        if key in normalized:
            return normalized[key]

    return None


def parse_ing_date(
    value,
):

    if pd.isna(value):
        return pd.NaT

    text = str(value).strip()

    # ING: YYYYMMDD
    if (
        len(text) == 8
        and text.isdigit()
    ):

        parsed = pd.to_datetime(
            text,
            format="%Y%m%d",
            errors="coerce",
        )

        if not pd.isna(parsed):
            return parsed

    # Algemene fallback
    return pd.to_datetime(
        text,
        errors="coerce",
        dayfirst=True,
    )


def parse_ing_amount(
    value,
):

    if pd.isna(value):
        return None

    text = str(value).strip()

    if not text:
        return None

    text = (
        text
        .replace("€", "")
        .replace("EUR", "")
        .replace("eur", "")
        .replace(" ", "")
    )

    # Europese notatie:
    # 1.234,56 -> 1234.56
    if (
        "," in text
        and "." in text
    ):

        text = (
            text
            .replace(".", "")
            .replace(",", ".")
        )

    elif "," in text:

        text = text.replace(
            ",",
            ".",
        )

    try:
        return float(text)
    except Exception:
        return None


def normalize_flow(
    value,
):

    text = (
        str(value)
        .strip()
        .lower()
    )

    if text in [
        "credit",
        "bij",
        "bijschrijving",
        "income",
        "income",
        "in",
        "c",
    ]:
        return "Inkomst"

    if text in [
        "debit",
        "af",
        "afschrijving",
        "expense",
        "out",
        "d",
    ]:
        return "Uitgave"

    return "Onbekend"


def normalize_merchant(
    description,
    merchant_rules=None,
):

    text = (
        str(description)
        .lower()
        .strip()
    )

    merchant_rules = (
        merchant_rules or {}
    )

    for merchant in merchant_rules:

        merchant_clean = (
            str(merchant)
            .lower()
            .strip()
        )

        if (
            merchant_clean
            and merchant_clean in text
        ):
            return merchant_clean

    known_merchants = [
        "albert heijn",
        "jumbo",
        "plus",
        "lidl",
        "aldi",
        "dirk",
        "picnic",
        "hoogvliet",
        "vomar",
        "spar",
        "netflix",
        "spotify",
        "disney",
        "youtube",
        "apple",
        "amazon",
        "bol.com",
        "ziggo",
        "odido",
        "kpn",
        "vodafone",
        "shell",
        "esso",
        "bp",
        "anwb",
        "uber",
        "bolt",
        "ns",
        "q-park",
        "parkmobile",
        "rituals",
        "douglas",
        "booking.com",
        "airbnb",
    ]

    for merchant in known_merchants:

        if merchant in text:
            return merchant

    return text


def categorize_import_transaction(
    description,
    merchant,
    merchant_rules,
    flow=None,
):
    text = f"{description or ''} {merchant or ''}".lower()

    # Alleen regels toepassen die passen bij het type transactie.
    allowed_categories = (
        INCOME_CATEGORIES if flow == "Inkomst"
        else EXPENSE_CATEGORIES if flow == "Uitgave"
        else CATEGORIES
    )
    for rule_merchant, category in (merchant_rules or {}).items():
        rule_text = str(rule_merchant).strip().lower()
        if rule_text and rule_text in text and category in allowed_categories:
            return category

    if flow == "Inkomst":
        income_keyword_rules = {
            "Salaris": ["salaris", "salary", "loon", "payroll", "salarisbetaling", "wage"],
            "Belasting": ["belastingdienst", "belastingteruggave", "zorgtoeslag", "huurtoeslag", "kinderopvangtoeslag", "kindgebonden budget", "tax refund", "tax return"],
            "Rente": ["rente", "interest"],
            "Overboeking spaargeld": ["spaarrekening", "spaargeld", "savings", "overboeking", "overgemaakt van", "eigen rekening", "interne overboeking", "transfer from"],
            "Tikkies": ["tikkie", "tikkies"],
            "Overige inkomsten": ["refund", "terugbetaling", "cashback", "vergoeding"],
        }
        for category, keywords in income_keyword_rules.items():
            if any(keyword in text for keyword in keywords):
                return category
        return "Overige inkomsten"

    category_rules = {
        "Boodschappen": ["albert heijn", "jumbo", "plus", "lidl", "aldi", "dirk", "picnic", "hoogvliet", "vomar", "spar", "supermarkt"],
        "Telecom": ["ziggo", "odido", "t-mobile", "tmobile", "kpn", "vodafone", "tele2", "simyo"],
        "Vervoer": ["shell", "esso", "bp", "total", "texaco", "anwb", "q-park", "parkmobile", "uber", "bolt", "ov-chipkaart", "ns "],
        "Horeca": ["restaurant", "cafe", "café", "mcdonald", "burger king", "starbucks", "thuisbezorgd", "uber eats", "deliveroo"],
        "Entertainment": ["netflix", "spotify", "disney", "prime video", "pathe", "bioscoop", "youtube", "apple music"],
        "Abonnementen": ["subscription", "membership", "abonnement"],
        "Wonen": ["vattenfall", "essent", "eneco", "huur", "hypotheek", "waternet"],
        "Verzekeringen": ["verzekering", "achmea", "interpolis", "ohra", "aegon"],
        "Gezondheid": ["apotheek", "ziekenhuis", "tandarts", "dokter", "huisarts"],
        "Kleding": ["zara", "h&m", "uniqlo", "nike", "adidas"],
        "Persoonlijke verzorging": ["kapper", "barber", "rituals", "douglas", "ici paris"],
        "Kinderen": ["school", "kinderopvang", "creche", "crèche", "kinderdagverblijf"],
        "Vakantie": ["booking.com", "airbnb", "hotel", "camping"],
    }

    for category, keywords in category_rules.items():
        if category in allowed_categories and any(keyword in text for keyword in keywords):
            return category

    return "Overig"

def create_import_transaction_hash(
    transaction_date,
    description,
    amount,
    transaction_type,
):

    raw = (
        f"{transaction_date}|"
        f"{description}|"
        f"{amount}|"
        f"{transaction_type}"
    )

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()


def prepare_ing_csv(
    uploaded_file,
    merchant_category_rules,
):

    df = read_csv_with_encoding(
        uploaded_file
    )

    df.columns = [
        normalize_column_name(
            column
        )
        for column in df.columns
    ]

    df = df.dropna(
        axis=1,
        how="all",
    )

    description_column = find_csv_column(
        df,
        [
            "description",
            "omschrijving",
            "beschrijving",
            "name / description",
            "name",
            "naam",
            "details",
            "merchant",
            "transaction",
            "transactie",
        ],
    )

    amount_column = find_csv_column(
        df,
        [
            "amount",
            "amount (eur)",
            "amount (euro)",
            "bedrag",
            "waarde",
            "transactiebedrag",
        ],
    )

    date_column = find_csv_column(
        df,
        [
            "date",
            "datum",
            "transaction date",
            "transactiedatum",
        ],
    )

    flow_column = find_csv_column(
        df,
        [
            "debit/credit",
            "debit credit",
            "debit_credit",
            "af/bij",
            "af bij",
            "type",
        ],
    )

    missing = []

    if description_column is None:
        missing.append("omschrijving")

    if amount_column is None:
        missing.append("bedrag")

    if date_column is None:
        missing.append("datum")

    if flow_column is None:
        missing.append(
            "debit/credit"
        )

    if missing:

        raise ValueError(
            "Niet gevonden: "
            + ", ".join(missing)
            + "\n\nGevonden kolommen:\n"
            + "\n".join(
                df.columns
            )
        )

    # --------------------------------------------------------
    # DATE
    # --------------------------------------------------------

    df["parsed_date"] = (
        df[date_column]
        .apply(parse_ing_date)
    )

    # --------------------------------------------------------
    # AMOUNT
    # --------------------------------------------------------

    df["parsed_amount"] = (
        df[amount_column]
        .apply(parse_ing_amount)
    )

    # --------------------------------------------------------
    # FLOW
    # --------------------------------------------------------

    df["transaction_type"] = (
        df[flow_column]
        .astype(str)
        .str.strip()
        .str.lower()
    )

    df["flow"] = (
        df["transaction_type"]
        .apply(normalize_flow)
    )

    # --------------------------------------------------------
    # MERCHANT
    # --------------------------------------------------------

    df["merchant"] = (
        df[description_column]
        .apply(
            lambda value:
                normalize_merchant(
                    value,
                    merchant_category_rules,
                )
        )
    )

    # --------------------------------------------------------
    # CATEGORY
    # --------------------------------------------------------

    df["category"] = df.apply(
        lambda row:
            categorize_import_transaction(
                row[description_column],
                row["merchant"],
                merchant_category_rules,
                flow=row["flow"],
            ),
        axis=1,
    )

    # --------------------------------------------------------
    # HASH
    # --------------------------------------------------------

    df["transaction_hash"] = df.apply(
        lambda row:
            create_import_transaction_hash(
                row["parsed_date"],
                row[description_column],
                row["parsed_amount"],
                row["transaction_type"],
            ),
        axis=1,
    )

    # --------------------------------------------------------
    # CLEAN
    # --------------------------------------------------------

    df = df[
        df["parsed_date"].notna()
        & df["parsed_amount"].notna()
    ].copy()

    df = df.drop_duplicates(
        subset=[
            "transaction_hash"
        ],
        keep="first",
    )

    return df, {
        "date": date_column,
        "description": description_column,
        "amount": amount_column,
        "flow": flow_column,
    }


# ============================================================
# AUTHENTICATION
# ============================================================

def show_login():

    st.title(
        "💰 Financial Cockpit"
    )

    st.write(
        "Log in om je persoonlijke "
        "financiële dashboard te bekijken."
    )

    login_tab, register_tab = st.tabs(
        [
            "Inloggen",
            "Account aanmaken",
        ]
    )

    with login_tab:

        email = st.text_input(
            "E-mailadres",
            key="login_email",
        )

        password = st.text_input(
            "Wachtwoord",
            type="password",
            key="login_password",
        )

        if st.button(
            "Inloggen",
            type="primary",
            use_container_width=True,
        ):

            if not email or not password:

                st.error(
                    "Vul je e-mailadres "
                    "en wachtwoord in."
                )

                return

            try:

                response = (
                    supabase
                    .auth
                    .sign_in_with_password(
                        {
                            "email": email,
                            "password": password,
                        }
                    )
                )

                if (
                    response.user
                    and response.session
                ):

                    st.session_state[
                        "user"
                    ] = response.user

                    st.session_state[
                        "access_token"
                    ] = (
                        response
                        .session
                        .access_token
                    )

                    st.session_state[
                        "refresh_token"
                    ] = (
                        response
                        .session
                        .refresh_token
                    )

                    supabase.auth.set_session(
                        response
                        .session
                        .access_token,
                        response
                        .session
                        .refresh_token,
                    )

                    st.rerun()

                else:

                    st.error(
                        "❌ Inloggen mislukt."
                    )

            except Exception as e:

                st.error(
                    f"❌ Inloggen mislukt: {e}"
                )

    with register_tab:

        email = st.text_input(
            "E-mailadres",
            key="register_email",
        )

        password = st.text_input(
            "Wachtwoord",
            type="password",
            key="register_password",
        )

        password_repeat = st.text_input(
            "Wachtwoord herhalen",
            type="password",
            key="register_password_repeat",
        )

        if st.button(
            "Account aanmaken",
            use_container_width=True,
        ):

            if not email:

                st.error(
                    "Vul een e-mailadres in."
                )

                return

            if password != password_repeat:

                st.error(
                    "❌ Wachtwoorden komen "
                    "niet overeen."
                )

                return

            if len(password) < 8:

                st.error(
                    "❌ Wachtwoord moet minimaal "
                    "8 tekens bevatten."
                )

                return

            try:

                response = (
                    supabase
                    .auth
                    .sign_up(
                        {
                            "email": email,
                            "password": password,
                        }
                    )
                )

                if response.user:

                    st.success(
                        "✅ Account aangemaakt."
                    )

                    st.info(
                        "Controleer je e-mail "
                        "om je account te bevestigen."
                    )

            except Exception as e:

                st.error(
                    f"❌ Account aanmaken "
                    f"mislukt: {e}"
                )


# ============================================================
# AUTH CHECK
# ============================================================

if "user" not in st.session_state:

    show_login()
    st.stop()


if (
    "access_token"
    not in st.session_state
    or
    "refresh_token"
    not in st.session_state
):

    st.warning(
        "Je sessie is niet meer beschikbaar."
    )

    if st.button(
        "Opnieuw inloggen"
    ):

        st.session_state.clear()
        st.rerun()

    st.stop()


try:

    supabase.auth.set_session(
        st.session_state[
            "access_token"
        ],
        st.session_state[
            "refresh_token"
        ],
    )

except Exception:

    st.warning(
        "Je sessie is verlopen. "
        "Log opnieuw in."
    )

    st.session_state.clear()
    st.stop()


user = st.session_state[
    "user"
]

user_id = user.id


# ============================================================
# LOAD CORE DATA
# ============================================================

merchant_category_rules = (
    load_merchant_category_rules(
        user_id
    )
)

accounts = load_accounts(
    user_id
)


# ============================================================
# FIRST ACCOUNT
# ============================================================

if not accounts:

    st.title(
        "💰 Financial Cockpit"
    )

    st.info(
        "Welkom! Voeg eerst een bankrekening toe."
    )

    with st.form(
        "first_account"
    ):

        name = st.text_input(
            "Naam rekening",
            placeholder="ING Betaalrekening",
        )

        bank = st.text_input(
            "Bank",
            placeholder="ING",
        )

        account_type = st.selectbox(
            "Type rekening",
            [
                "Betaalrekening",
                "Spaarrekening",
                "Creditcard",
                "Beleggingsrekening",
                "Anders",
            ],
        )

        submitted = (
            st.form_submit_button(
                "🏦 Rekening toevoegen",
                use_container_width=True,
            )
        )

        if submitted:

            if not name.strip():

                st.error(
                    "Vul een naam in."
                )

            else:

                try:

                    result = (
                        supabase
                        .table("accounts")
                        .insert(
                            {
                                "user_id":
                                    user_id,
                                "name":
                                    name.strip(),
                                "bank":
                                    bank.strip(),
                                "account_type":
                                    account_type,
                            }
                        )
                        .execute()
                    )

                    if result.data:

                        st.success(
                            "Rekening toegevoegd."
                        )

                        st.rerun()

                except Exception as e:

                    st.error(
                        "❌ Rekening kon niet "
                        f"worden toegevoegd: {e}"
                    )

    st.stop()


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.title(
        "💰 Financial Cockpit"
    )

    st.caption(
        f"Ingelogd als {user.email}"
    )

    st.caption(
        f"📅 Vandaag: "
        f"{today().strftime('%d-%m-%Y')}"
    )

    st.divider()

    chapter = st.radio(
        "Navigatie",
        [
            "📊 Overzicht",
            "💳 Transacties",
            "🏷️ Categorieën",
            "🔄 Terugkerend",
            "🎯 Budgetten",
            "💼 Vermogen & doelen",
            "📆 Jaaranalyse",
            "⚙️ Instellingen",
        ],
        label_visibility="collapsed",
    )

    st.divider()

    account_names = {
        account["name"]:
            account["id"]
        for account in accounts
    }

    selected_account_name = (
        st.selectbox(
            "🏦 Rekening",
            list(
                account_names.keys()
            ),
        )
    )

    selected_account_id = (
        account_names[
            selected_account_name
        ]
    )

    st.divider()

    if st.button(
        "Uitloggen",
        use_container_width=True,
    ):

        try:
            supabase.auth.sign_out()
        except Exception:
            pass

        st.session_state.clear()
        st.rerun()


# ============================================================
# LOAD ACCOUNT DATA
# ============================================================

transactions = load_transactions(
    user_id,
    selected_account_id,
)

transaction_df = prepare_transactions(
    transactions
)

saved_recurring = (
    load_recurring_transactions(
        user_id,
        selected_account_id,
    )
)

budgets = load_budgets(
    user_id
)


def income_source_summary(df):
    """Return incoming amounts grouped by source, keeping internal transfers visible separately."""
    if df is None or df.empty or "flow" not in df.columns:
        return pd.Series(dtype=float)
    incoming = df[df["flow"] == "Inkomst"].copy()
    if incoming.empty:
        return pd.Series(dtype=float)
    incoming["amount"] = pd.to_numeric(incoming["amount"], errors="coerce").fillna(0).abs()
    if "category" not in incoming.columns:
        incoming["category"] = "Overige inkomsten"
    incoming["category"] = incoming["category"].fillna("Overige inkomsten").astype(str)
    # Older imported transactions may have a generic category despite transfer-like descriptions.
    description = incoming.get("description", pd.Series("", index=incoming.index)).fillna("").astype(str)
    merchant = incoming.get("merchant", pd.Series("", index=incoming.index)).fillna("").astype(str)
    transfer_pattern = r"overboeking|eigen rekening|spaarrekening|spaargeld|transfer|overgemaakt van|interne overboeking"
    looks_like_transfer = (description + " " + merchant).str.contains(transfer_pattern, case=False, regex=True, na=False)
    incoming.loc[looks_like_transfer, "category"] = "Overboeking spaargeld"
    if "is_transfer" in incoming.columns:
        incoming.loc[incoming["is_transfer"].fillna(False), "category"] = "Overboeking spaargeld"
    return incoming.groupby("category")["amount"].sum().sort_values(ascending=False)


# ============================================================
# CHAPTER 1 — OVERVIEW
# ============================================================

if chapter == "📊 Overzicht":

    st.title(
        "📊 Overzicht"
    )

    st.caption(
        "Je financiële situatie in één oogopslag."
    )

    # --------------------------------------------------------
    # DATE
    # --------------------------------------------------------

    st.info(
        f"📅 Vandaag is "
        f"**{today().strftime('%d-%m-%Y')}**."
    )

    # --------------------------------------------------------
    # MONTH SELECTOR
    # --------------------------------------------------------

    selected_period = month_selector(
        transaction_df,
        key="overview_period",
        months_forward=12,
        months_backward=12,
    )

    is_future = (
        selected_period
        > current_period()
    )

    is_current = (
        selected_period
        == current_period()
    )

    # --------------------------------------------------------
    # RECURRING
    # --------------------------------------------------------

    active_recurring = [
        item
        for item in saved_recurring
        if item.get(
            "active",
            True,
        )
    ]

    # --------------------------------------------------------
    # ACTUAL METRICS
    # --------------------------------------------------------

    if not is_future:

        metrics = (
            calculate_monthly_metrics(
                transaction_df,
                selected_period,
                exclude_internal_transfers=True,
            )
        )

        income = float(
            metrics.get(
                "income",
                0,
            )
        )

        expenses = float(
            metrics.get(
                "expenses",
                0,
            )
        )

        net = float(
            metrics.get(
                "net",
                0,
            )
        )

    else:

        income = 0.0
        expenses = 0.0
        net = 0.0

    # --------------------------------------------------------
    # FORECAST
    # --------------------------------------------------------

    forecast = (
        calculate_month_forecast(
            transaction_df,
            selected_period,
            active_recurring,
            budgets,
        )
    )

    projected_income = float(
        forecast.get(
            "projected_income",
            0,
        )
    )

    projected_expenses = float(
        forecast.get(
            "projected_expenses",
            0,
        )
    )

    projected_net = float(
        forecast.get(
            "projected_net",
            0,
        )
    )

    # --------------------------------------------------------
    # TOP METRICS
    # --------------------------------------------------------

    if is_future:

        col1, col2, col3, col4 = (
            st.columns(4)
        )

        with col1:
            st.metric(
                "🔮 Verwachte inkomsten",
                euro(projected_income),
            )

        with col2:
            st.metric(
                "🔮 Verwachte uitgaven",
                euro(projected_expenses),
            )

        with col3:
            st.metric(
                "🔮 Verwacht netto",
                euro(projected_net),
            )

        with col4:
            st.metric(
                "Periode",
                "Forecast",
            )

    else:

        col1, col2, col3, col4 = (
            st.columns(4)
        )

        with col1:
            st.metric(
                "💰 Inkomsten",
                euro(income),
            )

        with col2:
            st.metric(
                "💸 Uitgaven",
                euro(expenses),
            )

        with col3:
            st.metric(
                "📈 Netto",
                euro(net),
            )

        with col4:

            savings_rate = (
                net / income * 100
                if income > 0
                else 0
            )

            st.metric(
                "🏦 Spaarpercentage",
                f"{savings_rate:.1f}%",
            )

    if is_future:

        st.caption(
            "Deze maand bevat nog geen werkelijke "
            "transacties. De cijfers hierboven zijn "
            "een forecast."
        )

    elif is_current:

        st.caption(
            "Dit zijn de werkelijke transacties "
            "die tot vandaag zijn geïmporteerd."
        )

    st.divider()

    # --------------------------------------------------------
    # MONTH TRANSACTIONS
    # --------------------------------------------------------

    month_df = transaction_df[
        transaction_df["date"]
        .dt.to_period("M")
        == selected_period
    ].copy()

    if not is_future:

        left, right = st.columns(2)

        with left:

            st.subheader(
                "💸 Uitgaven per categorie"
            )

            # Internal savings transfers are shown separately below, not as expenses.
            clean_month_df = without_transfers(month_df)
            expense_df = clean_month_df[
                clean_month_df["flow"] == "Uitgave"
            ].copy()

            if not expense_df.empty:

                expense_df[
                    "amount"
                ] = (
                    expense_df[
                        "amount"
                    ].abs()
                )

                category_summary = (
                    expense_df
                    .groupby(
                        "category"
                    )["amount"]
                    .sum()
                    .sort_values(
                        ascending=False
                    )
                )

                st.bar_chart(
                    category_summary
                )

            else:

                st.info(
                    "Geen uitgaven in deze maand."
                )

        with right:

            st.subheader(
                "🏪 Grootste uitgaven"
            )

            if not expense_df.empty:

                merchant_summary = (
                    expense_df
                    .groupby(
                        "merchant"
                    )["amount"]
                    .sum()
                    .sort_values(
                        ascending=False
                    )
                    .head(10)
                )

                st.bar_chart(
                    merchant_summary
                )

            else:

                st.info(
                    "Geen uitgaven in deze maand."
                )

    # --------------------------------------------------------
    # INCOME SOURCE BREAKDOWN
    # --------------------------------------------------------
    if not is_future:
        st.divider()
        st.subheader("💶 Waar komen je inkomsten vandaan?")
        income_sources = income_source_summary(month_df)
        if not income_sources.empty:
            income_total = float(income_sources.sum())
            transfer_income = float(income_sources.get("Overboeking spaargeld", 0.0))
            real_income = income_total - transfer_income
            income_col1, income_col2, income_col3 = st.columns(3)
            income_col1.metric("Totaal bijgeschreven", euro(income_total))
            income_col2.metric("Inkomsten excl. overboekingen", euro(real_income))
            income_col3.metric("Interne/waarschijnlijke overboekingen", euro(transfer_income))
            source_display = income_sources.rename_axis("Bron").rename("Bedrag")
            st.bar_chart(source_display)
            st.dataframe(
                source_display.reset_index().rename(columns={"Bedrag": "Bedrag"}),
                use_container_width=True,
                hide_index=True,
            )
            st.caption(
                "Overboekingen worden apart getoond omdat geld verplaatsen tussen eigen rekeningen "
                "geen nieuw inkomen is. Controleer de categorie als een overboeking niet juist is herkend."
            )
        else:
            st.info("Geen inkomsten in deze maand.")

        # Show savings/internal transfers separately from income and expenses.
        transfer_rows = month_df.loc[is_transfer_series(month_df)].copy()
        if not transfer_rows.empty:
            st.subheader("🔁 Overboekingen spaargeld (geen inkomsten of uitgaven)")
            transfer_rows["Bedrag"] = transfer_rows["amount"].abs()
            transfer_rows["Soort"] = transfer_rows["flow"].map({
                "Inkomst": "Bijschrijving naar rekening",
                "Uitgave": "Afschrijving van rekening",
            }).fillna("Overboeking")
            transfer_in = transfer_rows.loc[transfer_rows["flow"] == "Inkomst", "amount"].abs().sum()
            transfer_out = transfer_rows.loc[transfer_rows["flow"] == "Uitgave", "amount"].abs().sum()
            transfer_col1, transfer_col2 = st.columns(2)
            transfer_col1.metric("Overboekingen ontvangen", euro(transfer_in))
            transfer_col2.metric("Overboekingen verstuurd", euro(transfer_out))
            transfer_cols = [
                col for col in ["date", "description", "merchant", "Bedrag", "Soort", "category"]
                if col in transfer_rows.columns
            ]
            st.dataframe(transfer_rows[transfer_cols], use_container_width=True, hide_index=True)

    else:

        st.subheader(
            "🔮 Verwachte uitgaven"
        )

        st.info(
            "Voor toekomstige maanden zijn nog geen "
            "werkelijke transacties beschikbaar. "
            "De forecast gebruikt historische patronen "
            "en actieve terugkerende transacties."
        )

    # --------------------------------------------------------
    # FINANCIAL HEALTH
    # --------------------------------------------------------

    st.divider()

    st.subheader(
        "🧠 Financial Health"
    )

    budget_status = (
        calculate_budget_status(
            transaction_df,
            budgets,
            selected_period,
        )
    )

    health = calculate_financial_health(
        forecast,
        budget_status,
    )

    col1, col2, col3, col4 = (
        st.columns(4)
    )

    with col1:

        st.metric(
            "Verwachte inkomsten",
            euro(projected_income),
        )

    with col2:

        st.metric(
            "Verwachte uitgaven",
            euro(projected_expenses),
        )

    with col3:

        st.metric(
            "Verwacht netto",
            euro(projected_net),
        )

    with col4:

        st.metric(
            "Financial Health",
            f"{health.get('score', 0)}/100",
        )

        st.caption(
            health.get(
                "status",
                "",
            )
        )

    if projected_net >= 0:

        st.success(
            f"🟢 Je hebt waarschijnlijk "
            f"**{euro(projected_net)}** "
            "over aan het einde van deze maand."
        )

    else:

        st.error(
            f"🔴 Je komt waarschijnlijk "
            f"**{euro(abs(projected_net))}** "
            "tekort."
        )

    safe_to_spend = (
        calculate_safe_to_spend(
            forecast,
            buffer=0,
        )
    )

    st.info(
        f"💳 Je kunt volgens deze berekening "
        f"ongeveer **{euro(safe_to_spend)}** "
        "extra uitgeven."
    )

    # --------------------------------------------------------
    # YEAR OVERVIEW
    # --------------------------------------------------------

    st.divider()

    st.subheader(
        "📆 Jaaroverzicht"
    )

    years = available_years(
        transaction_df
    )

    selected_year = st.selectbox(
        "Jaar",
        years,
        format_func=format_year,
        key="overview_year",
    )

    selected_year = int(
        selected_year
    )

    if selected_year > current_year():

        year_df = (
            calculate_full_year_forecast(
                transaction_df,
                active_recurring,
                budgets,
                selected_year,
            )
        )

        year_type = "Forecast"

    else:

        year_df = (
            calculate_year_forecast(
                transaction_df,
                active_recurring,
                budgets,
                selected_year,
            )
        )

        year_type = (
            "Werkelijk + forecast"
            if selected_year == current_year()
            else "Werkelijk"
        )

    year_income = (
        year_df["income"].sum()
    )

    year_expenses = (
        year_df["expenses"].sum()
    )

    year_net = (
        year_df["net"].sum()
    )

    col1, col2, col3, col4 = (
        st.columns(4)
    )

    with col1:

        st.metric(
            "💰 Jaarinkomen",
            euro(year_income),
        )

    with col2:

        st.metric(
            "💸 Jaaruitgaven",
            euro(year_expenses),
        )

    with col3:

        st.metric(
            "📈 Jaarresultaat",
            euro(year_net),
        )

    with col4:

        year_savings_rate = (
            year_net
            / year_income
            * 100
            if year_income > 0
            else 0
        )

        st.metric(
            "🏦 Spaarpercentage",
            f"{year_savings_rate:.1f}%",
        )

    st.caption(
        f"Type overzicht: **{year_type}**"
    )

    # --------------------------------------------------------
    # YEAR CHART
    # --------------------------------------------------------

    chart_df = year_df.copy()

    chart_df[
        "Maand"
    ] = chart_df[
        "month"
    ].apply(
        lambda p:
            f"{DUTCH_MONTHS[p.month][:3]} "
            f"{p.year}"
    )

    chart_df = chart_df.set_index(
        "Maand"
    )

    st.bar_chart(
        chart_df[
            [
                "income",
                "expenses",
                "net",
            ]
        ]
    )

    # --------------------------------------------------------
    # YEAR TABLE
    # --------------------------------------------------------

    display_year_df = year_df.copy()

    display_year_df[
        "Maand"
    ] = display_year_df[
        "month"
    ].apply(
        lambda p:
            f"{DUTCH_MONTHS[p.month].capitalize()} "
            f"{p.year}"
    )

    display_year_df[
        "Inkomsten"
    ] = display_year_df[
        "income"
    ].apply(euro)

    display_year_df[
        "Uitgaven"
    ] = display_year_df[
        "expenses"
    ].apply(euro)

    display_year_df[
        "Netto"
    ] = display_year_df[
        "net"
    ].apply(euro)

    display_year_df[
        "Type"
    ] = display_year_df[
        "type"
    ].replace(
        {
            "Actual": "Werkelijk",
            "Forecast": "Forecast",
        }
    )

    st.dataframe(
        display_year_df[
            [
                "Maand",
                "Type",
                "Inkomsten",
                "Uitgaven",
                "Netto",
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )


# ============================================================
# CHAPTER 2 — TRANSACTIONS
# ============================================================

elif chapter == "💳 Transacties":

    st.title(
        "💳 Transacties"
    )

    st.caption(
        "Importeer, bekijk en controleer "
        "je banktransacties."
    )

    # --------------------------------------------------------
    # CSV IMPORT
    # --------------------------------------------------------

    with st.expander(
        "📁 Nieuwe CSV importeren",
        expanded=not transactions,
    ):

        uploaded_file = st.file_uploader(
            "Upload je banktransacties",
            type=["csv"],
        )

        if uploaded_file is not None:

            try:

                import_df, columns = (
                    prepare_ing_csv(
                        uploaded_file,
                        merchant_category_rules,
                    )
                )

                st.success(
                    f"✅ {len(import_df):,} "
                    "transacties gevonden."
                )

                preview_columns = [
                    "parsed_date",
                    columns["description"],
                    "merchant",
                    "parsed_amount",
                    "flow",
                    "category",
                ]

                st.dataframe(
                    import_df[
                        preview_columns
                    ],
                    use_container_width=True,
                    hide_index=True,
                )

                if st.button(
                    "💾 Transacties opslaan",
                    type="primary",
                    use_container_width=True,
                ):

                    records = []

                    for _, row in (
                        import_df.iterrows()
                    ):

                        records.append(
                            {
                                "user_id":
                                    user_id,

                                "account_id":
                                    selected_account_id,

                                "date":
                                    row[
                                        "parsed_date"
                                    ].strftime(
                                        "%Y-%m-%d"
                                    ),

                                "description":
                                    str(
                                        row[
                                            columns[
                                                "description"
                                            ]
                                        ]
                                    ),

                                "merchant":
                                    str(
                                        row[
                                            "merchant"
                                        ]
                                    ),

                                "amount":
                                    float(
                                        row[
                                            "parsed_amount"
                                        ]
                                    ),

                                "flow":
                                    row["flow"],

                                "category":
                                    row["category"],

                                "transaction_type":
                                    row[
                                        "transaction_type"
                                    ],

                                "transaction_hash":
                                    row[
                                        "transaction_hash"
                                    ],
                            }
                        )

                    try:

                        result = (
                            supabase
                            .table(
                                "transactions"
                            )
                            .upsert(
                                records,
                                on_conflict=(
                                    "user_id,"
                                    "transaction_hash"
                                ),
                            )
                            .execute()
                        )

                        st.success(
                            f"✅ "
                            f"{len(result.data or [])} "
                            "transacties verwerkt."
                        )

                        st.rerun()

                    except Exception as e:

                        st.error(
                            f"❌ Opslaan mislukt: {e}"
                        )

            except Exception as e:

                st.error(
                    f"❌ CSV kon niet worden verwerkt: {e}"
                )

    # --------------------------------------------------------
    # EXISTING TRANSACTIONS
    # --------------------------------------------------------

    st.divider()

    if transactions:

        transaction_display = (
            pd.DataFrame(
                transactions
            )
        )

        transaction_display[
            "amount"
        ] = pd.to_numeric(
            transaction_display[
                "amount"
            ],
            errors="coerce",
        )

        transfer_mask = (
            transaction_display.get("is_transfer", pd.Series(False, index=transaction_display.index))
            .fillna(False).astype(bool)
        )
        transfer_mask = transfer_mask | transaction_display.get(
            "category", pd.Series("", index=transaction_display.index)
        ).fillna("").astype(str).str.strip().str.lower().eq("overboeking spaargeld")
        transfer_text = (
            transaction_display.get("description", pd.Series("", index=transaction_display.index)).fillna("").astype(str)
            + " "
            + transaction_display.get("merchant", pd.Series("", index=transaction_display.index)).fillna("").astype(str)
        )
        transfer_mask = transfer_mask | transfer_text.str.contains(
            r"overboeking|eigen rekening|spaarrekening|spaargeld|transfer from|overgemaakt van|interne overboeking",
            case=False, regex=True, na=False,
        )
        transaction_display["Weergavetype"] = transaction_display["flow"].where(~transfer_mask, "Overboeking")
        regular_transactions = transaction_display.loc[~transfer_mask].copy()
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("Transacties", len(transaction_display))

        with col2:
            expenses = regular_transactions.loc[regular_transactions["flow"] == "Uitgave", "amount"].abs().sum()
            st.metric("Uitgaven", euro(expenses))

        with col3:
            income = regular_transactions.loc[regular_transactions["flow"] == "Inkomst", "amount"].sum()
            st.metric("Inkomsten", euro(income))

        with col4:
            transfer_amount = transaction_display.loc[transfer_mask, "amount"].abs().sum()
            st.metric("Overboekingen spaargeld", euro(transfer_amount))

        st.subheader("💶 Inkomsten per bron")
        source_summary = income_source_summary(transaction_display)
        if not source_summary.empty:
            st.bar_chart(source_summary)
            source_table = source_summary.rename_axis("Bron").rename("Bedrag").reset_index()
            source_table["Bedrag"] = source_table["Bedrag"].apply(euro)
            st.dataframe(source_table, use_container_width=True, hide_index=True)
            st.caption("Controleer in Categorieën of salaris, belasting/toeslagen en overboekingen juist zijn ingedeeld.")

        st.subheader(
            "Alle transacties"
        )

        display_columns = [
            "date",
            "description",
            "merchant",
            "amount",
            "Weergavetype",
            "category",
        ]

        available_columns = [
            column
            for column in display_columns
            if column
            in transaction_display.columns
        ]

        st.dataframe(
            transaction_display[
                available_columns
            ],
            use_container_width=True,
            hide_index=True,
        )

    else:

        st.info(
            "Nog geen transacties."
        )


# ============================================================
# CHAPTER 3 — CATEGORIES
# ============================================================

elif chapter == "🏷️ Categorieën":

    st.title(
        "🏷️ Categorieën"
    )

    st.caption(
        "Categoriseer inkomsten én uitgaven per winkel, organisatie of tegenrekening. "
        "Zo zie je apart wat salaris, belasting/toeslagen en overboekingen opleveren."
    )

    all_transactions = (
        load_all_transactions(
            user_id
        )
    )

    if not all_transactions:

        st.info(
            "Importeer eerst transacties."
        )

        st.stop()

    df = pd.DataFrame(
        all_transactions
    )

    df["amount"] = pd.to_numeric(
        df["amount"],
        errors="coerce",
    )

    category_transfer_mask = is_transfer_series(df)
    expenses = df[
        (df["flow"] == "Uitgave")
        & ~category_transfer_mask
    ].copy()

    if expenses.empty:
        st.info("Geen uitgaven gevonden. Je kunt hieronder wel inkomsten categoriseren.")

    st.info(
        "💡 Kies bijvoorbeeld "
        "**Albert Heijn → Boodschappen**. "
        "Deze keuze wordt permanent opgeslagen "
        "en toegepast op alle huidige én "
        "toekomstige transacties van deze merchant."
    )

    merchant_summary = (
        expenses
        .groupby(
            "merchant",
            dropna=False,
        )
        .agg(
            transactions=(
                "amount",
                "count",
            ),
            total=(
                "amount",
                lambda x:
                    x.abs().sum(),
            ),
        )
        .reset_index()
    )

    def merchant_current_category(
        merchant
    ):

        merchant = (
            str(merchant)
            .lower()
            .strip()
        )

        if (
            merchant
            in merchant_category_rules
        ):
            return (
                merchant_category_rules[
                    merchant
                ]
            )

        categories = (
            expenses.loc[
                expenses[
                    "merchant"
                ]
                .astype(str)
                .str.lower()
                .str.strip()
                == merchant,
                "category",
            ]
            .dropna()
            .astype(str)
        )

        if categories.empty:
            return "Overig"

        modes = categories.mode()

        return (
            modes.iloc[0]
            if not modes.empty
            else "Overig"
        )

    merchant_summary[
        "current_category"
    ] = merchant_summary[
        "merchant"
    ].apply(
        merchant_current_category
    )

    merchant_summary = (
        merchant_summary
        .sort_values(
            "total",
            ascending=False,
        )
    )

    col1, col2 = st.columns(
        [3, 1.8]
    )

    with col1:
        search = st.text_input(
            "🔎 Zoek winkel of organisatie",
            placeholder="Bijvoorbeeld Albert Heijn",
        )

    with col2:
        manage_categories = st.toggle(
            "Bestaande categorieën aanpassen",
            value=False,
            key="manage_existing_categories",
            help="Zet aan om eerder opgeslagen categoriekeuzes te wijzigen.",
        )

    # Standaard alleen merchants zonder opgeslagen keuze tonen.
    # In de beheerstand tonen we juist de merchants met een bestaande regel.
    rule_merchants = set(merchant_category_rules.keys())
    normalized_merchants = merchant_summary["merchant"].fillna("").astype(str).str.lower().str.strip()
    if manage_categories:
        merchant_summary = merchant_summary[normalized_merchants.isin(rule_merchants)].copy()
    else:
        merchant_summary = merchant_summary[~normalized_merchants.isin(rule_merchants)].copy()

    if search:

        merchant_summary = (
            merchant_summary[
                merchant_summary[
                    "merchant"
                ]
                .astype(str)
                .str.contains(
                    search,
                    case=False,
                    na=False,
                    regex=False,
                )
            ]
        )

    st.subheader(
        "🛠️ Bestaande categorieën aanpassen" if manage_categories else "☑️ Nog te categoriseren — winkels & organisaties"
    )

    if not merchant_summary.empty:
        st.caption(
            "Na opslaan verdwijnt een merchant uit deze afvinklijst. "
            "Zet ‘Bestaande categorieën aanpassen’ aan om opgeslagen keuzes later te wijzigen."
        )
    else:
        st.success(
            "Alle winkels en organisaties in deze lijst zijn gecategoriseerd."
            if not manage_categories
            else "Er zijn nog geen opgeslagen categorieën om aan te passen."
        )

    income_df = df[df["flow"] == "Inkomst"].copy()
    if not income_df.empty:
        income_df["amount"] = pd.to_numeric(income_df["amount"], errors="coerce").fillna(0)
        if "merchant" not in income_df.columns:
            income_df["merchant"] = "Onbekend"
        income_df["merchant"] = income_df["merchant"].fillna("Onbekend").astype(str)
        income_summary = (
            income_df.groupby("merchant", dropna=False)
            .agg(transactions=("amount", "count"), total=("amount", lambda values: values.abs().sum()))
            .reset_index()
            .sort_values("total", ascending=False)
        )
        income_summary["_merchant_key"] = income_summary["merchant"].fillna("").astype(str).str.lower().str.strip()
        if manage_categories:
            income_summary = income_summary[income_summary["_merchant_key"].isin(rule_merchants)].copy()
        else:
            income_summary = income_summary[~income_summary["_merchant_key"].isin(rule_merchants)].copy()
    else:
        income_summary = pd.DataFrame(columns=["merchant", "transactions", "total", "_merchant_key"])

    # Eén formulier voor alle categorieën: wijzigingen worden pas opgeslagen
    # wanneer de gebruiker onderaan één keer op 'Alles opslaan' klikt.
    pending_category_rules = []

    with st.form("bulk_category_rules_form"):
        st.markdown("### Uitgaven categoriseren")
        if merchant_summary.empty:
            st.caption("Geen openstaande uitgaven om te categoriseren.")
        for index, row in merchant_summary.reset_index(drop=True).iterrows():
            merchant = str(row["merchant"]).strip().lower()
            current_category = str(row["current_category"])
            total = abs(float(row["total"]))
            count = int(row["transactions"])
            rule_exists = merchant in merchant_category_rules
            with st.container(border=True):
                col1, col2, col3 = st.columns([3, 1.5, 2])
                with col1:
                    st.markdown(f"**{merchant.title()}**")
                    st.caption(f"{count} transacties · {euro(total)}" + (" · vaste regel" if rule_exists else ""))
                with col2:
                    st.caption("Huidige categorie")
                    st.write(current_category)
                with col3:
                    category_options = [category for category in EXPENSE_CATEGORIES]
                    selected_category = st.selectbox(
                        "Categorie",
                        category_options,
                        index=category_options.index(current_category) if current_category in category_options else category_options.index("Overig"),
                        key=f"bulk_expense_category_{index}_{merchant}",
                        label_visibility="collapsed",
                    )
                pending_category_rules.append((merchant, current_category, selected_category, "Uitgave"))

        st.divider()
        st.markdown("### Inkomsten categoriseren")
        if income_df.empty:
            st.caption("Geen openstaande inkomsten om te categoriseren.")
        for income_index, income_row in income_summary.reset_index(drop=True).iterrows():
            merchant_name = str(income_row["merchant"]).strip()
            merchant_key = merchant_name.lower()
            current_series = income_df.loc[
                income_df["merchant"].astype(str).str.lower().str.strip() == merchant_key,
                "category",
            ].dropna().astype(str)
            current_income_category = current_series.mode().iloc[0] if not current_series.empty else "Overige inkomsten"
            if current_income_category not in INCOME_CATEGORIES:
                current_income_category = "Overige inkomsten"
            with st.container(border=True):
                income_left, income_mid = st.columns([3, 2])
                with income_left:
                    st.markdown(f"**{merchant_name.title()}**")
                    st.caption(f"{int(income_row['transactions'])} bijschrijvingen · {euro(float(income_row['total']))}")
                with income_mid:
                    new_income_category = st.selectbox(
                        "Inkomstencategorie",
                        INCOME_CATEGORIES,
                        index=INCOME_CATEGORIES.index(current_income_category),
                        key=f"bulk_income_category_{income_index}_{merchant_key}",
                        label_visibility="collapsed",
                    )
                pending_category_rules.append((merchant_key, current_income_category, new_income_category, "Inkomst"))

        submitted_all_categories = st.form_submit_button(
            "💾 Alles opslaan en toepassen",
            type="primary",
            use_container_width=True,
        )

    if submitted_all_categories:
        successful = 0
        failed = []
        unchanged = 0
        changed_rules = [
            (merchant, old_category, new_category, flow)
            for merchant, old_category, new_category, flow in pending_category_rules
            if new_category != old_category
        ]

        allowed_by_flow = {
            "Uitgave": set(EXPENSE_CATEGORIES),
            "Inkomst": set(INCOME_CATEGORIES),
        }

        for merchant, old_category, category, flow in changed_rules:
            # Valideer vóór het opslaan: alleen gewijzigde categorieën en
            # uitsluitend categorieën die bij het transactie-type horen.
            if flow not in allowed_by_flow or category not in allowed_by_flow[flow]:
                failed.append(merchant)
                continue

            saved = save_merchant_category_rule(user_id, merchant, category)
            if saved is None:
                failed.append(merchant)
                continue

            updated = update_transactions_for_merchant(
                user_id, merchant, category, flow=flow
            )
            if updated is None:
                failed.append(merchant)
                continue
            successful += 1

        unchanged = len(pending_category_rules) - len(changed_rules)

        if failed:
            st.error(
                f"{successful} gewijzigde categorieën opgeslagen en toegepast. "
                f"{unchanged} ongewijzigd gelaten. Niet gelukt voor: "
                + ", ".join(sorted(set(failed)))
                + ". Controleer de foutmeldingen en probeer opnieuw."
            )
        elif successful == 0:
            st.info(
                "Er zijn geen categorieën gewijzigd. Er is niets opgeslagen; "
                "ongewijzigde keuzes worden niet als vaste regel vastgelegd."
            )
        else:
            st.success(
                f"✅ {successful} gewijzigde categorieën opgeslagen en toegepast. "
                f"{unchanged} ongewijzigd gelaten. Alleen gewijzigde keuzes worden "
                "als vaste regel onthouden voor toekomstige transacties."
            )
            st.rerun()

    # --------------------------------------------------------
    # CUSTOM RULE
    # --------------------------------------------------------

    st.divider()

    st.subheader(
        "⚙️ Eigen categorisatieregel"
    )

    with st.form(
        "custom_category_rule"
    ):

        custom_merchant = (
            st.text_input(
                "Naam / herkenning",
                placeholder="bijvoorbeeld bol.com",
            )
        )

        custom_category = (
            st.selectbox(
                "Categorie",
                [
                    category
                    for category
                    in CATEGORIES
                    if category
                    != "Inkomen"
                ],
            )
        )

        save_rule = (
            st.form_submit_button(
                "➕ Regel toevoegen",
                use_container_width=True,
            )
        )

        if save_rule:

            custom_merchant = (
                custom_merchant
                .strip()
                .lower()
            )

            if not custom_merchant:

                st.error(
                    "Vul een merchantnaam in."
                )

            else:

                saved = (
                    save_merchant_category_rule(
                        user_id,
                        custom_merchant,
                        custom_category,
                    )
                )

                if saved is not None:

                    updated = (
                        update_transactions_for_merchant(
                            user_id,
                            custom_merchant,
                            custom_category,
                        )
                    )

                    if updated is not None:

                        st.success(
                            f"✅ Regel opgeslagen: "
                            f"{custom_merchant.title()} "
                            f"→ {custom_category}"
                        )

                        st.rerun()

    # --------------------------------------------------------
    # PERSISTENT RULES
    # --------------------------------------------------------

    st.divider()

    st.subheader(
        "📌 Mijn eigen regels"
    )

    if not merchant_category_rules:

        st.caption(
            "Je hebt nog geen eigen "
            "categorisatieregels."
        )

    else:

        for (
            rule_index,
            (
                merchant,
                category,
            ),
        ) in enumerate(
            sorted(
                merchant_category_rules.items()
            )
        ):

            with st.container(
                border=True
            ):

                col1, col2, col3 = (
                    st.columns(
                        [
                            3,
                            2,
                            1.2,
                        ]
                    )
                )

                with col1:

                    st.markdown(
                        f"**{merchant.title()}**"
                    )

                with col2:

                    st.write(
                        category
                    )

                with col3:

                    if st.button(
                        "🗑️ Verwijderen",
                        key=(
                            f"delete_rule_"
                            f"{rule_index}_"
                            f"{merchant}"
                        ),
                        use_container_width=True,
                    ):

                        deleted = (
                            delete_merchant_category_rule(
                                user_id,
                                merchant,
                            )
                        )

                        if deleted is not None:

                            st.success(
                                "Regel verwijderd."
                            )

                            st.rerun()


# ============================================================
# CHAPTER 4 — RECURRING
# ============================================================

elif chapter == "🔄 Terugkerend":

    st.title(
        "🔄 Terugkerende betalingen"
    )

    st.caption(
        "Financial Cockpit zoekt naar betalingen "
        "die regelmatig terugkomen."
    )

    # --------------------------------------------------------
    # DETECT RECURRING TRANSACTIONS
    # --------------------------------------------------------

    if st.button(
        "🔍 Terugkerende betalingen detecteren",
        type="primary",
        use_container_width=True,
    ):

        # transaction_df is already normalized by
        # prepare_transactions() above.
        #
        # detect_recurring_transactions() expects
        # a pandas DataFrame.

        if transaction_df is None:

            recurring_input = pd.DataFrame()

        elif isinstance(
            transaction_df,
            pd.DataFrame,
        ):

            recurring_input = (
                transaction_df.copy()
            )

        else:

            recurring_input = pd.DataFrame(
                transaction_df
            )

        # ----------------------------------------------------
        # DETECT
        # ----------------------------------------------------

        detected = (
            detect_recurring_transactions(
                recurring_input
            )
        )

        # Safely handle None
        if detected is None:
            detected = []

        # ----------------------------------------------------
        # SAVE
        # ----------------------------------------------------

        if detected:

            saved = (
                save_recurring_transactions(
                    user_id,
                    selected_account_id,
                    detected,
                )
            )

            if saved:

                st.success(
                    f"✅ {len(saved)} "
                    "terugkerende betalingen opgeslagen."
                )

                st.rerun()

            else:

                st.warning(
                    "⚠️ Er zijn terugkerende "
                    "betalingen gevonden, maar ze "
                    "konden niet worden opgeslagen."
                )

        else:

            st.info(
                "Geen duidelijke terugkerende "
                "betalingen gevonden."
            )

    # --------------------------------------------------------
    # LOAD / DISPLAY SAVED RECURRING
    # --------------------------------------------------------

    if saved_recurring:

        active = [
            item
            for item in saved_recurring
            if item.get(
                "active",
                True,
            )
        ]

        inactive = [
            item
            for item in saved_recurring
            if not item.get(
                "active",
                True,
            )
        ]

        # ----------------------------------------------------
        # COST CALCULATIONS
        # ----------------------------------------------------

        monthly_cost = (
            calculate_monthly_recurring_cost(
                saved_recurring
            )
        )

        yearly_cost = (
            calculate_yearly_recurring_cost(
                saved_recurring
            )
        )

        # ----------------------------------------------------
        # SUMMARY
        # ----------------------------------------------------

        col1, col2, col3, col4 = (
            st.columns(4)
        )

        with col1:

            st.metric(
                "Actieve betalingen",
                len(active),
            )

        with col2:

            st.metric(
                "Geschatte maandlasten",
                euro(monthly_cost),
            )

        with col3:

            st.metric(
                "Geschatte jaarlasten",
                euro(yearly_cost),
            )

        with col4:

            st.metric(
                "Inactief",
                len(inactive),
            )

        st.divider()

        # ----------------------------------------------------
        # ACTIVE RECURRING
        # ----------------------------------------------------

        if active:

            st.subheader(
                "🔄 Actieve terugkerende betalingen"
            )

            for recurring in active:

                recurring_id = recurring.get(
                    "id"
                )

                merchant = recurring.get(
                    "merchant",
                    "Onbekend",
                )

                category = recurring.get(
                    "category",
                    "Overig",
                )

                frequency = recurring.get(
                    "frequency",
                    "Onbekend",
                )

                amount = float(
                    recurring.get(
                        "expected_amount",
                        0,
                    )
                    or 0
                )

                next_occurrence = recurring.get(
                    "next_occurrence",
                    "-",
                )

                reliability = recurring.get(
                    "reliability",
                    "-",
                )

                is_one_time_large = bool(
                    recurring.get(
                        "is_one_time_large",
                        False,
                    )
                )

                with st.container(
                    border=True
                ):

                    col1, col2, col3, col4 = (
                        st.columns(
                            [
                                3,
                                1.5,
                                1.5,
                                1.5,
                            ]
                        )
                    )

                    # ----------------------------------------
                    # MERCHANT
                    # ----------------------------------------

                    with col1:

                        st.markdown(
                            f"**{str(merchant).title()}**"
                        )

                        labels = (
                            f"{category} · "
                            f"{frequency}"
                        )

                        if is_one_time_large:

                            labels += (
                                " · grote eenmalige uitgave"
                            )

                        st.caption(
                            labels
                        )

                    # ----------------------------------------
                    # AMOUNT
                    # ----------------------------------------

                    with col2:

                        st.metric(
                            "Bedrag",
                            euro(amount),
                        )

                    # ----------------------------------------
                    # NEXT OCCURRENCE
                    # ----------------------------------------

                    with col3:

                        st.metric(
                            "Volgende",
                            next_occurrence,
                        )

                    # ----------------------------------------
                    # RELIABILITY
                    # ----------------------------------------

                    with col4:

                        st.metric(
                            "Betrouwbaarheid",
                            reliability,
                        )

                    # ----------------------------------------
                    # ACTIONS
                    # ----------------------------------------

                    c1, c2 = st.columns(2)

                    with c1:

                        if st.button(
                            "⏸️ Deactiveren",
                            key=(
                                f"deactivate_"
                                f"{recurring_id}"
                            ),
                            use_container_width=True,
                        ):

                            result = (
                                update_recurring_active(
                                    recurring_id,
                                    False,
                                )
                            )

                            if result is not None:

                                st.success(
                                    "Betaling gedeactiveerd."
                                )

                                st.rerun()

                    with c2:

                        if st.button(
                            "🗑️ Verwijderen",
                            key=(
                                f"delete_"
                                f"{recurring_id}"
                            ),
                            use_container_width=True,
                        ):

                            result = (
                                delete_recurring_transaction(
                                    recurring_id
                                )
                            )

                            if result is not None:

                                st.success(
                                    "Terugkerende betaling verwijderd."
                                )

                                st.rerun()

        else:

            st.info(
                "Er zijn momenteel geen actieve "
                "terugkerende betalingen."
            )

        # ----------------------------------------------------
        # INACTIVE RECURRING
        # ----------------------------------------------------

        if inactive:

            st.divider()

            with st.expander(
                "⏸️ Inactieve betalingen"
            ):

                for recurring in inactive:

                    recurring_id = recurring.get(
                        "id"
                    )

                    merchant = recurring.get(
                        "merchant",
                        "Onbekend",
                    )

                    category = recurring.get(
                        "category",
                        "Overig",
                    )

                    frequency = recurring.get(
                        "frequency",
                        "Onbekend",
                    )

                    amount = float(
                        recurring.get(
                            "expected_amount",
                            0,
                        )
                        or 0
                    )

                    with st.container(
                        border=True
                    ):

                        col1, col2, col3 = (
                            st.columns(
                                [
                                    3,
                                    2,
                                    2,
                                ]
                            )
                        )

                        with col1:

                            st.markdown(
                                f"**{str(merchant).title()}**"
                            )

                            st.caption(
                                f"{category} · "
                                f"{frequency}"
                            )

                        with col2:

                            st.metric(
                                "Bedrag",
                                euro(amount),
                            )

                        with col3:

                            if st.button(
                                "▶️ Activeren",
                                key=(
                                    f"activate_"
                                    f"{recurring_id}"
                                ),
                                use_container_width=True,
                            ):

                                result = (
                                    update_recurring_active(
                                        recurring_id,
                                        True,
                                    )
                                )

                                if result is not None:

                                    st.success(
                                        "Betaling geactiveerd."
                                    )

                                    st.rerun()

    else:

        st.info(
            "Nog geen terugkerende "
            "betalingen gevonden."
        )


# ============================================================
# CHAPTER 5 — BUDGETS
# ============================================================

elif chapter == "🎯 Budgetten":

    st.title("🎯 Budgetten")
    st.caption(
        "Voorstellen op basis van je eerdere uitgaven. Je kunt elk voorstel aanpassen "
        "en uitgaven indelen als maandelijks, periodiek of jaarlijks."
    )

    # Historical estimates use the 12 most recently completed months, so the
    # current partial month does not artificially lower the suggested budget.
    history = transaction_df.copy() if transaction_df is not None else pd.DataFrame()
    suggestions = []
    if not history.empty and "date" in history.columns:
        history["date"] = pd.to_datetime(history["date"], errors="coerce")
        history = history[history["date"].notna()].copy()
        if "flow" in history.columns:
            history = history[history["flow"] == "Uitgave"].copy()
        if "is_transfer" in history.columns:
            history = history[~history["is_transfer"].fillna(False)].copy()
        history["expense_amount"] = pd.to_numeric(history["amount"], errors="coerce").abs()
        history = history[history["expense_amount"].notna()]
        this_month = pd.Timestamp(date.today().replace(day=1))
        history_start = this_month - pd.DateOffset(months=36)
        history = history[(history["date"] >= history_start) & (history["date"] < this_month)]
        history_months_covered = 36
        if not history.empty:
            first_history_month = history["date"].min().to_period("M")
            history_months_covered = max(
                1,
                min(36, (this_month.to_period("M") - first_history_month).n),
            )

        if "category" not in history.columns:
            history["category"] = "Overig"
        history["category"] = history["category"].fillna("Overig")

        # Look back 36 months so annual and infrequent expenses aren't missed.
        # Monthly recommendations still use the latest 12 completed months.
        if not history.empty:
            history["month"] = history["date"].dt.to_period("M")
            monthly_totals = (
                history.groupby(["category", "month"])["expense_amount"]
                .sum().reset_index()
            )
            for category in sorted(history["category"].unique()):
                category_history = history[history["category"] == category]
                category_months = monthly_totals[monthly_totals["category"] == category]
                category_total = float(category_history["expense_amount"].sum())
                recent_start = this_month - pd.DateOffset(months=12)
                recent_total = float(
                    category_history.loc[category_history["date"] >= recent_start, "expense_amount"].sum()
                )
                monthly_average = recent_total / 12.0
                spending_month_count = int(category_history["month"].nunique())
                if category_total <= 0:
                    continue

                budget_type = "monthly"
                period_months = 1
                planned_amount = monthly_average if monthly_average > 0 else category_total / 36.0
                type_reason = (
                    "Gemiddelde per maand over de laatste 12 volledige maanden"
                    if monthly_average > 0
                    else "Spreiding van oudere uitgaven over 36 maanden; controleer dit voorstel"
                )

                # Where the user has already configured a recurring payment,
                # retain its real frequency and amount for the suggestion.
                matching = [
                    item for item in (saved_recurring or [])
                    if str(item.get("category", "")).strip() == str(category).strip()
                    and item.get("active", True)
                    and item.get("flow", "Uitgave") == "Uitgave"
                ]
                frequency_map = {
                    "wekelijks": ("monthly", 1),
                    "weekly": ("monthly", 1),
                    "maandelijks": ("monthly", 1),
                    "monthly": ("monthly", 1),
                    "per kwartaal": ("periodic", 3),
                    "quarterly": ("periodic", 3),
                    "halfjaarlijks": ("periodic", 6),
                    "semi-annually": ("periodic", 6),
                    "jaarlijks": ("annual", 12),
                    "yearly": ("annual", 12),
                    "annually": ("annual", 12),
                }
                for item in matching:
                    frequency = str(item.get("frequency", "")).lower()
                    if frequency in frequency_map:
                        budget_type, period_months = frequency_map[frequency]
                        planned_amount = float(item.get("expected_amount", 0) or 0)
                        if frequency in ("wekelijks", "weekly"):
                            planned_amount *= 52.0 / 12.0
                        type_reason = f"Gebaseerd op opgeslagen terugkerende betaling ({item.get('frequency')})"
                        break
                else:
                    # Sparse historical categories often represent annual or
                    # periodic bills. These are estimates, and remain editable.
                    if spending_month_count <= 3:
                        budget_type = "annual"
                        period_months = 12
                        observed_years = max(1.0, history_months_covered / 12.0)
                        planned_amount = category_total / observed_years
                        type_reason = "Schatting van jaarlijkse uitgaven op basis van de beschikbare historie (maximaal 36 maanden)"
                    elif spending_month_count <= 9:
                        budget_type = "periodic"
                        period_months = min(12, max(2, round(36 / spending_month_count)))
                        planned_amount = category_total / max(1, spending_month_count) * period_months
                        type_reason = f"Schatting van periodieke uitgaven; ongeveer elke {period_months} maanden"

                suggestions.append({
                    "category": str(category),
                    "planned_amount": max(0.0, float(planned_amount)),
                    "budget_type": budget_type,
                    "period_months": period_months,
                    "historical_total": category_total,
                    "monthly_average": monthly_average,
                    "reason": type_reason,
                })

    budgets = load_budgets(user_id)
    existing_by_category = {str(item.get("category")): item for item in budgets}
    suggestions = [item for item in suggestions if item["category"] not in existing_by_category]

    st.subheader("💡 Budgetvoorstellen op basis van je uitgaven")
    st.caption(
        "Maandgemiddelden gebruiken de laatste 12 volledige maanden; om jaarlijkse en onregelmatige "
        "uitgaven te herkennen kijken we tot 36 maanden terug. Periodieke frequenties worden overgenomen "
        "uit opgeslagen terugkerende betalingen als die beschikbaar zijn. Voorstellen zijn schattingen: "
        "controleer en wijzig ze voordat je ze opslaat."
    )

    if suggestions:
        suggestion_tabs = st.tabs(["Maandelijks", "Periodiek", "Jaarlijks"])
        type_details = [
            ("monthly", "Maandelijks"),
            ("periodic", "Periodiek"),
            ("annual", "Jaarlijks"),
        ]
        for tab, (type_value, type_label) in zip(suggestion_tabs, type_details):
            with tab:
                typed = [item for item in suggestions if item["budget_type"] == type_value]
                if not typed:
                    st.info("Geen voorstellen van dit type gevonden. Je kunt ook hieronder handmatig een budget toevoegen.")
                for item in typed:
                    with st.container(border=True):
                        left, middle, right = st.columns([2, 2, 1])
                        with left:
                            st.markdown(f"**{item['category']}**")
                            st.caption(item["reason"])
                            st.caption(f"Historisch uitgegeven in 12 maanden: {euro(item['historical_total'])}")
                        with middle:
                            unit = "per jaar" if type_value == "annual" else (
                                f"per {item['period_months']} maanden" if type_value == "periodic" else "per maand"
                            )
                            suggested_amount = st.number_input(
                                f"Voorstel ({unit})",
                                min_value=0.0,
                                value=round(float(item["planned_amount"]), 2),
                                step=10.0,
                                format="%.2f",
                                key=f"budget_suggest_amount_{item['category']}",
                            )
                        with right:
                            st.write("")
                            st.write("")
                            if st.button("Voorstel opslaan", key=f"budget_suggest_save_{item['category']}", use_container_width=True):
                                saved = save_budget(
                                    user_id, item["category"], suggested_amount,
                                    item["budget_type"], item["period_months"]
                                )
                                if saved is not None:
                                    st.success(f"Budget voor {item['category']} opgeslagen.")
                                    st.rerun()
    else:
        st.info(
            "Er zijn geen nieuwe voorstellen. Importeer meer transacties of pas bestaande budgetten hieronder aan."
        )

    with st.expander("➕ Zelf een budget toevoegen", expanded=not bool(budgets)):
        available_budget_categories = [
            c for c in CATEGORIES if c != "Inkomen" and c not in existing_by_category
        ]
        if not available_budget_categories:
            st.info("Alle beschikbare categorieën hebben al een budget. Pas een bestaand budget hierboven aan.")
        else:
            add_category = st.selectbox(
                "Categorie", available_budget_categories, key="budget_add_category",
            )
            add_type_label = st.selectbox(
                "Soort uitgave",
                ["Maandelijks", "Periodiek", "Jaarlijks"],
                key="budget_add_type",
            )
            add_type = {"Maandelijks": "monthly", "Periodiek": "periodic", "Jaarlijks": "annual"}[add_type_label]
            add_period_months = 1
            if add_type == "periodic":
                add_period_months = st.selectbox(
                    "Herhaling elke",
                    [2, 3, 4, 6, 9, 12],
                    format_func=lambda x: f"{x} maanden",
                    key="budget_add_period",
                )
            add_amount_label = "Bedrag per jaar" if add_type == "annual" else (
                "Bedrag per periode" if add_type == "periodic" else "Bedrag per maand"
            )
            add_amount = st.number_input(
                add_amount_label, min_value=0.0, step=10.0, value=100.0,
                format="%.2f", key="budget_add_amount",
            )
            if st.button("Budget toevoegen", type="primary", use_container_width=True, key="budget_add_save"):
                saved = save_budget(user_id, add_category, add_amount, add_type, add_period_months)
                if saved is not None:
                    st.success(f"Budget voor {add_category} opgeslagen.")
                    st.rerun()

    budgets = load_budgets(user_id)
    if budgets:
        st.subheader("✏️ Bestaande budgetten aanpassen")
        edit_tabs = st.tabs(["Maandelijks", "Periodiek", "Jaarlijks"])
        edit_types = [
            ("monthly", "Maandelijks"),
            ("periodic", "Periodiek"),
            ("annual", "Jaarlijks"),
        ]
        for tab, (type_value, type_label) in zip(edit_tabs, edit_types):
            with tab:
                typed_budgets = [
                    b for b in budgets
                    if str(b.get("budget_type", "monthly")) == type_value
                ]
                if not typed_budgets:
                    st.info("Nog geen budgetten in deze categorie.")
                for budget in typed_budgets:
                    category = str(budget.get("category", "Overig"))
                    with st.expander(category, expanded=False):
                        current_type = str(budget.get("budget_type", "monthly"))
                        current_months = int(budget.get("period_months", 1) or 1)
                        default_amount = float(
                            budget.get("planned_amount")
                            if budget.get("planned_amount") is not None
                            else budget.get("monthly_limit", 0) * (12 if current_type == "annual" else current_months)
                        )
                        with st.form(f"edit_budget_form_{category}"):
                            edited_type_label = st.selectbox(
                                "Soort uitgave",
                                ["Maandelijks", "Periodiek", "Jaarlijks"],
                                index={"monthly": 0, "periodic": 1, "annual": 2}.get(current_type, 0),
                                key=f"edit_budget_type_{category}",
                            )
                            edited_type = {"Maandelijks": "monthly", "Periodiek": "periodic", "Jaarlijks": "annual"}[edited_type_label]
                            edited_months = 1
                            if edited_type == "periodic":
                                choices = [2, 3, 4, 6, 9, 12]
                                selected_months = current_months if current_months in choices else 3
                                edited_months = st.selectbox(
                                    "Herhaling elke",
                                    choices,
                                    index=choices.index(selected_months),
                                    format_func=lambda x: f"{x} maanden",
                                    key=f"edit_budget_months_{category}",
                                )
                            label = "Bedrag per jaar" if edited_type == "annual" else (
                                "Bedrag per periode" if edited_type == "periodic" else "Bedrag per maand"
                            )
                            edited_amount = st.number_input(
                                label, min_value=0.0, value=round(default_amount, 2),
                                step=10.0, format="%.2f", key=f"edit_budget_amount_{category}",
                            )
                            submitted = st.form_submit_button("Wijzigingen opslaan", use_container_width=True)
                        if submitted:
                            saved = save_budget(user_id, category, edited_amount, edited_type, edited_months)
                            if saved is not None:
                                st.success(f"Budget voor {category} bijgewerkt.")
                                st.rerun()

        st.subheader("📊 Budget versus uitgaven")
        selected_period = month_selector(
            transaction_df, key="budget_period", months_forward=12, months_backward=12
        )
        budget_status = calculate_budget_status(transaction_df, budgets, selected_period)
        if selected_period > current_period():
            st.info("Dit is een toekomstige maand. De uitgaven zijn een voorspelling op basis van budgetten.")
        for budget in budget_status:
            category = budget["category"]
            budget_amount = budget["budget"]
            spent = budget["spent"]
            remaining = budget["remaining"]
            percentage = budget["percentage"]
            st.markdown(f"**{category}** — budget per maand: {euro(budget_amount)}")
            col1, col2, col3 = st.columns(3)
            col1.metric("Budget per maand (genormaliseerd)", euro(budget_amount))
            col2.metric("Uitgegeven deze maand", euro(spent))
            col3.metric("Resterend deze maand", euro(remaining))
            st.progress(min(max(percentage / 100, 0), 1))
            if budget["over_budget"]:
                st.error(f"Budget overschreden met {euro(abs(remaining))}")
            elif percentage >= 80:
                st.warning(f"{percentage:.0f}% van het maandbudget gebruikt.")
            else:
                st.success(f"{percentage:.0f}% van het maandbudget gebruikt.")
            st.divider()
    else:
        st.info("Je hebt nog geen budgetten ingesteld.")


# CHAPTER 6 — SETTINGS
# ============================================================

elif chapter == "📆 Jaaranalyse":

    st.title("📆 Jaaranalyse")
    st.caption("Vergelijk de drie meest recente volledige kalenderjaren. Het lopende jaar wordt apart getoond.")

    if transaction_df.empty:
        st.info("Er zijn nog geen transacties beschikbaar.")
    else:
        annual_df = transaction_df.copy()
        annual_df["date"] = pd.to_datetime(annual_df["date"], errors="coerce")
        annual_df = annual_df[annual_df["date"].notna()]
        # Keep the full set for separate transfer reporting, but exclude internal
        # transfers from all normal income/expense/net figures and category tables.
        annual_transfer_mask = is_transfer_series(annual_df)
        transfer_annual_df = annual_df.loc[annual_transfer_mask].copy()
        clean_annual_df = annual_df.loc[~annual_transfer_mask].copy()
        current_year = date.today().year
        full_years = [current_year - 3, current_year - 2, current_year - 1]
        all_years = full_years + [current_year]
        available_years = sorted(annual_df["date"].dt.year.unique().tolist())
        missing_years = [year for year in full_years if year not in available_years]
        if missing_years:
            st.warning("Voor deze volledige kalenderjaren zijn geen transacties gevonden: " + ", ".join(map(str, missing_years)) + ". Controleer of alle bankbestanden zijn geïmporteerd.")
        summary_rows = []
        for year in all_years:
            year_df = clean_annual_df[clean_annual_df["date"].dt.year == year]
            income_rows = year_df[year_df["flow"] == "Inkomst"].copy()
            income = float(income_rows["amount"].sum())
            expense_rows = year_df[year_df["flow"] == "Uitgave"].copy()
            expenses = float(expense_rows["amount"].abs().sum())
            summary_rows.append({
                "Jaar": year,
                "Periode": "Lopend jaar" if year == current_year else "Volledig kalenderjaar",
                "Inkomsten": income,
                "Uitgaven": expenses,
                "Netto": income - expenses,
                "Transacties": len(year_df),
                "Maanden met data": int(year_df["date"].dt.to_period("M").nunique()),
            })
        summary = pd.DataFrame(summary_rows)
        st.dataframe(
            summary.style.format({"Inkomsten": "€ {:,.2f}", "Uitgaven": "€ {:,.2f}", "Netto": "€ {:,.2f}"}),
            use_container_width=True,
            hide_index=True,
        )

        st.subheader("💶 Jaarlijkse inkomsten per bron")
        income_df = clean_annual_df[clean_annual_df["flow"] == "Inkomst"].copy()
        if not income_df.empty:
            income_df["Bedrag"] = pd.to_numeric(income_df["amount"], errors="coerce").abs()
            income_df["Bron"] = income_df.get("category", pd.Series("Overige inkomsten", index=income_df.index)).fillna("Overige inkomsten")
            income_descriptions = income_df.get("description", pd.Series("", index=income_df.index)).fillna("").astype(str)
            income_merchants = income_df.get("merchant", pd.Series("", index=income_df.index)).fillna("").astype(str)
            transfer_mask = (income_descriptions + " " + income_merchants).str.contains(
                r"overboeking|eigen rekening|spaarrekening|spaargeld|transfer from|overgemaakt van|interne overboeking",
                case=False, regex=True, na=False,
            )
            income_df.loc[transfer_mask, "Bron"] = "Overboeking spaargeld"
            if "is_transfer" in income_df.columns:
                income_df.loc[income_df["is_transfer"].fillna(False), "Bron"] = "Overboeking spaargeld"
            income_df = income_df[income_df["date"].dt.year.isin(all_years)]
            income_by_year = income_df.pivot_table(
                index="Bron", columns=income_df["date"].dt.year, values="Bedrag", aggfunc="sum", fill_value=0
            )
            income_by_year.columns = [str(year) for year in income_by_year.columns]
            st.dataframe(income_by_year.style.format("€ {:,.2f}"), use_container_width=True)
            st.caption("Overboekingen staan apart van salaris en andere inkomsten. Controleer de categorieën bij twijfel.")
        else:
            st.info("Geen inkomsten gevonden voor deze periode.")

        st.subheader("Uitgaven per categorie")
        expense_df = clean_annual_df[clean_annual_df["flow"] == "Uitgave"].copy()
        if not expense_df.empty:
            expense_df["Bedrag"] = expense_df["amount"].abs()
            category_year = expense_df[expense_df["date"].dt.year.isin(all_years)].pivot_table(
                index="category", columns=expense_df["date"].dt.year, values="Bedrag", aggfunc="sum", fill_value=0
            )
            category_year.columns = [str(c) for c in category_year.columns]
            st.dataframe(category_year.style.format("€ {:,.2f}"), use_container_width=True)
        else:
            st.info("Geen uitgaven gevonden voor de geselecteerde periode.")

        st.subheader("🔁 Jaarlijkse overboekingen spaargeld")
        if not transfer_annual_df.empty:
            transfer_annual_df = transfer_annual_df[transfer_annual_df["date"].dt.year.isin(all_years)].copy()
            transfer_annual_df["Bedrag"] = pd.to_numeric(transfer_annual_df["amount"], errors="coerce").abs()
            transfer_annual_df["Jaar"] = transfer_annual_df["date"].dt.year
            transfer_annual_df["Type"] = transfer_annual_df["flow"].map({
                "Inkomst": "Ontvangen",
                "Uitgave": "Verstuurd",
            }).fillna("Overboeking")
            transfer_summary = transfer_annual_df.pivot_table(
                index="Type", columns="Jaar", values="Bedrag", aggfunc="sum", fill_value=0
            )
            transfer_summary.columns = [str(year) for year in transfer_summary.columns]
            st.dataframe(transfer_summary.style.format("€ {:,.2f}"), use_container_width=True)
            transfer_details = transfer_annual_df.groupby(["Jaar", "Type"], dropna=False)["Bedrag"].sum().reset_index()
            st.caption("Deze bedragen worden apart getoond en tellen niet mee als inkomsten, uitgaven of nettoresultaat.")
        else:
            st.info("Geen overboekingen spaargeld herkend voor deze periode.")

        st.caption("Deze analyse gebruikt alle transacties die de app uit Supabase kan ophalen voor de geselecteerde rekeningweergave. Een ontbrekend jaar kan ook betekenen dat historische banktransacties nog niet zijn geïmporteerd.")


elif chapter == "💼 Vermogen & doelen":

    st.title("💼 Vermogen & spaardoelen")
    st.caption("Beheer actuele saldi, reserveer geld voor specifieke doelen en plan toekomstige grote uitgaven.")

    total_liquid = sum(float(a.get("current_balance") or 0) for a in accounts if a.get("is_liquid", True) and "beleg" not in str(a.get("account_type", "")).lower())
    total_investments = sum(float(a.get("current_balance") or 0) for a in accounts if "beleg" in str(a.get("account_type", "")).lower())
    col1, col2, col3 = st.columns(3)
    col1.metric("Totaal ingevoerde liquide middelen", euro(total_liquid))
    col2.metric("Beleggingsrekeningen (ingevoerd saldo)", euro(total_investments))
    col3.metric("Rekeningen", len(accounts))
    st.info("Vul saldi in via Instellingen → Actuele saldi. Beleggingswaarden zijn handmatig ingevoerd en geen live beurskoersen.")

    st.subheader("Rekeningen en bestemming")
    account_rows = []
    for account in accounts:
        account_rows.append({
            "Rekening": account.get("name", "Onbekend"),
            "Type": account.get("account_type", "Onbekend"),
            "Bank": account.get("bank", ""),
            "Saldo": float(account.get("current_balance") or 0),
            "Peildatum": account.get("balance_as_of") or "Niet ingevuld",
            "Bestemming": account.get("savings_purpose") or "Vrij beschikbaar / niet ingesteld",
        })
    st.dataframe(pd.DataFrame(account_rows), use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("Spaardoelen en grote toekomstige uitgaven")
    with st.form("new_financial_goal"):
        goal_name = st.text_input("Doel", placeholder="Bijv. auto, keuken, badkamer of noodreserve")
        goal_type = st.selectbox("Type", ["Spaardoel", "Grote uitgave", "Noodreserve", "Belegging"])
        goal_target = st.number_input("Doelbedrag (€)", min_value=0.0, step=500.0, value=5000.0)
        goal_current = st.number_input("Al gereserveerd (€)", min_value=0.0, step=100.0, value=0.0)
        goal_date = st.date_input("Gewenste datum", value=date(date.today().year + 1, date.today().month, min(date.today().day, 28)))
        goal_monthly = st.number_input("Maandelijkse inleg (€)", min_value=0.0, step=25.0, value=0.0)
        goal_notes = st.text_input("Notities (optioneel)")
        goal_submitted = st.form_submit_button("Spaardoel opslaan", type="primary")
    if goal_submitted:
        if not goal_name.strip():
            st.error("Geef het spaardoel een naam.")
        else:
            months_left = max(1, (goal_date.year - date.today().year) * 12 + goal_date.month - date.today().month)
            remaining_goal = max(0.0, goal_target - goal_current)
            monthly_suggested = remaining_goal / months_left
            result = save_financial_goal(user_id, {
                "name": goal_name.strip(),
                "goal_type": goal_type,
                "target_amount": float(goal_target),
                "current_amount": float(goal_current),
                "target_date": goal_date.isoformat(),
                "monthly_contribution": float(goal_monthly or monthly_suggested),
                "notes": goal_notes.strip() or None,
            })
            if result is not None:
                st.success("Spaardoel opgeslagen.")
                st.rerun()

    goals = load_financial_goals(user_id)
    if goals:
        for goal in goals:
            target = float(goal.get("target_amount") or 0)
            saved = float(goal.get("current_amount") or 0)
            remaining = max(0.0, target - saved)
            monthly = float(goal.get("monthly_contribution") or 0)
            st.markdown(f"**{goal.get('name')}** · {goal.get('goal_type', 'Spaardoel')}")
            st.progress(min(1.0, saved / target) if target > 0 else 0.0)
            c1, c2, c3 = st.columns(3)
            c1.metric("Doelbedrag", euro(target))
            c2.metric("Gereserveerd", euro(saved))
            c3.metric("Nog nodig", euro(remaining))
            target_date_value = goal.get("target_date")
            if target_date_value:
                st.caption(f"Doeldatum: {target_date_value} · Maandelijkse inleg: {euro(monthly)}")
            st.divider()
    else:
        st.info("Je hebt nog geen spaardoelen. Voeg hierboven bijvoorbeeld een auto, keuken of badkamer toe.")

    st.subheader("Budgetvoorstellen op basis van historie")
    st.caption("Voorstellen gebruiken de transacties die op dit moment in de applicatie beschikbaar zijn. Controleer de volledigheid van de historie voordat je een voorstel activeert.")
    if not transaction_df.empty:
        hist = transaction_df.copy()
        hist = hist[(hist["flow"] == "Uitgave") & (~hist.get("is_transfer", pd.Series(False, index=hist.index)).fillna(False))]
        if not hist.empty:
            hist["expense_amount"] = hist["amount"].abs()
            monthly_cat = hist.assign(month=hist["date"].dt.to_period("M")).groupby(["category", "month"])["expense_amount"].sum().reset_index()
            proposal_rows = []
            for category, group in monthly_cat.groupby("category"):
                # Include zero-spend months within the observed period for a fair monthly average.
                first_month = monthly_cat["month"].min()
                last_month = monthly_cat["month"].max()
                full_months = max(1, (last_month.year - first_month.year) * 12 + last_month.month - first_month.month + 1)
                avg = float(group["expense_amount"].sum()) / full_months
                proposal_rows.append({"Categorie": category, "Historisch gemiddeld p/m": round(avg, 2), "Voorgesteld budget p/m": round(avg, 2), "Maandbudget": round(avg * 12, 2)})
            proposal_df = pd.DataFrame(proposal_rows).sort_values("Historisch gemiddeld p/m", ascending=False)
            edited_proposals = st.data_editor(proposal_df, use_container_width=True, hide_index=True, disabled=["Categorie", "Historisch gemiddeld p/m", "Maandbudget"], key="budget_proposal_editor")
            proposal_period = st.selectbox("Periode waarvoor je voorstellen wilt opslaan", ["Maand", "Kwartaal", "Jaar"], key="proposal_period")
            if st.button("Voorstellen opslaan als conceptbudgetten", type="primary"):
                today = date.today()
                if proposal_period == "Maand":
                    period_start = today.replace(day=1)
                    period_end = (period_start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
                    period_type = "month"
                    factor = 1
                elif proposal_period == "Kwartaal":
                    quarter_month = ((today.month - 1) // 3) * 3 + 1
                    period_start = date(today.year, quarter_month, 1)
                    next_start_month = quarter_month + 3
                    next_start = date(today.year + (next_start_month - 1) // 12, (next_start_month - 1) % 12 + 1, 1)
                    period_end = next_start - timedelta(days=1)
                    period_type = "quarter"
                    factor = 3
                else:
                    period_start = date(today.year, 1, 1)
                    period_end = date(today.year, 12, 31)
                    period_type = "year"
                    factor = 12
                saved_count = 0
                for _, row in edited_proposals.iterrows():
                    amount = float(row["Voorgesteld budget p/m"]) * factor
                    result = save_budget_plan(user_id, {
                        "category": str(row["Categorie"]),
                        "period_type": period_type,
                        "period_start": period_start.isoformat(),
                        "period_end": period_end.isoformat(),
                        "amount": amount,
                        "status": "draft",
                        "source": "historical_average",
                    })
                    if result is not None:
                        saved_count += 1
                st.success(f"{saved_count} conceptbudgetten opgeslagen. Deze vervangen je bestaande maandbudgetten niet automatisch.")
                st.rerun()
        else:
            st.info("Geen uitgavetransacties beschikbaar om budgetvoorstellen te berekenen.")
    else:
        st.info("Importeer transacties om historische budgetvoorstellen te berekenen.")

    existing_plans = load_budget_plans(user_id)
    if existing_plans:
        st.subheader("Opgeslagen periodebudgetten")
        st.dataframe(pd.DataFrame([{
            "Categorie": p.get("category"),
            "Periode": f"{p.get('period_start')} t/m {p.get('period_end')}",
            "Type": p.get("period_type"),
            "Bedrag": float(p.get("amount") or 0),
            "Status": p.get("status"),
            "Bron": p.get("source"),
        } for p in existing_plans]), use_container_width=True, hide_index=True)

elif chapter == "⚙️ Instellingen":

    st.title(
        "⚙️ Instellingen"
    )

    st.subheader(
        "🏦 Mijn rekeningen"
    )

    for account in accounts:

        with st.container(
            border=True
        ):

            col1, col2, col3 = (
                st.columns(
                    [
                        3,
                        2,
                        2,
                    ]
                )
            )

            with col1:

                st.markdown(
                    f"**{account.get('name', 'Onbekend')}**"
                )

            with col2:

                st.write(
                    account.get(
                        "bank",
                        "-",
                    )
                )

            with col3:

                st.write(
                    account.get(
                        "account_type",
                        "-",
                    )
                )

    st.divider()

    st.subheader("💶 Actuele saldi")
    st.caption("Voer per rekening het saldo en de peildatum in. Dit wordt gebruikt voor het actuele vermogensoverzicht; het saldo wordt niet bij historische inkomsten opgeteld.")

    for account in accounts:
        with st.container(border=True):
            st.markdown(f"**{account.get('name', 'Rekening')}**")
            current_balance = account.get("current_balance")
            with st.form(f"balance_{account['id']}"):
                balance_value = st.number_input(
                    "Huidig saldo (€)",
                    value=float(current_balance or 0),
                    step=50.0,
                    format="%.2f",
                    key=f"balance_value_{account['id']}",
                )
                balance_date_value = st.date_input(
                    "Saldo per",
                    value=pd.to_datetime(account.get("balance_as_of") or date.today()).date(),
                    key=f"balance_date_{account['id']}",
                )
                purpose_value = st.text_input(
                    "Bestemming / spaardoel (optioneel)",
                    value=account.get("savings_purpose") or "",
                    key=f"purpose_{account['id']}",
                )
                balance_saved = st.form_submit_button("Saldo opslaan")
            if balance_saved:
                try:
                    supabase.table("accounts").update({
                        "current_balance": float(balance_value),
                        "balance_as_of": balance_date_value.isoformat(),
                        "savings_purpose": purpose_value.strip() or None,
                    }).eq("id", account["id"]).eq("user_id", user_id).execute()
                    st.success("Saldo bijgewerkt.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Saldo kon niet worden opgeslagen. Voer eerst de SQL-migratie uit: {e}")

    st.divider()

    st.subheader(
        "👤 Account"
    )

    st.write(
        f"**E-mailadres:** {user.email}"
    )

    st.divider()

    st.subheader(
        "📅 Datum"
    )

    st.write(
        f"Vandaag is "
        f"**{today().strftime('%d-%m-%Y')}**."
    )

    st.caption(
        "De datum wordt automatisch iedere "
        "dag opnieuw bepaald."
    )

    st.divider()

    st.subheader(
        "🏷️ Categorieën"
    )

    st.write(
        "Financial Cockpit gebruikt automatische "
        "regels om transacties te categoriseren."
    )

    st.write(
        f"Er zijn momenteel "
        f"{len(CATEGORIES)} categorieën."
    )

    st.divider()

    st.caption(
        "Financial Cockpit"
    )
