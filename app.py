import streamlit as st
import pandas as pd
import hashlib
from supabase import create_client

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
# CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="Financial Cockpit",
    page_icon="💰",
    layout="wide",
)


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
# CATEGORIES
# ============================================================

CATEGORIES = [
    "Salaris",
    "Belasting",
    "Rente",
    "Overboeking spaargeld",
    "Tikkies",
    "Overige inkomsten",

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


CATEGORY_RULES = {
    # Inkomsten
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
    ],

    "Rente": [
        "rente",
        "interest",
        "spaarrente",
    ],

    "Overboeking spaargeld": [
        "spaarrekening",
        "spaarrekening",
        "sparen",
        "overboeking sparen",
        "overboeking spaargeld",
    ],

    "Tikkies": [
        "tikkie",
        "tikkies",
        "betaalverzoek",
    ],

    "Overige inkomsten": [
        "inkomsten",
        "ontvangst",
        "uitbetaling",
        "vergoeding",
    ],

    # Uitgaven
    "Boodschappen": [
        "albert heijn",
        "ah ",
        "jumbo",
        "lidl",
        "aldi",
        "plus",
        "dirk",
        "hoogvliet",
        "vomar",
        "coop",
    ],

    "Telecom": [
        "kpn",
        "vodafone",
        "ziggo",
        "t-mobile",
        "odido",
        "tele2",
    ],

    "Vervoer": [
        "shell",
        "bp ",
        "esso",
        "total",
        "q8",
        "parking",
        "parkeren",
        "ns ",
        "ov-chipkaart",
    ],

    "Horeca": [
        "restaurant",
        "cafe",
        "café",
        "mcdonald",
        "starbucks",
        "thuisbezorgd",
        "uber eats",
    ],

    "Entertainment": [
        "spotify",
        "netflix",
        "pathe",
        "bioscoop",
        "steam",
        "playstation",
    ],

    "Abonnementen": [
        "subscription",
        "abonnement",
        "amazon prime",
        "disney",
        "apple.com/bill",
    ],

    "Wonen": [
        "hypotheek",
        "huur",
        "energie",
        "water",
        "vitens",
        "essent",
        "vandebron",
    ],

    "Verzekeringen": [
        "verzekering",
        "verzekeringen",
        "achmea",
        "aegon",
        "interpolis",
    ],

    "Gezondheid": [
        "apotheek",
        "huisarts",
        "ziekenhuis",
        "tandarts",
        "fysio",
    ],

    "Kleding": [
        "zara",
        "h&m",
        "uniqlo",
        "zalando",
        "we fashion",
    ],

    "Persoonlijke verzorging": [
        "rituals",
        "kapper",
        "kapsalon",
        "douglas",
        "ici paris",
    ],

    "Kinderen": [
        "kinderopvang",
        "school",
        "bsо",
        "crèche",
        "creche",
    ],

    "Vakantie": [
        "booking.com",
        "airbnb",
        "hotel",
        "vakantie",
        "transavia",
        "klm",
        "ryanair",
    ],
}


# ============================================================
# HELPERS
# ============================================================

def euro(value):
    try:
        return (
            f"€ {float(value):,.2f}"
            .replace(",", "X")
            .replace(".", ",")
            .replace("X", ".")
        )
    except Exception:
        return "€ 0,00"


def categorize_transaction(
    description,
    merchant=None,
    merchant_rules=None,
):

    text = str(description).lower()
    normalized = str(
        merchant or ""
    ).lower().strip()

    merchant_rules = merchant_rules or {}

    # User rules first
    for rule_merchant, category in merchant_rules.items():

        rule = str(
            rule_merchant
        ).lower().strip()

        if rule and (
            rule in normalized
            or rule in text
        ):
            return category

    # Default rules
    for category, keywords in CATEGORY_RULES.items():

        for keyword in keywords:

            if keyword.lower() in text:
                return category

    return "Overig"


def normalize_merchant(
    description,
    merchant_rules=None,
):

    text = str(
        description
    ).lower().strip()

    merchant_rules = merchant_rules or {}

    # User-defined merchants
    for merchant in merchant_rules:

        merchant = str(
            merchant
        ).lower().strip()

        if merchant and merchant in text:
            return merchant

    # Known merchants
    for keywords in CATEGORY_RULES.values():

        for keyword in keywords:

            if keyword.lower() in text:
                return keyword.strip().lower()

    return text


def create_transaction_hash(
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


# ============================================================
# DATABASE — MERCHANT RULES
# ============================================================

def load_merchant_category_rules(user_id):

    try:

        result = (
            supabase
            .table("merchant_category_rules")
            .select("*")
            .eq("user_id", user_id)
            .order("merchant")
            .execute()
        )

        return {
            str(row["merchant"])
            .lower()
            .strip(): row["category"]
            for row in (result.data or [])
            if row.get("merchant")
        }

    except Exception as e:

        st.error(
            f"❌ Categorieregels konden niet worden geladen: {e}"
        )

        return {}


def save_merchant_category_rule(
    user_id,
    merchant,
    category,
):

    merchant = str(
        merchant
    ).strip().lower()

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
                    "updated_at": pd.Timestamp.utcnow().isoformat(),
                },
                on_conflict="user_id,merchant",
            )
            .execute()
        )

        return result.data or []

    except Exception as e:

        st.error(
            f"❌ Categorieregel kon niet worden opgeslagen: {e}"
        )

        return None


