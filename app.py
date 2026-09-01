import streamlit as st
import pandas as pd
import hashlib
import re
from datetime import date, datetime
from calendar import monthrange

from supabase import create_client, Client

from financial_engine import (
    prepare_transactions,
    detect_transfer_transactions,
    calculate_monthly_metrics,
    calculate_category_spending,
    calculate_month_forecast,
    calculate_budget_status,
    calculate_financial_health,
    calculate_safe_to_spend,
    calculate_monthly_recurring_cost,
    calculate_monthly_recurring_income,
)


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="Financial Cockpit",
    page_icon="💶",
    layout="wide",
)


# ============================================================
# CONSTANTS
# ============================================================

INCOME_CATEGORIES = [
    "Salaris",
    "Belasting",
    "Rente",
    "Overboeking spaargeld",
    "Tikkies",
    "Overige inkomsten",
]

EXPENSE_CATEGORIES = [
    "Boodschappen",
    "Wonen",
    "Telecom",
    "Vervoer",
    "Horeca",
    "Entertainment",
    "Abonnementen",
    "Gezondheid",
    "Verzekeringen",
    "Kinderen",
    "Vakantie",
    "Kleding",
    "Persoonlijke verzorging",
    "Belastingen",
    "Overboekingen",
    "Overig",
]

CATEGORIES = INCOME_CATEGORIES + EXPENSE_CATEGORIES


# ============================================================
# AUTOMATIC CATEGORY RULES
# ============================================================

CATEGORY_RULES = {

    # --------------------------------------------------------
    # INCOME
    # --------------------------------------------------------

    "Salaris": [
        "salaris",
        "loon",
        "salary",
        "payroll",
        "wage",
    ],

    "Belasting": [
        "belastingdienst",
        "belasting terug",
        "teruggave belasting",
        "inkomstenbelasting",
        "toeslag",
        "zorgtoeslag",
        "kinderopvangtoeslag",
        "huurtoeslag",
    ],

    "Rente": [
        "rente",
        "interest",
        "spaarrente",
        "deposito rente",
    ],

    "Overboeking spaargeld": [
        "spaarrekening",
        "sparen",
        "spaargeld",
        "overboeking sparen",
        "overboeking spaargeld",
    ],

    "Tikkies": [
        "tikkie",
        "tikkies",
        "betaalverzoek",
        "betaalverzoeken",
    ],

    "Overige inkomsten": [
        "vergoeding",
        "uitbetaling",
        "ontvangst",
        "terugbetaling",
        "refund",
        "cashback",
    ],

    # --------------------------------------------------------
    # EXPENSES
    # --------------------------------------------------------

    "Boodschappen": [
        "albert heijn",
        "albert heijn",
        "ah ",
        "jumbo",
        "lidl",
        "aldi",
        "plus ",
        "dirk",
        "hoogvliet",
        "vomar",
        "coop",
        "picnic",
        "spar ",
        "ekoplaza",
    ],

    "Wonen": [
        "hypotheek",
        "huur",
        "energie",
        "water",
        "vitens",
        "essent",
        "vandebron",
        "eneco",
        "nuon",
        "liander",
        "stedin",
        "woning",
    ],

    "Telecom": [
        "kpn",
        "vodafone",
        "ziggo",
        "t-mobile",
        "odido",
        "tele2",
        "youfone",
        "simyo",
    ],

    "Vervoer": [
        "shell",
        "bp ",
        "esso",
        "total",
        "q8",
        "tinq",
        "parking",
        "parkeren",
        "ns ",
        "ov-chipkaart",
        "ovpay",
        "uber",
        "bolt",
        "taxi",
    ],

    "Horeca": [
        "restaurant",
        "cafe",
        "café",
        "mcdonald",
        "starbucks",
        "burger king",
        "kfc",
        "thuisbezorgd",
        "uber eats",
        "deliveroo",
    ],

    "Entertainment": [
        "spotify",
        "netflix",
        "pathe",
        "pathé",
        "bioscoop",
        "steam",
        "playstation",
        "xbox",
        "nintendo",
        "ticketmaster",
    ],

    "Abonnementen": [
        "subscription",
        "abonnement",
        "amazon prime",
        "disney",
        "disney+",
        "apple.com/bill",
        "icloud",
        "microsoft",
        "google one",
        "dropbox",
    ],

    "Gezondheid": [
        "apotheek",
        "huisarts",
        "ziekenhuis",
        "tandarts",
        "fysio",
        "fysiotherapie",
        "oogarts",
        "medisch",
    ],

    "Verzekeringen": [
        "verzekering",
        "verzekeringen",
        "achmea",
        "aegon",
        "interpolis",
        "cz ",
        "zilveren kruis",
        "vgz",
        "menzis",
    ],

    "Kinderen": [
        "kinderopvang",
        "kinderopvangtoeslag",
        "school",
        "bso",
        "crèche",
        "creche",
        "kinderdagverblijf",
        "peuterspeelzaal",
    ],

    "Vakantie": [
        "booking.com",
        "airbnb",
        "hotel",
        "vakantie",
        "transavia",
        "klm",
        "ryanair",
        "easyjet",
        "sunweb",
    ],

    "Kleding": [
        "zara",
        "h&m",
        "uniqlo",
        "zalando",
        "we fashion",
        "about you",
        "primark",
        "nike",
        "adidas",
    ],

    "Persoonlijke verzorging": [
        "rituals",
        "kapper",
        "kapsalon",
        "douglas",
        "ici paris",
        "ici paris xl",
        "parfumerie",
    ],

    "Belastingen": [
        "gemeentebelasting",
        "waterschap",
        "belasting",
        "motorrijtuigenbelasting",
        "wegenbelasting",
    ],

    "Overboekingen": [
        "overboeking",
        "overschrijving",
        "transfer",
    ],
}


