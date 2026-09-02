import io
import hashlib
from datetime import date

import pandas as pd
import streamlit as st
from supabase import create_client

from categorization import (
    CATEGORIES,
    EXPENSE_CATEGORIES,
)

from database import Database

from ui_helpers import (
    euro,
    without_transfers,
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
):

    merchant = (
        str(merchant)
        .strip()
        .lower()
    )

    try:

        result = (
            supabase
            .table("transactions")
            .update(
                {
                    "category": category
                }
            )
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


def load_transactions(
    user_id,
    account_id,
):

    try:

        result = (
            supabase
            .table("transactions")
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
                "date",
                desc=True,
            )
            .execute()
        )

        return result.data or []

    except Exception as e:

        st.error(
            f"❌ Transacties konden niet "
            f"worden geladen: {e}"
        )

        return []


def load_all_transactions(
    user_id,
):

    try:

        result = (
            supabase
            .table("transactions")
            .select("*")
            .eq(
                "user_id",
                user_id,
            )
            .order(
                "date",
                desc=True,
            )
            .execute()
        )

        return result.data or []

    except Exception as e:

        st.error(
            f"❌ Alle transacties konden niet "
            f"worden geladen: {e}"
        )

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
    monthly_limit,
):

    try:

        result = (
            supabase
            .table("budgets")
            .upsert(
                {
                    "user_id": user_id,
                    "category": category,
                    "monthly_limit":
                        float(
                            monthly_limit
                        ),
                },
                on_conflict=(
                    "user_id,category"
                ),
            )
            .execute()
        )

        return result.data

    except Exception as e:

        st.error(
            f"❌ Budget kon niet "
            f"worden opgeslagen: {e}"
        )

        return None


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
):

    text = (
        f"{description} "
        f"{merchant}"
    ).lower()

    # Eigen regels eerst
    for rule_merchant, category in (
        merchant_rules or {}
    ).items():

        if (
            str(rule_merchant).lower()
            in text
        ):
            return category

    category_rules = {

        "Boodschappen": [
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
            "supermarkt",
        ],

        "Telecom": [
            "ziggo",
            "odido",
            "t-mobile",
            "tmobile",
            "kpn",
            "vodafone",
            "tele2",
            "simyo",
        ],

        "Vervoer": [
            "shell",
            "esso",
            "bp",
            "total",
            "texaco",
            "anwb",
            "q-park",
            "parkmobile",
            "uber",
            "bolt",
            "ov-chipkaart",
            "ns ",
        ],

        "Horeca": [
            "restaurant",
            "cafe",
            "café",
            "mcdonald",
            "burger king",
            "starbucks",
            "thuisbezorgd",
            "uber eats",
            "deliveroo",
        ],

        "Entertainment": [
            "netflix",
            "spotify",
            "disney",
            "prime video",
            "pathe",
            "bioscoop",
            "youtube",
            "apple music",
        ],

        "Abonnementen": [
            "subscription",
            "membership",
            "abonnement",
        ],

        "Wonen": [
            "vattenfall",
            "essent",
            "eneco",
            "huur",
            "hypotheek",
            "waternet",
        ],

        "Verzekeringen": [
            "verzekering",
            "achmea",
            "interpolis",
            "ohra",
            "aegon",
        ],

        "Gezondheid": [
            "apotheek",
            "ziekenhuis",
            "tandarts",
            "dokter",
            "huisarts",
        ],

        "Kleding": [
            "zara",
            "h&m",
            "uniqlo",
            "nike",
            "adidas",
        ],

        "Persoonlijke verzorging": [
            "kapper",
            "barber",
            "rituals",
            "douglas",
            "ici paris",
        ],

        "Kinderen": [
            "school",
            "kinderopvang",
            "creche",
            "crèche",
            "kinderdagverblijf",
        ],

        "Vakantie": [
            "booking.com",
            "airbnb",
            "hotel",
            "camping",
        ],

        "Inkomen": [
            "salaris",
            "salary",
            "loon",
        ],
    }

    for category, keywords in (
        category_rules.items()
    ):

        for keyword in keywords:

            if keyword in text:
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

            expense_df = month_df[
                month_df["flow"]
                == "Uitgave"
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

        col1, col2, col3 = (
            st.columns(3)
        )

        with col1:

            st.metric(
                "Transacties",
                len(transaction_display),
            )

        with col2:

            expenses = (
                transaction_display[
                    transaction_display[
                        "flow"
                    ]
                    == "Uitgave"
                ]["amount"]
                .abs()
                .sum()
            )

            st.metric(
                "Uitgaven",
                euro(expenses),
            )

        with col3:

            income = (
                transaction_display[
                    transaction_display[
                        "flow"
                    ]
                    == "Inkomst"
                ]["amount"]
                .sum()
            )

            st.metric(
                "Inkomsten",
                euro(income),
            )

        st.subheader(
            "Alle transacties"
        )

        display_columns = [
            "date",
            "description",
            "merchant",
            "amount",
            "flow",
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
        "Categoriseer je uitgaven eenvoudig "
        "per winkel of organisatie."
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

    expenses = df[
        df["flow"]
        == "Uitgave"
    ].copy()

    if expenses.empty:

        st.info(
            "Geen uitgaven gevonden."
        )

        st.stop()

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
        [3, 1.5]
    )

    with col1:

        search = st.text_input(
            "🔎 Zoek winkel of organisatie",
            placeholder="Bijvoorbeeld Albert Heijn",
        )

    with col2:

        only_rules = st.checkbox(
            "Alleen mijn regels"
        )

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

    if only_rules:

        merchant_summary = (
            merchant_summary[
                merchant_summary[
                    "merchant"
                ]
                .astype(str)
                .str.lower()
                .isin(
                    merchant_category_rules.keys()
                )
            ]
        )

    st.subheader(
        "🏪 Winkels & organisaties"
    )

    for index, row in (
        merchant_summary
        .reset_index(drop=True)
        .iterrows()
    ):

        merchant = (
            str(row["merchant"])
            .strip()
            .lower()
        )

        current_category = str(
            row[
                "current_category"
            ]
        )

        total = abs(
            float(
                row["total"]
            )
        )

        count = int(
            row["transactions"]
        )

        rule_exists = (
            merchant
            in merchant_category_rules
        )

        with st.container(
            border=True
        ):

            col1, col2, col3, col4 = (
                st.columns(
                    [
                        3,
                        1.5,
                        2,
                        1.8,
                    ]
                )
            )

            with col1:

                st.markdown(
                    f"**{merchant.title()}**"
                )

                rule_label = (
                    " · vaste regel"
                    if rule_exists
                    else ""
                )

                st.caption(
                    f"{count} transacties · "
                    f"{euro(total)}"
                    f"{rule_label}"
                )

            with col2:

                st.caption(
                    "Huidige categorie"
                )

                st.write(
                    current_category
                )

            with col3:

                category_options = [
                    category
                    for category
                    in CATEGORIES
                    if category
                    != "Inkomen"
                ]

                new_category = (
                    st.selectbox(
                        "Nieuwe categorie",
                        category_options,
                        index=(
                            category_options.index(
                                current_category
                            )
                            if current_category
                            in category_options
                            else category_options.index(
                                "Overig"
                            )
                        ),
                        key=(
                            f"category_"
                            f"{index}_"
                            f"{merchant}"
                        ),
                        label_visibility=(
                            "collapsed"
                        ),
                    )
                )

            with col4:

                if st.button(
                    "💾 Toepassen",
                    key=(
                        f"save_category_"
                        f"{index}_"
                        f"{merchant}"
                    ),
                    use_container_width=True,
                    type="primary",
                ):

                    saved = (
                        save_merchant_category_rule(
                            user_id,
                            merchant,
                            new_category,
                        )
                    )

                    if saved is not None:

                        updated = (
                            update_transactions_for_merchant(
                                user_id,
                                merchant,
                                new_category,
                            )
                        )

                        if updated is not None:

                            st.success(
                                f"✅ "
                                f"{merchant.title()} "
                                f"→ {new_category}."
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

    st.title(
        "🎯 Budgetten"
    )

    st.caption(
        "Stel per categorie een maximaal "
        "bedrag per maand in."
    )

    with st.expander(
        "➕ Budget instellen"
    ):

        budget_category = (
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

        budget_amount = (
            st.number_input(
                "Maandelijks budget",
                min_value=0.0,
                step=25.0,
                value=250.0,
                format="%.2f",
            )
        )

        if st.button(
            "💾 Budget opslaan",
            type="primary",
            use_container_width=True,
        ):

            result = save_budget(
                user_id,
                budget_category,
                budget_amount,
            )

            if result is not None:

                st.success(
                    f"✅ Budget voor "
                    f"{budget_category} opgeslagen."
                )

                st.rerun()

    budgets = load_budgets(
        user_id
    )

    if budgets:

        # NIEUW:
        # toekomstige maanden zijn ook selecteerbaar

        selected_period = month_selector(
            transaction_df,
            key="budget_period",
            months_forward=12,
            months_backward=12,
        )

        budget_status = (
            calculate_budget_status(
                transaction_df,
                budgets,
                selected_period,
            )
        )

        if (
            selected_period
            > current_period()
        ):

            st.info(
                "📅 Dit is een toekomstige maand. "
                "Er zijn nog geen werkelijke uitgaven. "
                "De budgetten staan alvast klaar."
            )

        for budget in budget_status:

            category = (
                budget["category"]
            )

            budget_amount = (
                budget["budget"]
            )

            spent = (
                budget["spent"]
            )

            remaining = (
                budget["remaining"]
            )

            percentage = (
                budget["percentage"]
            )

            st.subheader(
                category
            )

            col1, col2, col3 = (
                st.columns(3)
            )

            with col1:

                st.metric(
                    "Budget",
                    euro(budget_amount),
                )

            with col2:

                st.metric(
                    "Uitgegeven",
                    euro(spent),
                )

            with col3:

                st.metric(
                    "Resterend",
                    euro(remaining),
                )

            progress = min(
                max(
                    percentage / 100,
                    0,
                ),
                1,
            )

            st.progress(
                progress
            )

            if budget[
                "over_budget"
            ]:

                st.error(
                    f"🔴 Budget overschreden "
                    f"met "
                    f"{euro(abs(remaining))}"
                )

            elif percentage >= 80:

                st.warning(
                    f"🟠 "
                    f"{percentage:.0f}% gebruikt."
                )

            else:

                st.success(
                    f"🟢 "
                    f"{percentage:.0f}% gebruikt."
                )

            st.divider()

    else:

        st.info(
            "Je hebt nog geen budgetten ingesteld."
        )


# ============================================================
# CHAPTER 6 — SETTINGS
# ============================================================

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