def delete_merchant_category_rule(
    user_id,
    merchant,
):

    merchant = str(
        merchant
    ).strip().lower()

    try:

        result = (
            supabase
            .table("merchant_category_rules")
            .delete()
            .eq("user_id", user_id)
            .eq("merchant", merchant)
            .execute()
        )

        return result.data or []

    except Exception as e:

        st.error(
            f"❌ Categorieregel kon niet worden verwijderd: {e}"
        )

        return None


def update_transactions_for_merchant(
    user_id,
    merchant,
    category,
):

    merchant = str(
        merchant
    ).strip().lower()

    if not merchant:
        return None

    try:

        result = (
            supabase
            .table("transactions")
            .update(
                {
                    "category": category
                }
            )
            .eq("user_id", user_id)
            .eq("merchant", merchant)
            .execute()
        )

        return result.data or []

    except Exception as e:

        st.error(
            f"❌ Bestaande transacties konden niet worden bijgewerkt: {e}"
        )

        return None


# ============================================================
# DATABASE — ACCOUNTS
# ============================================================

def load_accounts(user_id):

    try:

        result = (
            supabase
            .table("accounts")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at")
            .execute()
        )

        return result.data or []

    except Exception as e:

        st.error(
            f"❌ Rekeningen konden niet worden geladen: {e}"
        )

        return []


# ============================================================
# DATABASE — TRANSACTIONS
# ============================================================

def load_transactions(
    user_id,
    account_id,
):

    try:

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

    except Exception as e:

        st.error(
            f"❌ Transacties konden niet worden geladen: {e}"
        )

        return []


def load_all_transactions(user_id):

    try:

        result = (
            supabase
            .table("transactions")
            .select("*")
            .eq("user_id", user_id)
            .order("date", desc=True)
            .execute()
        )

        return result.data or []

    except Exception as e:

        st.error(
            f"❌ Alle transacties konden niet worden geladen: {e}"
        )

        return []


# ============================================================
# DATABASE — BUDGETS
# ============================================================

def load_budgets(user_id):

    try:

        result = (
            supabase
            .table("budgets")
            .select("*")
            .eq("user_id", user_id)
            .order("category")
            .execute()
        )

        return result.data or []

    except Exception as e:

        st.error(
            f"❌ Budgetten konden niet worden geladen: {e}"
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
                    "monthly_limit": float(
                        monthly_limit
                    ),
                },
                on_conflict="user_id,category",
            )
            .execute()
        )

        return result.data

    except Exception as e:

        st.error(
            f"❌ Budget kon niet worden opgeslagen: {e}"
        )

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
            .eq("user_id", user_id)
            .eq("account_id", account_id)
            .order("next_occurrence")
            .execute()
        )

        return result.data or []

    except Exception as e:

        st.error(
            f"❌ Terugkerende transacties konden niet worden geladen: {e}"
        )

        return []


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
                "merchant": recurring["merchant"],
                "category": recurring["category"],
                "frequency": recurring["frequency"],
                "expected_amount": float(
                    recurring["expected_amount"]
                ),
                "last_occurrence": recurring[
                    "last_occurrence"
                ],
                "next_occurrence": recurring[
                    "next_occurrence"
                ],
                "active": True,
                "flow": recurring.get(
                    "flow",
                    "Uitgave",
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
            f"❌ Terugkerende betalingen konden niet worden opgeslagen: {e}"
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
            .eq("id", recurring_id)
            .execute()
            .data
        )

    except Exception as e:

        st.error(
            f"❌ Status kon niet worden gewijzigd: {e}"
        )

        return None


def delete_recurring_transaction(
    recurring_id
):

    try:

        return (
            supabase
            .table("recurring_transactions")
            .delete()
            .eq("id", recurring_id)
            .execute()
            .data
        )

    except Exception as e:

        st.error(
            f"❌ Terugkerende transactie kon niet worden verwijderd: {e}"
        )

        return None


# ============================================================
# RECURRING DETECTION
# ============================================================