# ============================================================
# SUPABASE
# ============================================================

@st.cache_resource
def get_supabase() -> Client:
    return create_client(
        st.secrets["SUPABASE_URL"],
        st.secrets["SUPABASE_KEY"],
    )


supabase = get_supabase()


# ============================================================
# SESSION STATE
# ============================================================

if "user" not in st.session_state:
    st.session_state.user = None

if "session" not in st.session_state:
    st.session_state.session = None


# ============================================================
# HELPERS
# ============================================================

def euro(value):
    """Format number as Dutch euro amount."""

    if value is None:
        return "€ 0,00"

    try:
        value = float(value)
    except (ValueError, TypeError):
        return "€ 0,00"

    return f"€ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def safe_float(value, default=0.0):
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def normalize_merchant(value):
    """Normalize merchant name."""

    if value is None:
        return ""

    value = str(value).strip().lower()

    value = re.sub(r"\s+", " ", value)

    return value


def create_transaction_hash(transaction_date, description, amount):
    """Create deterministic transaction hash."""

    raw = (
        f"{transaction_date}|"
        f"{str(description).strip().lower()}|"
        f"{float(amount):.2f}"
    )

    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def categorize_transaction(description, amount, flow):
    """
    Automatically categorize a transaction.

    Income is categorized exclusively into:
    Salaris
    Belasting
    Rente
    Overboeking spaargeld
    Tikkies
    Overige inkomsten
    """

    text = str(description or "").lower()

    # --------------------------------------------------------
    # INCOME
    # --------------------------------------------------------

    if flow == "Inkomst":

        for category in INCOME_CATEGORIES:
            keywords = CATEGORY_RULES.get(category, [])

            for keyword in keywords:
                if keyword.lower() in text:
                    return category

        return "Overige inkomsten"

    # --------------------------------------------------------
    # EXPENSE
    # --------------------------------------------------------

    for category in EXPENSE_CATEGORIES:

        keywords = CATEGORY_RULES.get(category, [])

        for keyword in keywords:

            if keyword.lower() in text:
                return category

    return "Overig"


def is_transfer_dataframe(df):
    """
    Returns boolean Series identifying transfer transactions.

    Supports both:
    - is_transfer column
    - transaction_type = transfer / overboeking
    """

    result = pd.Series(False, index=df.index)

    if "is_transfer" in df.columns:
        result = (
            df["is_transfer"]
            .fillna(False)
            .astype(bool)
        )

    if "transaction_type" in df.columns:

        transaction_type = (
            df["transaction_type"]
            .fillna("")
            .astype(str)
            .str.lower()
        )

        result = result | transaction_type.isin([
            "transfer",
            "overboeking",
            "overboekingen",
        ])

    return result


def format_period(period):
    """Return Dutch month/year."""

    months = {
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

    if hasattr(period, "month"):

        return f"{months[period.month]} {period.year}"

    return str(period)


# ============================================================
# DATABASE — MERCHANT CATEGORY RULES
# ============================================================

def load_merchant_category_rules(user_id):

    result = (
        supabase
        .table("merchant_category_rules")
        .select("*")
        .eq("user_id", user_id)
        .order("merchant")
        .execute()
    )

    return result.data or []


def save_merchant_category_rule(user_id, merchant, category):

    merchant = normalize_merchant(merchant)

    if not merchant:
        return

    (
        supabase
        .table("merchant_category_rules")
        .upsert(
            {
                "user_id": user_id,
                "merchant": merchant,
                "category": category,
                "updated_at": datetime.utcnow().isoformat(),
            },
            on_conflict="user_id,merchant",
        )
        .execute()
    )


def delete_merchant_category_rule(user_id, merchant):

    (
        supabase
        .table("merchant_category_rules")
        .delete()
        .eq("user_id", user_id)
        .eq("merchant", merchant)
        .execute()
    )


def update_transactions_for_merchant(
    user_id,
    merchant,
    category,
):

    transactions = (
        supabase
        .table("transactions")
        .select("id, merchant")
        .eq("user_id", user_id)
        .execute()
    )

    rows = transactions.data or []

    for row in rows:

        if normalize_merchant(row.get("merchant")) == normalize_merchant(merchant):

            (
                supabase
                .table("transactions")
                .update({"category": category})
                .eq("id", row["id"])
                .eq("user_id", user_id)
                .execute()
            )


# ============================================================
# DATABASE — ACCOUNTS
# ============================================================

def load_accounts(user_id):

    result = (
        supabase
        .table("accounts")
        .select("*")
        .eq("user_id", user_id)
        .order("name")
        .execute()
    )

    return result.data or []


def create_account(user_id, name, bank, account_type):

    (
        supabase
        .table("accounts")
        .insert(
            {
                "user_id": user_id,
                "name": name,
                "bank": bank,
                "account_type": account_type,
            }
        )
        .execute()
    )


# ============================================================
# DATABASE — TRANSACTIONS
# ============================================================

def load_transactions(user_id, account_id):

    result = (
        supabase
        .table("transactions")
        .select("*")
        .eq("user_id", user_id)
        .eq("account_id", account_id)
        .order("date", desc=True)
        .execute()
    )

    return result.data or []


def load_all_transactions(user_id):

    result = (
        supabase
        .table("transactions")
        .select("*")
        .eq("user_id", user_id)
        .order("date", desc=True)
        .execute()
    )

    return result.data or []


# ============================================================
# DATABASE — BUDGETS
# ============================================================

def load_budgets(user_id):

    result = (
        supabase
        .table("budgets")
        .select("*")
        .eq("user_id", user_id)
        .order("category")
        .execute()
    )

    return result.data or []


def save_budget(user_id, category, monthly_limit):

    (
        supabase
        .table("budgets")
        .upsert(
            {
                "user_id": user_id,
                "category": category,
                "monthly_limit": monthly_limit,
            },
            on_conflict="user_id,category",
        )
        .execute()
    )


# ============================================================
# DATABASE — RECURRING
# ============================================================

def load_recurring_transactions(user_id, account_id):

    result = (
        supabase
        .table("recurring_transactions")
        .select("*")
        .eq("user_id", user_id)
        .eq("account_id", account_id)
        .order("next_occurrence")
        .execute()
    )

    return result.data or []


def load_all_recurring_transactions(user_id):

    result = (
        supabase
        .table("recurring_transactions")
        .select("*")
        .eq("user_id", user_id)
        .order("next_occurrence")
        .execute()
    )

    return result.data or []


def save_recurring_transactions(user_id, account_id, rows):

    for row in rows:

        data = {
            "user_id": user_id,
            "account_id": account_id,
            "merchant": row.get("merchant"),
            "category": row.get("category"),
            "frequency": row.get("frequency", "monthly"),
            "expected_amount": row.get("expected_amount"),
            "last_occurrence": row.get("last_occurrence"),
            "next_occurrence": row.get("next_occurrence"),
            "active": row.get("active", True),
            "flow": row.get("flow", "Uitgave"),
        }

        (
            supabase
            .table("recurring_transactions")
            .insert(data)
            .execute()
        )


def update_recurring_active(user_id, recurring_id, active):

    (
        supabase
        .table("recurring_transactions")
        .update({"active": active})
        .eq("id", recurring_id)
        .eq("user_id", user_id)
        .execute()
    )


def delete_recurring_transaction(user_id, recurring_id):

    (
        supabase
        .table("recurring_transactions")
        .delete()
        .eq("id", recurring_id)
        .eq("user_id", user_id)
        .execute()
    )


# ============================================================
# RECURRING DETECTION
# ============================================================

def detect_recurring_transactions(df):

    if df.empty:
        return []

    expenses = df[
        (df["flow"] == "Uitgave")
        & (~is_transfer_dataframe(df))
    ].copy()

    if expenses.empty:
        return []

    expenses["date"] = pd.to_datetime(
        expenses["date"],
        errors="coerce",
    )

    expenses = expenses.dropna(subset=["date"])

    if "merchant" not in expenses.columns:
        expenses["merchant"] = expenses["description"]

    recurring = []

    for merchant, group in expenses.groupby("merchant"):

        if len(group) < 3:
            continue

        group = group.sort_values("date")

        dates = group["date"].tolist()

        intervals = [
            (dates[i] - dates[i - 1]).days
            for i in range(1, len(dates))
        ]

        if not intervals:
            continue

        avg_interval = sum(intervals) / len(intervals)

        if 25 <= avg_interval <= 35:
            frequency = "monthly"

        elif 6 <= avg_interval <= 8:
            frequency = "weekly"

        elif 80 <= avg_interval <= 100:
            frequency = "quarterly"

        else:
            continue

        last_row = group.iloc[-1]

        recurring.append(
            {
                "merchant": merchant,
                "category": last_row.get("category"),
                "frequency": frequency,
                "expected_amount": abs(
                    safe_float(last_row.get("amount"))
                ),
                "last_occurrence": (
                    last_row["date"].date().isoformat()
                ),
                "next_occurrence": None,
                "active": True,
                "flow": "Uitgave",
            }
        )

    return recurring


# ============================================================
# AUTHENTICATION
# ============================================================

def login():

    st.title("💶 Financial Cockpit")

    st.subheader("Inloggen")

    email = st.text_input("E-mailadres")

    password = st.text_input(
        "Wachtwoord",
        type="password",
    )

    col1, col2 = st.columns(2)

    with col1:

        if st.button(
            "Inloggen",
            use_container_width=True,
        ):

            try:

                response = supabase.auth.sign_in_with_password(
                    {
                        "email": email,
                        "password": password,
                    }
                )

                st.session_state.user = response.user
                st.session_state.session = response.session

                st.rerun()

            except Exception as e:

                st.error(
                    f"Inloggen mislukt: {e}"
                )

    with col2:

        if st.button(
            "Account aanmaken",
            use_container_width=True,
        ):

            try:

                response = supabase.auth.sign_up(
                    {
                        "email": email,
                        "password": password,
                    }
                )

                st.success(
                    "Account aangemaakt. "
                    "Controleer eventueel je e-mail."
                )

            except Exception as e:

                st.error(
                    f"Registreren mislukt: {e}"
                )


if st.session_state.user is None:

    login()

    st.stop()


# ============================================================
# USER
# ============================================================

user_id = st.session_state.user.id


# ============================================================
# ACCOUNTS
# ============================================================

accounts = load_accounts(user_id)


if not accounts:

    st.title("💶 Financial Cockpit")

    st.info(
        "Je hebt nog geen bankrekening toegevoegd."
    )

    with st.form("first_account"):

        name = st.text_input(
            "Naam rekening",
            placeholder="Privérekening",
        )

        bank = st.text_input(
            "Bank",
            placeholder="ING",
        )

        account_type = st.selectbox(
            "Type",
            [
                "checking",
                "savings",
                "credit",
                "other",
            ],
        )

        submitted = st.form_submit_button(
            "Rekening toevoegen"
        )

        if submitted:

            if not name:

                st.error(
                    "Vul een naam voor de rekening in."
                )

            else:

                try:

                    create_account(
                        user_id,
                        name,
                        bank,
                        account_type,
                    )

                    st.success(
                        "Rekening toegevoegd."
                    )

                    st.rerun()

                except Exception as e:

                    st.error(
                        f"Opslaan mislukt: {e}"
                    )

    st.stop()


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.title("💶 Financial Cockpit")

account_options = {
    "Alle rekeningen": None
}

for account in accounts:

    account_options[
        account["name"]
    ] = account["id"]


selected_account_name = st.sidebar.selectbox(
    "Rekening",
    list(account_options.keys()),
)

selected_account_id = account_options[
    selected_account_name
]


chapter = st.sidebar.radio(
    "Navigatie",
    [
        "Overzicht",
        "Transacties",
        "Categorieën",
        "Terugkerend",
        "Budgetten",
        "Instellingen",
    ],
)


if st.sidebar.button("Uitloggen"):

    try:
        supabase.auth.sign_out()
    except Exception:
        pass

    st.session_state.user = None
    st.session_state.session = None

    st.rerun()


# ============================================================
# LOAD DATA
# ============================================================

if selected_account_id is None:

    transactions = load_all_transactions(
        user_id
    )

    saved_recurring = load_all_recurring_transactions(
        user_id
    )

else:

    transactions = load_transactions(
        user_id,
        selected_account_id,
    )

    saved_recurring = load_recurring_transactions(
        user_id,
        selected_account_id,
    )


transaction_df = prepare_transactions(
    transactions
)

budgets = load_budgets(user_id)


# ============================================================
# ADD ACCOUNT NAMES
# ============================================================

account_lookup = {
    str(account["id"]): account["name"]
    for account in accounts
}

if not transaction_df.empty and "account_id" in transaction_df.columns:

    transaction_df["account_name"] = (
        transaction_df["account_id"]
        .astype(str)
        .map(account_lookup)
        .fillna("Onbekend")
    )


# ============================================================
# TRANSFER DETECTION
# ============================================================

if not transaction_df.empty:

    try:

        detected = detect_transfer_transactions(
            transaction_df
        )

        if isinstance(detected, pd.DataFrame):

            transaction_df = detected

    except Exception:

        # Keep application running if the engine
        # does not support transfer detection yet.
        pass


# ============================================================
# OVERVIEW
# ============================================================

if chapter == "Overzicht":

    st.title("Overzicht")

    if selected_account_id is None:

        st.caption(
            "Gecombineerd overzicht van alle rekeningen"
        )

    else:

        st.caption(
            f"Rekening: {selected_account_name}"
        )

    # --------------------------------------------------------
    # CURRENT MONTH
    # --------------------------------------------------------

    today = date.today()

    current_month = pd.Period(
        today.strftime("%Y-%m"),
        freq="M",
    )

    st.subheader(
        f"Financieel overzicht — "
        f"{format_period(current_month)}"
    )

    try:

        metrics = calculate_monthly_metrics(
            transaction_df
        )

    except Exception:

        metrics = {}

    # --------------------------------------------------------
    # MAIN METRICS
    # --------------------------------------------------------

    col1, col2, col3, col4 = st.columns(4)

    income = safe_float(
        metrics.get(
            "income",
            metrics.get("total_income", 0),
        )
    )

    expenses = safe_float(
        metrics.get(
            "expenses",
            metrics.get("total_expenses", 0),
        )
    )

    net = income - expenses

    with col1:

        st.metric(
            "Inkomsten",
            euro(income),
        )

    with col2:

        st.metric(
            "Uitgaven",
            euro(expenses),
        )

    with col3:

        st.metric(
            "Netto",
            euro(net),
        )

    with col4:

        recurring_cost = calculate_monthly_recurring_cost(
            saved_recurring
        )

        recurring_income = calculate_monthly_recurring_income(
            saved_recurring
        )

        st.metric(
            "Vaste lasten",
            euro(recurring_cost),
        )

    st.divider()

    # ========================================================
    # INCOME SECTION
    # ========================================================

    st.subheader("💰 Inkomsten")

    # Filter income transactions for current month

    income_df = transaction_df.copy()

    if not income_df.empty:

        income_df["date"] = pd.to_datetime(
            income_df["date"],
            errors="coerce",
        )

        income_df = income_df[
            income_df["date"].dt.to_period("M")
            == current_month
        ]

        income_df = income_df[
            income_df["flow"] == "Inkomst"
        ]

        # Do not include detected transfers
        income_df = income_df[
            ~is_transfer_dataframe(income_df)
        ]

    if income_df.empty:

        st.info(
            "Nog geen inkomsten geregistreerd "
            "voor deze maand."
        )

    else:

        income_by_category = (
            income_df
            .groupby("category")["amount"]
            .sum()
            .sort_values(ascending=False)
        )

        income_columns = st.columns(
            min(
                max(len(income_by_category), 1),
                3,
            )
        )

        for index, (category, amount) in enumerate(
            income_by_category.items()
        ):

            with income_columns[
                index % len(income_columns)
            ]:

                st.metric(
                    category,
                    euro(abs(amount)),
                )

        st.bar_chart(
            income_by_category
        )

    st.divider()

    # ========================================================
    # EXPENSE SECTION
    # ========================================================

    st.subheader("💸 Uitgaven per categorie")

    try:

        category_spending = calculate_category_spending(
            transaction_df
        )

    except Exception:

        category_spending = {}

    if isinstance(category_spending, pd.Series):

        spending_series = category_spending

    elif isinstance(category_spending, dict):

        spending_series = pd.Series(
            category_spending
        )

    else:

        spending_series = pd.Series(dtype=float)

    # Remove income categories from expense chart
    spending_series = spending_series[
        ~spending_series.index.isin(
            INCOME_CATEGORIES
        )
    ]

    if spending_series.empty:

        st.info(
            "Nog geen uitgaven beschikbaar."
        )

    else:

        spending_series = (
            spending_series
            .sort_values(ascending=False)
        )

        st.bar_chart(
            spending_series
        )

    st.divider()

    # ========================================================
    # FORECAST
    # ========================================================

    st.subheader("🔮 Verwachting")

    try:

        forecast = calculate_month_forecast(
            transaction_df,
            budgets,
            saved_recurring,
        )

    except TypeError:

        try:

            forecast = calculate_month_forecast(
                transaction_df,
                budgets,
            )

        except Exception:

            forecast = {}

    except Exception:

        forecast = {}

    if isinstance(forecast, dict):

        forecast_income = safe_float(
            forecast.get(
                "forecast_income",
                forecast.get(
                    "projected_income",
                    0,
                ),
            )
        )

        forecast_expenses = safe_float(
            forecast.get(
                "forecast_expenses",
                forecast.get(
                    "projected_expenses",
                    0,
                ),
            )
        )

        projected_result = safe_float(
            forecast.get(
                "projected_result",
                forecast.get(
                    "forecast_net",
                    forecast_income
                    - forecast_expenses,
                ),
            )
        )

        c1, c2, c3 = st.columns(3)

        with c1:

            st.metric(
                "Verwachte inkomsten",
                euro(forecast_income),
            )

        with c2:

            st.metric(
                "Verwachte uitgaven",
                euro(forecast_expenses),
            )

        with c3:

            st.metric(
                "Verwacht resultaat",
                euro(projected_result),
            )

    # ========================================================
    # SAFE TO SPEND
    # ========================================================

    st.divider()

    st.subheader("🛡️ Safe to spend")

    buffer_amount = st.number_input(
        "Gewenste financiële buffer",
        min_value=0.0,
        value=500.0,
        step=100.0,
        format="%.0f",
    )

    try:

        safe_spend = calculate_safe_to_spend(
            transaction_df,
            saved_recurring,
            buffer_amount,
        )

    except TypeError:

        try:

            safe_spend = calculate_safe_to_spend(
                transaction_df,
                saved_recurring,
            )

        except Exception:

            safe_spend = 0

    except Exception:

        safe_spend = 0

    if isinstance(safe_spend, dict):

        safe_value = safe_spend.get(
            "safe_to_spend",
            safe_spend.get("amount", 0),
        )

    else:

        safe_value = safe_spend

    st.metric(
        "Beschikbaar om uit te geven",
        euro(safe_value),
    )

    # ========================================================
    # FINANCIAL HEALTH
    # ========================================================

    st.divider()

    st.subheader("❤️ Financiële gezondheid")

    try:

        health = calculate_financial_health(
            transaction_df,
            budgets,
            saved_recurring,
        )

    except Exception:

        health = None

    if isinstance(health, dict):

        health_score = health.get(
            "score",
            health.get(
                "health_score",
                None,
            ),
        )

        health_label = health.get(
            "label",
            health.get(
                "status",
                "",
            ),
        )

        if health_score is not None:

            st.metric(
                "Gezondheidsscore",
                f"{health_score}/100",
            )

        if health_label:

            st.write(
                f"**{health_label}**"
            )

    elif health is not None:

        st.write(health)


# ============================================================
# TRANSACTIONS
# ============================================================

elif chapter == "Transacties":

    st.title("Transacties")

    st.caption(
        "Importeer banktransacties vanuit een CSV-bestand."
    )

    if selected_account_id is None:

        st.warning(
            "Selecteer eerst een specifieke rekening "
            "om transacties te importeren."
        )

    else:

        uploaded_file = st.file_uploader(
            "CSV uploaden",
            type=["csv"],
        )

        if uploaded_file is not None:

            try:

                df = pd.read_csv(
                    uploaded_file,
                    sep=None,
                    engine="python",
                )

                st.success(
                    f"{len(df)} transacties gevonden."
                )

                st.write(
                    "Gevonden kolommen:"
                )

                st.write(
                    list(df.columns)
                )

                # ------------------------------------------------
                # COLUMN DETECTION
                # ------------------------------------------------

                def find_column(
                    columns,
                    possibilities,
                ):

                    normalized = {
                        str(c).lower().strip(): c
                        for c in columns
                    }

                    for possibility in possibilities:

                        if possibility.lower() in normalized:

                            return normalized[
                                possibility.lower()
                            ]

                    for column in columns:

                        column_lower = (
                            str(column)
                            .lower()
                            .strip()
                        )

                        for possibility in possibilities:

                            if (
                                possibility.lower()
                                in column_lower
                            ):

                                return column

                    return None

                date_col = find_column(
                    df.columns,
                    [
                        "date",
                        "datum",
                        "boekdatum",
                        "transactiedatum",
                    ],
                )

                description_col = find_column(
                    df.columns,
                    [
                        "description",
                        "omschrijving",
                        "beschrijving",
                        "name",
                        "naam",
                    ],
                )

                amount_col = find_column(
                    df.columns,
                    [
                        "amount",
                        "bedrag",
                        "saldo",
                    ],
                )

                debit_col = find_column(
                    df.columns,
                    [
                        "debit",
                        "af",
                        "uitgave",
                        "afschrijving",
                    ],
                )

                credit_col = find_column(
                    df.columns,
                    [
                        "credit",
                        "bij",
                        "inkomst",
                        "bijschrijving",
                    ],
                )

                if date_col is None:

                    st.error(
                        "Geen datumkolom gevonden."
                    )

                elif description_col is None:

                    st.error(
                        "Geen omschrijvingskolom gevonden."
                    )

                else:

                    # ------------------------------------------------
                    # DATE
                    # ------------------------------------------------

                    df["date"] = pd.to_datetime(
                        df[date_col].astype(str),
                        format="%Y%m%d",
                        errors="coerce",
                    )

                    failed_dates = df["date"].isna()

                    if failed_dates.any():

                        df.loc[
                            failed_dates,
                            "date"
                        ] = pd.to_datetime(
                            df.loc[
                                failed_dates,
                                date_col,
                            ],
                            dayfirst=True,
                            errors="coerce",
                        )

                    # ------------------------------------------------
                    # DESCRIPTION
                    # ------------------------------------------------

                    df["description"] = (
                        df[description_col]
                        .fillna("")
                        .astype(str)
                    )

                    df["merchant"] = (
                        df["description"]
                        .apply(normalize_merchant)
                    )

                    # ------------------------------------------------
                    # AMOUNT
                    # ------------------------------------------------

                    if amount_col is not None:

                        amount = (
                            df[amount_col]
                            .astype(str)
                            .str.replace(
                                "€",
                                "",
                                regex=False,
                            )
                            .str.replace(
                                " ",
                                "",
                                regex=False,
                            )
                        )

                        amount = (
                            amount
                            .str.replace(
                                ".",
                                "",
                                regex=False,
                            )
                            .str.replace(
                                ",",
                                ".",
                                regex=False,
                            )
                        )

                        df["amount"] = pd.to_numeric(
                            amount,
                            errors="coerce",
                        )

                    elif (
                        debit_col is not None
                        or credit_col is not None
                    ):

                        df["amount"] = 0.0

                        if debit_col is not None:

                            debit = (
                                df[debit_col]
                                .astype(str)
                                .str.replace(
                                    ".",
                                    "",
                                    regex=False,
                                )
                                .str.replace(
                                    ",",
                                    ".",
                                    regex=False,
                                )
                            )

                            df["amount"] -= pd.to_numeric(
                                debit,
                                errors="coerce",
                            ).fillna(0)

                        if credit_col is not None:

                            credit = (
                                df[credit_col]
                                .astype(str)
                                .str.replace(
                                    ".",
                                    "",
                                    regex=False,
                                )
                                .str.replace(
                                    ",",
                                    ".",
                                    regex=False,
                                )
                            )

                            df["amount"] += pd.to_numeric(
                                credit,
                                errors="coerce",
                            ).fillna(0)

                    else:

                        st.error(
                            "Geen bedragkolom gevonden."
                        )

                        st.stop()

                    # ------------------------------------------------
                    # FLOW
                    # ------------------------------------------------

                    df["flow"] = df["amount"].apply(
                        lambda x:
                            "Inkomst"
                            if x > 0
                            else "Uitgave"
                    )

                    # ------------------------------------------------
                    # CATEGORY
                    # ------------------------------------------------

                    merchant_rules = (
                        load_merchant_category_rules(
                            user_id
                        )
                    )

                    merchant_rule_lookup = {
                        normalize_merchant(
                            rule["merchant"]
                        ): rule["category"]
                        for rule in merchant_rules
                    }

                    def apply_category(row):

                        merchant = normalize_merchant(
                            row["merchant"]
                        )

                        if merchant in merchant_rule_lookup:

                            return merchant_rule_lookup[
                                merchant
                            ]

                        return categorize_transaction(
                            row["description"],
                            row["amount"],
                            row["flow"],
                        )

                    df["category"] = df.apply(
                        apply_category,
                        axis=1,
                    )

                    # ------------------------------------------------
                    # TRANSACTION TYPE
                    # ------------------------------------------------

                    df["transaction_type"] = (
                        "income"
                        if False
                        else df["flow"]
                    )

                    # ------------------------------------------------
                    # HASH
                    # ------------------------------------------------

                    df["transaction_hash"] = df.apply(
                        lambda row:
                            create_transaction_hash(
                                row["date"],
                                row["description"],
                                row["amount"],
                            ),
                        axis=1,
                    )

                    # ------------------------------------------------
                    # PREVIEW
                    # ------------------------------------------------

                    preview_columns = [
                        "date",
                        "description",
                        "amount",
                        "flow",
                        "category",
                    ]

                    st.subheader(
                        "Voorbeeld"
                    )

                    st.dataframe(
                        df[preview_columns],
                        use_container_width=True,
                        hide_index=True,
                    )

                    # ------------------------------------------------
                    # CATEGORY SUMMARY
                    # ------------------------------------------------

                    st.subheader(
                        "Categorisering"
                    )

                    category_summary = (
                        df.groupby(
                            ["flow", "category"]
                        )["amount"]
                        .agg(["count", "sum"])
                        .reset_index()
                    )

                    st.dataframe(
                        category_summary,
                        use_container_width=True,
                        hide_index=True,
                    )

                    # ------------------------------------------------
                    # SAVE
                    # ------------------------------------------------

                    if st.button(
                        "Transacties opslaan",
                        type="primary",
                    ):

                        records = []

                        for _, row in df.iterrows():

                            if pd.isna(row["date"]):

                                continue

                            records.append(
                                {
                                    "user_id": user_id,
                                    "account_id": selected_account_id,
                                    "date": row[
                                        "date"
                                    ].date().isoformat(),
                                    "description": row[
                                        "description"
                                    ],
                                    "merchant": row[
                                        "merchant"
                                    ],
                                    "amount": float(
                                        row["amount"]
                                    ),
                                    "flow": row[
                                        "flow"
                                    ],
                                    "category": row[
                                        "category"
                                    ],
                                    "transaction_type": row[
                                        "transaction_type"
                                    ],
                                    "transaction_hash": row[
                                        "transaction_hash"
                                    ],
                                }
                            )

                        try:

                            if records:

                                (
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
                                f"{len(records)} transacties "
                                "opgeslagen."
                            )

                            st.rerun()

                        except Exception as e:

                            st.error(
                                f"Opslaan mislukt: {e}"
                            )

    st.divider()

    # ========================================================
    # EXISTING TRANSACTIONS
    # ========================================================

    st.subheader(
        "Opgeslagen transacties"
    )

    if transaction_df.empty:

        st.info(
            "Nog geen transacties."
        )

    else:

        display_df = transaction_df.copy()

        columns = [
            "date",
            "description",
            "amount",
            "flow",
            "category",
        ]

        if (
            selected_account_id is None
            and "account_name" in display_df.columns
        ):

            columns.insert(
                1,
                "account_name",
            )

        available_columns = [
            c for c in columns
            if c in display_df.columns
        ]

        st.dataframe(
            display_df[
                available_columns
            ],
            use_container_width=True,
            hide_index=True,
        )


# ============================================================
# CATEGORIES
# ============================================================

elif chapter == "Categorieën":

    st.title("Categorieën")

    st.write(
        "Hier kun je categorieën per merchant "
        "permanent instellen."
    )

    rules = load_merchant_category_rules(
        user_id
    )

    if rules:

        rules_df = pd.DataFrame(rules)

        st.dataframe(
            rules_df[
                [
                    "merchant",
                    "category",
                ]
            ],
            use_container_width=True,
            hide_index=True,
        )

    st.subheader(
        "Nieuwe merchant-regel"
    )

    with st.form("merchant_rule"):

        merchant = st.text_input(
            "Merchant"
        )

        category = st.selectbox(
            "Categorie",
            CATEGORIES,
        )

        save = st.form_submit_button(
            "Regel opslaan"
        )

        if save:

            if not merchant:

                st.error(
                    "Vul een merchant in."
                )

            else:

                try:

                    save_merchant_category_rule(
                        user_id,
                        merchant,
                        category,
                    )

                    update_transactions_for_merchant(
                        user_id,
                        merchant,
                        category,
                    )

                    st.success(
                        "Regel opgeslagen en transacties "
                        "bijgewerkt."
                    )

                    st.rerun()

                except Exception as e:

                    st.error(
                        f"Opslaan mislukt: {e}"
                    )


# ============================================================
# RECURRING
# ============================================================

elif chapter == "Terugkerend":

    st.title("Terugkerende transacties")

    if selected_account_id is None:

        st.info(
            "Voor automatische detectie kun je het beste "
            "één specifieke rekening selecteren."
        )

    else:

        if st.button(
            "Detecteer terugkerende transacties"
        ):

            detected = detect_recurring_transactions(
                transaction_df
            )

            if not detected:

                st.info(
                    "Geen terugkerende transacties gevonden."
                )

            else:

                save_recurring_transactions(
                    user_id,
                    selected_account_id,
                    detected,
                )

                st.success(
                    f"{len(detected)} terugkerende "
                    "transacties gevonden en opgeslagen."
                )

                st.rerun()

    st.subheader(
        "Opgeslagen terugkerende transacties"
    )

    if not saved_recurring:

        st.info(
            "Nog geen terugkerende transacties."
        )

    else:

        for recurring in saved_recurring:

            col1, col2, col3, col4 = st.columns(
                [3, 2, 2, 1]
            )

            with col1:

                st.write(
                    f"**{recurring.get('merchant')}**"
                )

                st.caption(
                    recurring.get(
                        "category",
                        "Onbekend",
                    )
                )

            with col2:

                st.write(
                    euro(
                        recurring.get(
                            "expected_amount",
                            0,
                        )
                    )
                )

            with col3:

                st.write(
                    recurring.get(
                        "frequency",
                        "monthly",
                    )
                )

            with col4:

                active = recurring.get(
                    "active",
                    True,
                )

                new_active = st.checkbox(
                    "Actief",
                    value=active,
                    key=f"active_{recurring['id']}",
                )

                if new_active != active:

                    update_recurring_active(
                        user_id,
                        recurring["id"],
                        new_active,
                    )

                    st.rerun()

                if st.button(
                    "🗑️",
                    key=f"delete_{recurring['id']}",
                ):

                    delete_recurring_transaction(
                        user_id,
                        recurring["id"],
                    )

                    st.rerun()


# ============================================================
# BUDGETS
# ============================================================

elif chapter == "Budgetten":

    st.title("Budgetten")

    st.write(
        "Stel een maandelijks budget per "
        "uitgavencategorie in."
    )

    existing_budgets = {
        budget["category"]: safe_float(
            budget.get("monthly_limit")
        )
        for budget in budgets
    }

    selected_category = st.selectbox(
        "Categorie",
        EXPENSE_CATEGORIES,
    )

    current_limit = existing_budgets.get(
        selected_category,
        0.0,
    )

    monthly_limit = st.number_input(
        "Maandbudget",
        min_value=0.0,
        value=current_limit,
        step=50.0,
        format="%.2f",
    )

    if st.button(
        "Budget opslaan",
        type="primary",
    ):

        try:

            save_budget(
                user_id,
                selected_category,
                monthly_limit,
            )

            st.success(
                "Budget opgeslagen."
            )

            st.rerun()

        except Exception as e:

            st.error(
                f"Opslaan mislukt: {e}"
            )

    st.divider()

    if budgets:

        budget_display = pd.DataFrame(
            budgets
        )

        budget_display[
            "monthly_limit"
        ] = budget_display[
            "monthly_limit"
        ].apply(euro)

        st.dataframe(
            budget_display[
                [
                    "category",
                    "monthly_limit",
                ]
            ],
            use_container_width=True,
            hide_index=True,
        )

    else:

        st.info(
            "Nog geen budgetten ingesteld."
        )


# ============================================================
# SETTINGS
# ============================================================

elif chapter == "Instellingen":

    st.title("Instellingen")

    st.subheader(
        "Account"
    )

    st.write(
        f"**E-mailadres:** "
        f"{st.session_state.user.email}"
    )

    st.divider()

    st.subheader(
        "Bankrekeningen"
    )

    for account in accounts:

        st.write(
            f"**{account.get('name')}**"
        )

        details = []

        if account.get("bank"):
            details.append(
                account["bank"]
            )

        if account.get("account_type"):
            details.append(
                account["account_type"]
            )

        if details:

            st.caption(
                " • ".join(details)
            )

    st.divider()

    st.subheader(
        "Categorieën"
    )

    st.write(
        "**Inkomsten**"
    )

    for category in INCOME_CATEGORIES:

        st.write(
            f"• {category}"
        )

    st.write(
        "**Uitgaven**"
    )

    for category in EXPENSE_CATEGORIES:

        st.write(
            f"• {category}"
        )