def detect_recurring_transactions(
    transactions
):

    if not transactions:
        return []

    df = pd.DataFrame(
        transactions
    )

    if df.empty:
        return []

    required = [
        "date",
        "merchant",
        "amount",
        "flow",
    ]

    for column in required:

        if column not in df.columns:
            return []

    df = df.copy()

    df["date"] = pd.to_datetime(
        df["date"],
        errors="coerce",
    )

    df["amount"] = pd.to_numeric(
        df["amount"],
        errors="coerce",
    )

    df["merchant"] = (
        df["merchant"]
        .astype(str)
        .str.strip()
        .str.lower()
    )

    df = df[
        df["date"].notna()
        & df["amount"].notna()
        & (df["merchant"] != "")
    ].copy()

    # Only real expenses for recurring detection.
    df = df[
        df["flow"] == "Uitgave"
    ].copy()

    if df.empty:
        return []

    df["amount_abs"] = (
        df["amount"].abs()
    )

    recurring = []

    for merchant, group in df.groupby(
        "merchant"
    ):

        if len(group) < 2:
            continue

        group = group.sort_values(
            "date"
        )

        dates = list(
            group["date"]
        )

        amounts = list(
            group["amount_abs"]
        )

        intervals = []

        for i in range(
            1,
            len(dates),
        ):

            days = (
                dates[i]
                - dates[i - 1]
            ).days

            if days > 0:
                intervals.append(days)

        if not intervals:
            continue

        average_interval = (
            sum(intervals)
            / len(intervals)
        )

        if (
            25
            <= average_interval
            <= 35
        ):

            frequency = "Maandelijks"

        elif (
            6
            <= average_interval
            <= 8
        ):

            frequency = "Wekelijks"

        elif (
            80
            <= average_interval
            <= 100
        ):

            frequency = "Per kwartaal"

        elif (
            350
            <= average_interval
            <= 380
        ):

            frequency = "Jaarlijks"

        else:
            continue

        average_amount = (
            sum(amounts)
            / len(amounts)
        )

        if average_amount == 0:
            continue

        max_difference = max(
            abs(
                amount
                - average_amount
            )
            for amount in amounts
        )

        percentage_difference = (
            max_difference
            / average_amount
        )

        if (
            percentage_difference
            <= 0.15
        ):

            reliability = "Hoog"

        elif (
            percentage_difference
            <= 0.30
        ):

            reliability = "Gemiddeld"

        else:
            continue

        category = "Overig"

        if "category" in group.columns:

            categories = (
                group["category"]
                .dropna()
                .astype(str)
            )

            if not categories.empty:

                modes = (
                    categories.mode()
                )

                if not modes.empty:
                    category = modes.iloc[0]

        last_date = dates[-1]

        if frequency == "Wekelijks":

            next_date = (
                last_date
                + pd.Timedelta(days=7)
            )

        elif frequency == "Maandelijks":

            next_date = (
                last_date
                + pd.DateOffset(months=1)
            )

        elif frequency == "Per kwartaal":

            next_date = (
                last_date
                + pd.DateOffset(months=3)
            )

        else:

            next_date = (
                last_date
                + pd.DateOffset(years=1)
            )

        recurring.append(
            {
                "merchant": merchant,
                "category": category,
                "frequency": frequency,
                "expected_amount": round(
                    average_amount,
                    2,
                ),
                "occurrences": len(group),
                "last_occurrence":
                    last_date.strftime(
                        "%Y-%m-%d"
                    ),
                "next_occurrence":
                    next_date.strftime(
                        "%Y-%m-%d"
                    ),
                "reliability":
                    reliability,
                "flow":
                    "Uitgave",
            }
        )

    return recurring


# ============================================================
# LOGIN
# ============================================================

def show_login():

    st.title(
        "💰 Financial Cockpit"
    )

    st.write(
        "Log in om je persoonlijke financiële dashboard te bekijken."
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
                    "Vul je e-mailadres en wachtwoord in."
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
                    "❌ Wachtwoorden komen niet overeen."
                )

                return

            if len(password) < 8:

                st.error(
                    "❌ Wachtwoord moet minimaal 8 tekens bevatten."
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
                        "Controleer je e-mail om je account te bevestigen."
                    )

            except Exception as e:

                st.error(
                    f"❌ Account aanmaken mislukt: {e}"
                )


# ============================================================
# AUTHENTICATION
# ============================================================

if "user" not in st.session_state:

    show_login()
    st.stop()


if (
    "access_token"
    not in st.session_state
    or "refresh_token"
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
        "Je sessie is verlopen. Log opnieuw in."
    )

    st.session_state.clear()
    st.stop()


user = st.session_state[
    "user"
]

user_id = user.id

merchant_category_rules = (
    load_merchant_category_rules(
        user_id
    )
)


# ============================================================
# LOAD ACCOUNTS
# ============================================================

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
                                "user_id": user_id,
                                "name": name.strip(),
                                "bank": bank.strip(),
                                "account_type": account_type,
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
                        f"❌ Rekening kon niet worden toegevoegd: {e}"
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

    # --------------------------------------------------------
    # ACCOUNT SELECTOR
    # --------------------------------------------------------

    account_options = {
        account["name"]: account["id"]
        for account in accounts
    }

    account_selection = st.selectbox(
        "🏦 Rekening",
        [
            "Alle rekeningen"
        ]
        + list(account_options.keys()),
    )

    if (
        account_selection
        == "Alle rekeningen"
    ):

        selected_account_id = None
        account_scope_label = (
            "Alle rekeningen"
        )

    else:

        selected_account_id = (
            account_options[
                account_selection
            ]
        )

        account_scope_label = (
            account_selection
        )

    st.caption(
        f"📌 {account_scope_label}"
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
# LOAD TRANSACTIONS
# ============================================================

if selected_account_id is None:

    transactions = load_all_transactions(
        user_id
    )

else:

    transactions = load_transactions(
        user_id,
        selected_account_id
    )


transaction_df = prepare_transactions(
    transactions
)


# ============================================================
# TRANSFER DETECTION
# ============================================================

if not transaction_df.empty:

    transaction_df = (
        detect_transfer_transactions(
            transaction_df
        )
    )


# ============================================================
# LOAD RECURRING
# ============================================================

if selected_account_id is None:

    saved_recurring = []

    for account in accounts:

        account_recurring = (
            load_recurring_transactions(
                user_id,
                account["id"],
            )
        )

        saved_recurring.extend(
            account_recurring
        )

else:

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
        f"Financieel overzicht · {account_scope_label}"
    )

    if transaction_df.empty:

        st.info(
            "Nog geen transacties beschikbaar. "
            "Ga naar 💳 Transacties om een CSV te importeren."
        )

        st.stop()

    # --------------------------------------------------------
    # PERIODS
    # --------------------------------------------------------

    available_periods = sorted(
        transaction_df["date"]
        .dt.to_period("M")
        .unique(),
        reverse=True,
    )

    current_period = (
        pd.Timestamp.today()
        .to_period("M")
    )

    if (
        current_period
        in available_periods
    ):

        default_index = (
            list(
                available_periods
            ).index(
                current_period
            )
        )

    else:

        default_index = 0

    selected_period = st.selectbox(
        "📅 Maand",
        available_periods,
        index=default_index,
        format_func=lambda x:
            x.strftime("%B %Y"),
    )

    # --------------------------------------------------------
    # METRICS
    # --------------------------------------------------------

    metrics = calculate_monthly_metrics(
        transaction_df,
        selected_period,
        exclude_internal_transfers=True,
    )

    income = metrics[
        "income"
    ]

    expenses = metrics[
        "expenses"
    ]

    net = metrics[
        "net"
    ]

    savings_rate = (
        net / income * 100
        if income > 0
        else 0
    )

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

        st.metric(
            "🏦 Spaarpercentage",
            f"{savings_rate:.1f}%",
        )

    # --------------------------------------------------------
    # TRANSFERS
    # --------------------------------------------------------

    transfer_count = 0

    if (
        not transaction_df.empty
        and "is_transfer"
        in transaction_df.columns
    ):

        transfer_count = int(
            transaction_df[
                "is_transfer"
            ].sum()
        )

    if transfer_count > 0:

        st.caption(
            f"ℹ️ {transfer_count} transacties "
            f"zijn herkend als interne overboeking "
            f"en tellen niet mee als inkomsten of uitgaven."
        )

    st.divider()

    # --------------------------------------------------------
    # MONTH DATA
    # --------------------------------------------------------

    month_df = transaction_df[
        transaction_df["date"]
        .dt.to_period("M")
        == selected_period
    ].copy()

    if "is_transfer" in month_df.columns:

        month_df = month_df[
            ~month_df["is_transfer"]
        ]

    expense_df = month_df[
        month_df["flow"]
        == "Uitgave"
    ].copy()

    # --------------------------------------------------------
    # CHARTS
    # --------------------------------------------------------

    left, right = st.columns(2)

    with left:

        st.subheader(
            "💸 Uitgaven per categorie"
        )

        if not expense_df.empty:

            expense_df[
                "expense_amount"
            ] = (
                expense_df[
                    "amount"
                ].abs()
            )

            category_summary = (
                expense_df
                .groupby(
                    "category"
                )[
                    "expense_amount"
                ]
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
                )[
                    "amount"
                ]
                .sum()
                .abs()
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
    # FORECAST
    # --------------------------------------------------------

    st.divider()

    st.subheader(
        "🔮 Verwachting"
    )

    active_recurring = [
        item
        for item in saved_recurring
        if item.get(
            "active",
            True,
        )
    ]

    forecast = calculate_month_forecast(
        transaction_df,
        selected_period,
        active_recurring,
        budgets,
    )

    budget_status = (
        calculate_budget_status(
            transaction_df,
            budgets,
            selected_period,
        )
    )

    health = (
        calculate_financial_health(
            forecast,
            budget_status,
        )
    )

    col1, col2, col3, col4 = (
        st.columns(4)
    )

    with col1:

        st.metric(
            "Verwachte inkomsten",
            euro(
                forecast[
                    "projected_income"
                ]
            ),
        )

    with col2:

        st.metric(
            "Verwachte uitgaven",
            euro(
                forecast[
                    "projected_expenses"
                ]
            ),
        )

    with col3:

        st.metric(
            "Verwacht netto",
            euro(
                forecast[
                    "projected_net"
                ]
            ),
        )

    with col4:

        st.metric(
            "Financial Health",
            f"{health['score']}/100",
        )

        st.caption(
            health["status"]
        )

    # --------------------------------------------------------
    # FORECAST DETAILS
    # --------------------------------------------------------

    if (
        selected_period
        == current_period
    ):

        col1, col2, col3 = (
            st.columns(3)
        )

        with col1:

            st.metric(
                "Al ontvangen",
                euro(
                    forecast[
                        "actual_income"
                    ]
                ),
            )

        with col2:

            st.metric(
                "Al uitgegeven",
                euro(
                    forecast[
                        "actual_expenses"
                    ]
                ),
            )

        with col3:

            st.metric(
                "Nog komende vaste lasten",
                euro(
                    forecast[
                        "recurring_remaining"
                    ]
                ),
            )

        st.caption(
            f"Nog {forecast['remaining_days']} dagen "
            f"in deze maand."
        )

    # --------------------------------------------------------
    # FORECAST MESSAGE
    # --------------------------------------------------------

    projected_net = forecast[
        "projected_net"
    ]

    if projected_net >= 0:

        st.success(
            f"🟢 Verwacht resultaat: "
            f"**{euro(projected_net)}** positief."
        )

    else:

        st.error(
            f"🔴 Verwacht resultaat: "
            f"**{euro(abs(projected_net))}** tekort."
        )

    # --------------------------------------------------------
    # SAFE TO SPEND
    # --------------------------------------------------------

    st.divider()

    st.subheader(
        "💳 Safe to Spend"
    )

    safety_buffer = 500.0

    safe_to_spend = (
        calculate_safe_to_spend(
            forecast,
            buffer=safety_buffer,
        )
    )

    safe_col1, safe_col2 = (
        st.columns([2, 1])
    )

    with safe_col1:

        if safe_to_spend > 0:

            st.success(
                f"### {euro(safe_to_spend)}"
            )

            st.caption(
                "Dit is het bedrag dat je volgens "
                "de huidige cashflowverwachting "
                "extra kunt uitgeven."
            )

        else:

            st.warning(
                "### € 0,00"
            )

            st.caption(
                "Er is op basis van de huidige "
                "forecast geen veilig extra "
                "uitgeefbaar bedrag."
            )

    with safe_col2:

        st.metric(
            "Veiligheidsbuffer",
            euro(safety_buffer),
        )

    # --------------------------------------------------------
    # RECURRING
    # --------------------------------------------------------

    st.divider()

    st.subheader(
        "🔄 Terugkerend"
    )

    recurring_expenses = (
        calculate_monthly_recurring_cost(
            active_recurring
        )
    )

    recurring_income = (
        calculate_monthly_recurring_income(
            active_recurring
        )
    )

    col1, col2, col3 = (
        st.columns(3)
    )

    with col1:

        st.metric(
            "Terugkerende inkomsten",
            euro(recurring_income),
        )

    with col2:

        st.metric(
            "Terugkerende uitgaven",
            euro(recurring_expenses),
        )

    with col3:

        st.metric(
            "Actieve recurring",
            len(active_recurring),
        )

    # --------------------------------------------------------
    # WARNINGS
    # --------------------------------------------------------

    if health["warnings"]:

        st.divider()

        st.subheader(
            "⚠️ Aandachtspunten"
        )

        for warning in health[
            "warnings"
        ]:

            st.write(
                warning
            )


# ============================================================
# CHAPTER 2 — TRANSACTIONS
# ============================================================

elif chapter == "💳 Transacties":

    st.title(
        "💳 Transacties"
    )

    st.caption(
        f"Transacties · {account_scope_label}"
    )

    # --------------------------------------------------------
    # CSV IMPORT
    # --------------------------------------------------------

    if selected_account_id is None:

        st.info(
            "ℹ️ Selecteer eerst een specifieke "
            "bankrekening om een CSV te importeren."
        )

    else:

        with st.expander(
            "📁 Nieuwe CSV importeren",
            expanded=not transactions,
        ):

            uploaded_file = (
                st.file_uploader(
                    "Upload je banktransacties",
                    type=["csv"],
                )
            )

            if uploaded_file is not None:

                try:

                    df = pd.read_csv(
                        uploaded_file,
                        sep=None,
                        engine="python",
                    )

                    df.columns = (
                        df.columns
                        .astype(str)
                        .str.strip()
                        .str.lower()
                    )

                    df = df.dropna(
                        axis=1,
                        how="all",
                    )

                    description_options = [
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
                    ]

                    amount_options = [
                        "amount",
                        "amount (eur)",
                        "amount (euro)",
                        "bedrag",
                        "waarde",
                        "transactiebedrag",
                    ]

                    date_options = [
                        "date",
                        "datum",
                        "transaction date",
                        "transactiedatum",
                    ]

                    debit_credit_options = [
                        "debit/credit",
                        "debit credit",
                        "debit_credit",
                        "type",
                    ]

                    description_column = next(
                        (
                            column
                            for column
                            in description_options
                            if column
                            in df.columns
                        ),
                        None,
                    )

                    amount_column = next(
                        (
                            column
                            for column
                            in amount_options
                            if column
                            in df.columns
                        ),
                        None,
                    )

                    date_column = next(
                        (
                            column
                            for column
                            in date_options
                            if column
                            in df.columns
                        ),
                        None,
                    )

                    debit_credit_column = next(
                        (
                            column
                            for column
                            in debit_credit_options
                            if column
                            in df.columns
                        ),
                        None,
                    )

                    missing = []

                    if (
                        description_column
                        is None
                    ):
                        missing.append(
                            "omschrijving"
                        )

                    if (
                        amount_column
                        is None
                    ):
                        missing.append(
                            "bedrag"
                        )

                    if (
                        date_column
                        is None
                    ):
                        missing.append(
                            "datum"
                        )

                    if (
                        debit_credit_column
                        is None
                    ):
                        missing.append(
                            "debit/credit"
                        )

                    if missing:

                        st.error(
                            "❌ Niet gevonden: "
                            + ", ".join(
                                missing
                            )
                        )

                        st.write(
                            "Gevonden kolommen:"
                        )

                        st.code(
                            "\n".join(
                                df.columns
                            )
                        )

                        st.stop()

                    # ------------------------------------------------
                    # DATE
                    # ------------------------------------------------

                    raw_dates = (
                        df[date_column]
                        .astype(str)
                        .str.strip()
                    )

                    df[date_column] = (
                        pd.to_datetime(
                            raw_dates,
                            format="%Y%m%d",
                            errors="coerce",
                        )
                    )

                    missing_dates = (
                        df[
                            date_column
                        ].isna()
                    )

                    if missing_dates.any():

                        df.loc[
                            missing_dates,
                            date_column,
                        ] = (
                            pd.to_datetime(
                                raw_dates[
                                    missing_dates
                                ],
                                errors="coerce",
                                dayfirst=True,
                            )
                        )

                    # ------------------------------------------------
                    # AMOUNT
                    # ------------------------------------------------

                    amount_series = (
                        df[amount_column]
                        .astype(str)
                        .str.strip()
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

                    df[amount_column] = (
                        pd.to_numeric(
                            amount_series,
                            errors="coerce",
                        )
                    )

                    # ------------------------------------------------
                    # FLOW
                    # ------------------------------------------------

                    df[
                        "transaction_type"
                    ] = (
                        df[
                            debit_credit_column
                        ]
                        .astype(str)
                        .str.strip()
                        .str.lower()
                    )

                    df["flow"] = (
                        df[
                            "transaction_type"
                        ].apply(
                            lambda x:
                                "Inkomst"
                                if x
                                == "credit"
                                else
                                "Uitgave"
                                if x
                                == "debit"
                                else
                                "Onbekend"
                        )
                    )

                    # ------------------------------------------------
                    # MERCHANT
                    # ------------------------------------------------

                    df["merchant"] = (
                        df[
                            description_column
                        ].apply(
                            lambda value:
                                normalize_merchant(
                                    value,
                                    merchant_category_rules,
                                )
                        )
                    )

                    # ------------------------------------------------
                    # CATEGORY
                    # ------------------------------------------------

                    df["category"] = (
                        df.apply(
                            lambda row:
                                categorize_transaction(
                                    row[
                                        description_column
                                    ],
                                    row[
                                        "merchant"
                                    ],
                                    merchant_category_rules,
                                ),
                            axis=1,
                        )
                    )

                    # ------------------------------------------------
                    # HASH
                    # ------------------------------------------------

                    df[
                        "transaction_hash"
                    ] = df.apply(
                        lambda row:
                            create_transaction_hash(
                                row[
                                    date_column
                                ],
                                row[
                                    description_column
                                ],
                                row[
                                    amount_column
                                ],
                                row[
                                    "transaction_type"
                                ],
                            ),
                        axis=1,
                    )

                    # Remove duplicates within import
                    df = df.drop_duplicates(
                        subset=[
                            "transaction_hash"
                        ],
                        keep="first",
                    )

                    df = df[
                        df[
                            date_column
                        ].notna()
                        & df[
                            amount_column
                        ].notna()
                    ].copy()

                    st.success(
                        f"✅ {len(df):,} transacties gevonden."
                    )

                    st.dataframe(
                        df[
                            [
                                date_column,
                                description_column,
                                "merchant",
                                amount_column,
                                "flow",
                                "category",
                            ]
                        ],
                        use_container_width=True,
                        hide_index=True,
                    )

                    # ------------------------------------------------
                    # SAVE
                    # ------------------------------------------------

                    if st.button(
                        "💾 Transacties opslaan",
                        type="primary",
                        use_container_width=True,
                    ):

                        records = []

                        for _, row in (
                            df.iterrows()
                        ):

                            records.append(
                                {
                                    "user_id":
                                        user_id,

                                    "account_id":
                                        selected_account_id,

                                    "date":
                                        row[
                                            date_column
                                        ].strftime(
                                            "%Y-%m-%d"
                                        ),

                                    "description":
                                        str(
                                            row[
                                                description_column
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
                                                amount_column
                                            ]
                                        ),

                                    "flow":
                                        row[
                                            "flow"
                                        ],

                                    "category":
                                        row[
                                            "category"
                                        ],

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
                                f"✅ {len(result.data)} transacties verwerkt."
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
    # TRANSACTION TABLE
    # --------------------------------------------------------

    st.divider()

    if not transaction_df.empty:

        display_df = transaction_df.copy()

        # Add transfer status
        if "is_transfer" in display_df.columns:

            display_df["Type"] = (
                display_df[
                    "is_transfer"
                ].apply(
                    lambda x:
                        "🔄 Overboeking"
                        if x
                        else "Normaal"
                )
            )

        else:

            display_df["Type"] = (
                "Normaal"
            )

        col1, col2, col3, col4 = (
            st.columns(4)
        )

        with col1:

            st.metric(
                "Transacties",
                len(display_df),
            )

        with col2:

            normal_expenses = (
                display_df[
                    (
                        display_df[
                            "flow"
                        ]
                        == "Uitgave"
                    )
                    & (
                        ~display_df[
                            "is_transfer"
                        ]
                    )
                ]["amount"]
                .abs()
                .sum()
                if "is_transfer"
                in display_df.columns
                else display_df[
                    display_df[
                        "flow"
                    ]
                    == "Uitgave"
                ]["amount"]
                .abs()
                .sum()
            )

            st.metric(
                "Uitgaven",
                euro(
                    normal_expenses
                ),
            )

        with col3:

            normal_income = (
                display_df[
                    (
                        display_df[
                            "flow"
                        ]
                        == "Inkomst"
                    )
                    & (
                        ~display_df[
                            "is_transfer"
                        ]
                    )
                ]["amount"]
                .sum()
                if "is_transfer"
                in display_df.columns
                else display_df[
                    display_df[
                        "flow"
                    ]
                    == "Inkomst"
                ]["amount"].sum()
            )

            st.metric(
                "Inkomsten",
                euro(
                    normal_income
                ),
            )

        with col4:

            st.metric(
                "Overboekingen",
                transfer_count
                if "transfer_count"
                in locals()
                else 0,
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
            "Type",
        ]

        available_columns = [
            column
            for column
            in display_columns
            if column
            in display_df.columns
        ]

        st.dataframe(
            display_df[
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
        "Categoriseer je uitgaven per winkel of organisatie."
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

    df = prepare_transactions(
        all_transactions
    )

    df = detect_transfer_transactions(
        df
    )

    if "is_transfer" in df.columns:

        df = df[
            ~df[
                "is_transfer"
            ]
        ]

    expenses = df[
        df["flow"] == "Uitgave"
    ].copy()

    if expenses.empty:

        st.info(
            "Geen uitgaven gevonden."
        )

        st.stop()

    st.info(
        "💡 Een merchantregel wordt toegepast "
        "op bestaande én toekomstige transacties."
    )

    # --------------------------------------------------------
    # MERCHANT SUMMARY
    # --------------------------------------------------------

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

        merchant = str(
            merchant
        ).lower().strip()

        if (
            merchant
            in merchant_category_rules
        ):

            return merchant_category_rules[
                merchant
            ]

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
    ] = (
        merchant_summary[
            "merchant"
        ].apply(
            merchant_current_category
        )
    )

    merchant_summary = (
        merchant_summary
        .sort_values(
            "total",
            ascending=False,
        )
    )

    # --------------------------------------------------------
    # FILTERS
    # --------------------------------------------------------

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

    if merchant_summary.empty:

        st.info(
            "Geen merchants gevonden."
        )

    else:

        for index, row in (
            merchant_summary
            .reset_index(drop=True)
            .iterrows()
        ):

            merchant = str(
                row["merchant"]
            ).strip().lower()

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
                        [3, 1.5, 2, 1.8]
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
                                    f"✅ {merchant.title()} → "
                                    f"{new_category}"
                                )

                                st.rerun()

    # --------------------------------------------------------
    # CUSTOM RULE
    # --------------------------------------------------------

    st.divider()

    st.subheader(
        "⚙️ Eigen categorisatieregel"
    )

    st.caption(
        "Bijvoorbeeld: bol.com → Persoonlijke verzorging."
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
                            f"{custom_merchant.title()} → "
                            f"{custom_category}"
                        )

                        st.rerun()

    # --------------------------------------------------------
    # RULES
    # --------------------------------------------------------

    st.divider()

    st.subheader(
        "📌 Mijn eigen regels"
    )

    if not merchant_category_rules:

        st.caption(
            "Je hebt nog geen eigen categorisatieregels."
        )

    else:

        for rule_index, (
            merchant,
            category,
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
                        [3, 2, 1.2]
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
                                f"Regel voor "
                                f"{merchant.title()} "
                                f"verwijderd."
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
        f"Terugkerende transacties · {account_scope_label}"
    )

    # --------------------------------------------------------
    # DETECTION
    # --------------------------------------------------------

    if selected_account_id is None:

        st.info(
            "💡 Je bekijkt alle rekeningen. "
            "Terugkerende betalingen worden per rekening "
            "gedetecteerd om dubbele of verkeerde koppelingen "
            "te voorkomen."
        )

        if st.button(
            "🔍 Terugkerende betalingen detecteren",
            type="primary",
            use_container_width=True,
        ):

            total_saved = 0

            for account in accounts:

                account_id = account[
                    "id"
                ]

                account_transactions = (
                    load_transactions(
                        user_id,
                        account_id,
                    )
                )

                detected = (
                    detect_recurring_transactions(
                        account_transactions
                    )
                )

                if detected:

                    saved = (
                        save_recurring_transactions(
                            user_id,
                            account_id,
                            detected,
                        )
                    )

                    total_saved += len(
                        saved
                    )

            if total_saved > 0:

                st.success(
                    f"✅ {total_saved} terugkerende "
                    f"betalingen opgeslagen."
                )

                st.rerun()

            else:

                st.info(
                    "Geen duidelijke terugkerende "
                    "betalingen gevonden."
                )

    else:

        if st.button(
            "🔍 Terugkerende betalingen detecteren",
            type="primary",
            use_container_width=True,
        ):

            detected = (
                detect_recurring_transactions(
                    transactions
                )
            )

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
                        f"terugkerende betalingen opgeslagen."
                    )

                    st.rerun()

            else:

                st.info(
                    "Geen duidelijke terugkerende "
                    "betalingen gevonden."
                )

    # --------------------------------------------------------
    # RECURRING OVERVIEW
    # --------------------------------------------------------

    if saved_recurring:

        active = [
            item
            for item
            in saved_recurring
            if item.get(
                "active",
                True,
            )
        ]

        inactive = [
            item
            for item
            in saved_recurring
            if not item.get(
                "active",
                True,
            )
        ]

        monthly_cost = (
            calculate_monthly_recurring_cost(
                saved_recurring
            )
        )

        monthly_income = (
            calculate_monthly_recurring_income(
                saved_recurring
            )
        )

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
                "Maandelijkse uitgaven",
                euro(monthly_cost),
            )

        with col3:

            st.metric(
                "Maandelijkse inkomsten",
                euro(monthly_income),
            )

        with col4:

            st.metric(
                "Inactief",
                len(inactive),
            )

        st.divider()

        for recurring in active:

            recurring_id = (
                recurring.get("id")
            )

            merchant = (
                recurring.get(
                    "merchant",
                    "Onbekend",
                )
            )

            category = (
                recurring.get(
                    "category",
                    "Overig",
                )
            )

            frequency = (
                recurring.get(
                    "frequency",
                    "Onbekend",
                )
            )

            amount = float(
                recurring.get(
                    "expected_amount",
                    0,
                )
                or 0
            )

            next_occurrence = (
                recurring.get(
                    "next_occurrence",
                    "-",
                )
            )

            flow = recurring.get(
                "flow",
                "Uitgave",
            )

            with st.container(
                border=True
            ):

                col1, col2, col3, col4 = (
                    st.columns(
                        [3, 1.5, 1.5, 1.5]
                    )
                )

                with col1:

                    st.markdown(
                        f"**{merchant.title()}**"
                    )

                    st.caption(
                        f"{category} · "
                        f"{frequency} · "
                        f"{flow}"
                    )

                with col2:

                    st.metric(
                        "Bedrag",
                        euro(amount),
                    )

                with col3:

                    st.metric(
                        "Volgende",
                        next_occurrence,
                    )

                with col4:

                    st.metric(
                        "Betrouwbaarheid",
                        recurring.get(
                            "reliability",
                            "-",
                        ),
                    )

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

                        update_recurring_active(
                            recurring_id,
                            False,
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

                        delete_recurring_transaction(
                            recurring_id
                        )

                        st.rerun()

        if inactive:

            with st.expander(
                "⏸️ Inactieve betalingen"
            ):

                for recurring in inactive:

                    recurring_id = (
                        recurring.get(
                            "id"
                        )
                    )

                    merchant = (
                        recurring.get(
                            "merchant",
                            "Onbekend",
                        )
                    )

                    if st.button(
                        f"▶️ {merchant.title()} activeren",
                        key=(
                            f"activate_"
                            f"{recurring_id}"
                        ),
                    ):

                        update_recurring_active(
                            recurring_id,
                            True,
                        )

                        st.rerun()

    else:

        st.info(
            "Nog geen terugkerende betalingen gevonden."
        )


# ============================================================
# CHAPTER 5 — BUDGETS
# ============================================================

elif chapter == "🎯 Budgetten":

    st.title(
        "🎯 Budgetten"
    )

    st.caption(
        "Stel per categorie een maximaal bedrag per maand in."
    )

    # --------------------------------------------------------
    # NEW BUDGET
    # --------------------------------------------------------

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

    if (
        not transaction_df.empty
        and budgets
    ):

        periods = sorted(
            transaction_df["date"]
            .dt.to_period("M")
            .unique(),
            reverse=True,
        )

        selected_period = (
            st.selectbox(
                "📅 Maand",
                periods,
                format_func=lambda x:
                    x.strftime(
                        "%B %Y"
                    ),
            )
        )

        budget_status = (
            calculate_budget_status(
                transaction_df,
                budgets,
                selected_period,
            )
        )

        for budget in budget_status:

            category = budget[
                "category"
            ]

            budget_amount = budget[
                "budget"
            ]

            spent = budget[
                "spent"
            ]

            remaining = budget[
                "remaining"
            ]

            percentage = budget[
                "percentage"
            ]

            st.subheader(
                category
            )

            col1, col2, col3 = (
                st.columns(3)
            )

            with col1:

                st.metric(
                    "Budget",
                    euro(
                        budget_amount
                    ),
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
                    f"met {euro(abs(remaining))}"
                )

            elif percentage >= 80:

                st.warning(
                    f"🟠 {percentage:.0f}% gebruikt."
                )

            else:

                st.success(
                    f"🟢 {percentage:.0f}% gebruikt."
                )

            st.divider()

    elif not budgets:

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
                    [3, 2, 2]
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
