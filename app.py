import streamlit as st
import pandas as pd
import hashlib
from supabase import create_client

from financial_engine import (
    prepare_transactions,
    calculate_monthly_metrics,
    calculate_month_forecast,
    calculate_budget_status,
    calculate_financial_health,
    calculate_safe_to_spend,
    calculate_monthly_recurring_cost,
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

CATEGORY_RULES = {
    "Boodschappen": [
        "albert heijn",
        "ah ",
        "jumbo",
        "plus",
        "lidl",
        "aldi",
        "dirk",
        "coop",
        "supermarkt",
    ],

    "Vervoer": [
        "shell",
        "esso",
        "bp",
        "total",
        "texaco",
        "ns ",
        "ov-chipkaart",
        "uber",
        "bolt",
        "anwb",
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
    ],

    "Entertainment": [
        "netflix",
        "spotify",
        "disney",
        "prime video",
        "pathe",
        "bioscoop",
        "youtube",
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
        "ziggo",
        "kpn",
        "huur",
        "hypotheek",
    ],

    "Verzekeringen": [
        "verzekering",
        "verzekeringen",
        "achmea",
        "interpolis",
        "ohra",
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


CATEGORIES = [
    "Inkomen",
    "Boodschappen",
    "Wonen",
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


# ============================================================
# HELPERS
# ============================================================

def categorize_transaction(description):
    text = str(description).lower()

    for category, keywords in CATEGORY_RULES.items():
        for keyword in keywords:
            if keyword in text:
                return category

    return "Overig"


def normalize_merchant(description):
    text = str(description).lower().strip()

    for keywords in CATEGORY_RULES.values():
        for keyword in keywords:
            if keyword in text:
                return keyword.strip()

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


# ============================================================
# DATABASE - ACCOUNTS
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
# DATABASE - TRANSACTIONS
# ============================================================

def load_transactions(user_id, account_id):
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


# ============================================================
# DATABASE - BUDGETS
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
                    "monthly_limit": float(monthly_limit),
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
# DATABASE - RECURRING
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
            "❌ Terugkerende transacties konden "
            f"niet worden geladen: {e}"
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
            "❌ Terugkerende transacties konden "
            f"niet worden opgeslagen: {e}"
        )
        return []


def update_recurring_active(
    recurring_id,
    active,
):
    try:
        result = (
            supabase
            .table("recurring_transactions")
            .update(
                {
                    "active": active,
                }
            )
            .eq("id", recurring_id)
            .execute()
        )

        return result.data

    except Exception as e:
        st.error(
            f"❌ Status kon niet worden gewijzigd: {e}"
        )
        return None


def delete_recurring_transaction(recurring_id):
    try:
        result = (
            supabase
            .table("recurring_transactions")
            .delete()
            .eq("id", recurring_id)
            .execute()
        )

        return result.data

    except Exception as e:
        st.error(
            "❌ Terugkerende transactie kon "
            f"niet worden verwijderd: {e}"
        )
        return None


# ============================================================
# RECURRING DETECTION
# ============================================================

def detect_recurring_transactions(transactions):

    if not transactions:
        return []

    df = pd.DataFrame(transactions)

    if df.empty:
        return []

    required_columns = [
        "date",
        "merchant",
        "amount",
        "flow",
    ]

    for column in required_columns:
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
        & df["merchant"].notna()
        & (df["merchant"] != "")
    ].copy()

    if df.empty:
        return []

    df = df[
        df["flow"] == "Uitgave"
    ].copy()

    if df.empty:
        return []

    df["amount_abs"] = df["amount"].abs()

    recurring = []

    for merchant, group in df.groupby("merchant"):

        if len(group) < 2:
            continue

        group = group.sort_values("date").copy()

        dates = list(group["date"])
        amounts = list(group["amount_abs"])

        intervals = []

        for i in range(1, len(dates)):
            days = (
                dates[i] - dates[i - 1]
            ).days

            if days > 0:
                intervals.append(days)

        if not intervals:
            continue

        average_interval = (
            sum(intervals) / len(intervals)
        )

        if 25 <= average_interval <= 35:
            frequency = "Maandelijks"

        elif 6 <= average_interval <= 8:
            frequency = "Wekelijks"

        elif 80 <= average_interval <= 100:
            frequency = "Per kwartaal"

        elif 350 <= average_interval <= 380:
            frequency = "Jaarlijks"

        else:
            continue

        average_amount = (
            sum(amounts) / len(amounts)
        )

        if average_amount == 0:
            continue

        max_difference = max(
            abs(amount - average_amount)
            for amount in amounts
        )

        percentage_difference = (
            max_difference / average_amount
        )

        if percentage_difference <= 0.15:
            reliability = "Hoog"

        elif percentage_difference <= 0.30:
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
                category = (
                    categories
                    .mode()
                    .iloc[0]
                )

        last_date = dates[-1]

        next_date = (
            last_date
            + pd.Timedelta(
                days=round(average_interval)
            )
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
                "last_occurrence": (
                    last_date.strftime("%Y-%m-%d")
                ),
                "next_occurrence": (
                    next_date.strftime("%Y-%m-%d")
                ),
                "reliability": reliability,
            }
        )

    return recurring


# ============================================================
# LOGIN
# ============================================================

def show_login():

    st.title("💰 Financial Cockpit")

    st.markdown(
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

                if response.user and response.session:

                    st.session_state["user"] = (
                        response.user
                    )

                    st.session_state["access_token"] = (
                        response.session.access_token
                    )

                    st.session_state["refresh_token"] = (
                        response.session.refresh_token
                    )

                    supabase.auth.set_session(
                        response.session.access_token,
                        response.session.refresh_token,
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


# ============================================================
# RESTORE SESSION
# ============================================================

if (
    "access_token" not in st.session_state
    or "refresh_token" not in st.session_state
):

    st.warning(
        "Je sessie is niet meer beschikbaar."
    )

    if st.button("Opnieuw inloggen"):

        st.session_state.clear()

        st.rerun()

    st.stop()


try:

    supabase.auth.set_session(
        st.session_state["access_token"],
        st.session_state["refresh_token"],
    )

except Exception:

    st.warning(
        "Je sessie is verlopen. Log opnieuw in."
    )

    st.session_state.clear()

    st.stop()


user = st.session_state["user"]
user_id = user.id


# ============================================================
# HEADER
# ============================================================

header_left, header_right = st.columns([5, 1])

with header_left:

    st.title("💰 Financial Cockpit")

with header_right:

    if st.button("Uitloggen"):

        try:
            supabase.auth.sign_out()
        except Exception:
            pass

        st.session_state.clear()

        st.rerun()

st.caption(
    f"Ingelogd als {user.email}"
)


# ============================================================
# ACCOUNTS
# ============================================================

accounts = load_accounts(user_id)

st.subheader("🏦 Mijn rekeningen")

with st.expander(
    "➕ Bankrekening toevoegen",
    expanded=len(accounts) == 0,
):

    account_name = st.text_input(
        "Naam rekening",
        placeholder="ING Betaalrekening",
    )

    bank_name = st.text_input(
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

    if st.button(
        "🏦 Rekening toevoegen",
        type="primary",
        use_container_width=True,
    ):

        if not account_name.strip():

            st.error(
                "Vul een naam voor de rekening in."
            )

        else:

            try:

                result = (
                    supabase
                    .table("accounts")
                    .insert(
                        {
                            "user_id": user_id,
                            "name": account_name.strip(),
                            "bank": bank_name.strip(),
                            "account_type": account_type,
                        }
                    )
                    .execute()
                )

                if result.data:

                    st.success(
                        "✅ Rekening toegevoegd!"
                    )

                    st.rerun()

            except Exception as e:

                st.error(
                    "❌ Rekening kon niet worden "
                    f"toegevoegd: {e}"
                )


if not accounts:

    st.info(
        "Voeg eerst een bankrekening toe."
    )

    st.stop()


# ============================================================
# ACCOUNT SELECTOR
# ============================================================

st.divider()

account_names = {
    account["name"]: account["id"]
    for account in accounts
}

selected_account_name = st.selectbox(
    "Selecteer rekening",
    list(account_names.keys()),
)

selected_account_id = account_names[
    selected_account_name
]


# ============================================================
# LOAD DATA
# ============================================================

transactions = load_transactions(
    user_id,
    selected_account_id,
)

transaction_df = prepare_transactions(
    transactions
)

saved_recurring = load_recurring_transactions(
    user_id,
    selected_account_id,
)

budgets = load_budgets(user_id)


# ============================================================
# CSV IMPORT
# ============================================================

st.divider()

st.subheader("📁 Transacties importeren")

uploaded_file = st.file_uploader(
    "Upload je banktransacties als CSV",
    type=["csv"],
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
                for column in description_options
                if column in df.columns
            ),
            None,
        )

        amount_column = next(
            (
                column
                for column in amount_options
                if column in df.columns
            ),
            None,
        )

        date_column = next(
            (
                column
                for column in date_options
                if column in df.columns
            ),
            None,
        )

        debit_credit_column = next(
            (
                column
                for column in debit_credit_options
                if column in df.columns
            ),
            None,
        )

        if description_column is None:

            st.error(
                "❌ Omschrijvingskolom niet gevonden."
            )

            st.code(
                "\n".join(df.columns)
            )

            st.stop()

        if amount_column is None:

            st.error(
                "❌ Bedragkolom niet gevonden."
            )

            st.code(
                "\n".join(df.columns)
            )

            st.stop()

        if date_column is None:

            st.error(
                "❌ Datumkolom niet gevonden."
            )

            st.code(
                "\n".join(df.columns)
            )

            st.stop()

        if debit_credit_column is None:

            st.error(
                "❌ Debit/Credit kolom niet gevonden."
            )

            st.code(
                "\n".join(df.columns)
            )

            st.stop()

        # ----------------------------------------------------
        # DATE
        # ----------------------------------------------------

        raw_dates = (
            df[date_column]
            .astype(str)
            .str.strip()
        )

        df[date_column] = pd.to_datetime(
            raw_dates,
            format="%Y%m%d",
            errors="coerce",
        )

        missing_dates = df[date_column].isna()

        if missing_dates.any():

            df.loc[
                missing_dates,
                date_column,
            ] = pd.to_datetime(
                raw_dates[missing_dates],
                errors="coerce",
                dayfirst=True,
            )

        # ----------------------------------------------------
        # AMOUNT
        # ----------------------------------------------------

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
        )

        amount_series = (
            amount_series
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

        df[amount_column] = pd.to_numeric(
            amount_series,
            errors="coerce",
        )

        # ----------------------------------------------------
        # FLOW
        # ----------------------------------------------------

        df["transaction_type"] = (
            df[debit_credit_column]
            .astype(str)
            .str.strip()
            .str.lower()
        )

        df["flow"] = df[
            "transaction_type"
        ].apply(
            lambda x:
                "Inkomst"
                if x == "credit"
                else
                "Uitgave"
                if x == "debit"
                else
                "Onbekend"
        )

        # ----------------------------------------------------
        # MERCHANT
        # ----------------------------------------------------

        df["merchant"] = df[
            description_column
        ].apply(
            normalize_merchant
        )

        # ----------------------------------------------------
        # CATEGORY
        # ----------------------------------------------------

        df["category"] = df[
            description_column
        ].apply(
            categorize_transaction
        )

        # ----------------------------------------------------
        # HASH
        # ----------------------------------------------------

        df["transaction_hash"] = df.apply(
            lambda row:
                create_transaction_hash(
                    row[date_column],
                    row[description_column],
                    row[amount_column],
                    row["transaction_type"],
                ),
            axis=1,
        )

        # ----------------------------------------------------
        # DUPLICATES
        # ----------------------------------------------------

        before_count = len(df)

        df = df.drop_duplicates(
            subset=[
                "transaction_hash"
            ],
            keep="first",
        )

        duplicate_count = (
            before_count - len(df)
        )

        if duplicate_count > 0:

            st.info(
                f"ℹ️ {duplicate_count} dubbele "
                "transacties overgeslagen."
            )

        # ----------------------------------------------------
        # INVALID
        # ----------------------------------------------------

        df = df[
            df[date_column].notna()
            & df[amount_column].notna()
            & df["flow"].isin(
                ["Inkomst", "Uitgave"]
            )
        ].copy()

        if df.empty:

            st.warning(
                "⚠️ Geen geldige transacties gevonden."
            )

        else:

            st.success(
                f"✅ {len(df):,} geldige transacties gevonden"
            )

            preview_columns = [
                date_column,
                description_column,
                "merchant",
                amount_column,
                "flow",
                "category",
            ]

            st.dataframe(
                df[preview_columns],
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

                transactions_to_insert = []

                for _, row in df.iterrows():

                    transactions_to_insert.append(
                        {
                            "user_id": user_id,
                            "account_id": selected_account_id,
                            "date": row[
                                date_column
                            ].strftime("%Y-%m-%d"),
                            "description": str(
                                row[
                                    description_column
                                ]
                            ),
                            "merchant": str(
                                row["merchant"]
                            ),
                            "amount": float(
                                row[
                                    amount_column
                                ]
                            ),
                            "flow": row["flow"],
                            "category": row["category"],
                            "transaction_type": row[
                                "transaction_type"
                            ],
                            "transaction_hash": row[
                                "transaction_hash"
                            ],
                        }
                    )

                try:

                    result = (
                        supabase
                        .table("transactions")
                        .upsert(
                            transactions_to_insert,
                            on_conflict=(
                                "user_id,"
                                "transaction_hash"
                            ),
                        )
                        .execute()
                    )

                    st.success(
                        f"✅ {len(result.data or [])} "
                        "transacties verwerkt."
                    )

                    st.rerun()

                except Exception as e:

                    st.error(
                        "❌ Transacties konden niet "
                        f"worden opgeslagen: {e}"
                    )

    except Exception as e:

        st.error(
            "❌ Het CSV-bestand kon niet "
            f"worden verwerkt: {e}"
        )


# ============================================================
# FINANCIAL COCKPIT
# ============================================================

st.divider()

st.header("📊 Financial Cockpit")

if transaction_df.empty:

    st.info(
        "Upload eerst transacties om je Financial Cockpit te vullen."
    )

else:

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

    if current_period in available_periods:

        default_index = list(
            available_periods
        ).index(current_period)

    else:

        default_index = 0

    selected_period = st.selectbox(
        "📅 Selecteer maand",
        available_periods,
        index=default_index,
        format_func=lambda x:
            x.strftime("%B %Y"),
    )

    metrics = calculate_monthly_metrics(
        transaction_df,
        selected_period,
    )

    income = metrics["income"]
    expenses = metrics["expenses"]
    net = metrics["net"]

    col1, col2, col3, col4 = st.columns(4)

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

    # --------------------------------------------------------
    # CASHFLOW
    # --------------------------------------------------------

    st.subheader("📈 Cashflow")

    month_df = transaction_df[
        transaction_df["date"]
        .dt.to_period("M")
        == selected_period
    ].copy()

    daily = (
        month_df
        .groupby("date")
        .apply(
            lambda x:
                x.loc[
                    x["flow"] == "Inkomst",
                    "amount",
                ].sum()
                -
                x.loc[
                    x["flow"] == "Uitgave",
                    "amount",
                ].abs().sum()
        )
    )

    if not daily.empty:

        cumulative = daily.cumsum()

        st.line_chart(cumulative)

    # --------------------------------------------------------
    # CATEGORY + MERCHANT
    # --------------------------------------------------------

    left, right = st.columns(2)

    with left:

        st.subheader(
            "💸 Uitgaven per categorie"
        )

        expense_df = month_df[
            month_df["flow"] == "Uitgave"
        ].copy()

        if not expense_df.empty:

            expense_df["amount"] = (
                expense_df["amount"].abs()
            )

            category_summary = (
                expense_df
                .groupby("category")["amount"]
                .sum()
                .sort_values(ascending=False)
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
                .groupby("merchant")["amount"]
                .sum()
                .sort_values(
                    ascending=False
                )
                .head(10)
            )

            merchant_summary.index = (
                merchant_summary
                .index
                .str.title()
            )

            st.bar_chart(
                merchant_summary
            )


# ============================================================
# FINANCIAL HEALTH
# ============================================================

st.divider()

st.header("🧠 Financial Health")

if not transaction_df.empty:

    active_recurring = [
        item
        for item in saved_recurring
        if item.get("active", True)
    ]

    budget_status = calculate_budget_status(
        transaction_df,
        budgets,
        selected_period,
    )

    forecast = calculate_month_forecast(
        transaction_df,
        selected_period,
        active_recurring,
        budgets,
    )

    health = calculate_financial_health(
        forecast,
        budget_status,
    )

    if forecast and health:

        col1, col2, col3, col4 = st.columns(4)

        with col1:

            st.metric(
                "Verwachte inkomsten",
                euro(
                    forecast["projected_income"]
                ),
            )

        with col2:

            st.metric(
                "Verwachte uitgaven",
                euro(
                    forecast["projected_expenses"]
                ),
            )

        with col3:

            st.metric(
                "Verwacht netto",
                euro(
                    forecast["projected_net"]
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

        projected_net = forecast[
            "projected_net"
        ]

        if projected_net >= 0:

            st.success(
                f"🟢 Je hebt waarschijnlijk "
                f"**{euro(projected_net)}** "
                "over aan het einde van deze maand."
            )

        else:

            st.error(
                f"🔴 Je komt deze maand waarschijnlijk "
                f"**{euro(abs(projected_net))}** tekort."
            )

        safe_to_spend = calculate_safe_to_spend(
            forecast,
            buffer=0,
        )

        st.info(
            f"💳 Je kunt volgens deze eerste "
            f"berekening ongeveer **{euro(safe_to_spend)}** "
            "uitgeven zonder dat je maandresultaat negatief wordt."
        )

        if forecast[
            "recurring_remaining"
        ] > 0:

            st.caption(
                "🔄 Verwachte resterende "
                "terugkerende betalingen: "
                f"{euro(forecast['recurring_remaining'])}"
            )

        if health["warnings"]:

            st.subheader(
                "⚠️ Aandachtspunten"
            )

            for warning in health["warnings"]:

                st.warning(warning)

        else:

            st.success(
                "✅ Op basis van de huidige gegevens "
                "zijn er geen belangrijke aandachtspunten."
            )


# ============================================================
# RECURRING TRANSACTIONS
# ============================================================

st.divider()

st.header("🔄 Terugkerende betalingen")

st.caption(
    "Financial Cockpit zoekt naar betalingen die regelmatig terugkomen."
)

if st.button(
    "🔍 Terugkerende betalingen detecteren",
    type="primary",
    use_container_width=True,
):

    detected = detect_recurring_transactions(
        transactions
    )

    if detected:

        saved = save_recurring_transactions(
            user_id,
            selected_account_id,
            detected,
        )

        if saved:

            st.success(
                f"✅ {len(saved)} terugkerende "
                "betalingen opgeslagen."
            )

            st.rerun()

    else:

        st.info(
            "Geen duidelijke terugkerende betalingen gevonden."
        )


saved_recurring = load_recurring_transactions(
    user_id,
    selected_account_id,
)

if saved_recurring:

    active_recurring = [
        item
        for item in saved_recurring
        if item.get("active", True)
    ]

    inactive_recurring = [
        item
        for item in saved_recurring
        if not item.get("active", True)
    ]

    monthly_recurring_cost = (
        calculate_monthly_recurring_cost(
            saved_recurring
        )
    )

    col1, col2, col3 = st.columns(3)

    with col1:

        st.metric(
            "🔄 Actieve betalingen",
            len(active_recurring),
        )

    with col2:

        st.metric(
            "💸 Geschatte maandlasten",
            euro(monthly_recurring_cost),
        )

    with col3:

        st.metric(
            "⏸️ Inactief",
            len(inactive_recurring),
        )

    # --------------------------------------------------------
    # ACTIVE
    # --------------------------------------------------------

    for recurring in active_recurring:

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

        expected_amount = float(
            recurring.get(
                "expected_amount",
                0,
            ) or 0
        )

        next_occurrence = recurring.get(
            "next_occurrence",
            "-",
        )

        recurring_id = recurring.get("id")

        with st.container(border=True):

            col1, col2, col3, col4 = st.columns(
                [3, 1.5, 1.5, 1.5]
            )

            with col1:

                st.markdown(
                    f"**{merchant.title()}**"
                )

                st.caption(
                    f"{category} · {frequency}"
                )

            with col2:

                st.metric(
                    "Bedrag",
                    euro(expected_amount),
                )

            with col3:

                st.metric(
                    "Volgende",
                    next_occurrence,
                )

            with col4:

                reliability = recurring.get(
                    "reliability",
                    "-",
                )

                st.metric(
                    "Betrouwbaarheid",
                    reliability,
                )

            button_col1, button_col2 = st.columns(2)

            with button_col1:

                if st.button(
                    "⏸️ Deactiveren",
                    key=f"deactivate_{recurring_id}",
                    use_container_width=True,
                ):

                    update_recurring_active(
                        recurring_id,
                        False,
                    )

                    st.rerun()

            with button_col2:

                if st.button(
                    "🗑️ Verwijderen",
                    key=f"delete_{recurring_id}",
                    use_container_width=True,
                ):

                    delete_recurring_transaction(
                        recurring_id
                    )

                    st.rerun()

    # --------------------------------------------------------
    # INACTIVE
    # --------------------------------------------------------

    if inactive_recurring:

        with st.expander(
            "⏸️ Inactieve terugkerende betalingen"
        ):

            for recurring in inactive_recurring:

                merchant = recurring.get(
                    "merchant",
                    "Onbekend",
                )

                expected_amount = float(
                    recurring.get(
                        "expected_amount",
                        0,
                    ) or 0
                )

                frequency = recurring.get(
                    "frequency",
                    "Onbekend",
                )

                recurring_id = recurring.get("id")

                col1, col2, col3 = st.columns(
                    [4, 2, 2]
                )

                with col1:

                    st.markdown(
                        f"**{merchant.title()}**"
                    )

                    st.caption(frequency)

                with col2:

                    st.write(
                        euro(expected_amount)
                    )

                with col3:

                    if st.button(
                        "▶️ Activeren",
                        key=f"activate_{recurring_id}",
                        use_container_width=True,
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
# BUDGETS
# ============================================================

st.divider()

st.header("🎯 Mijn budgetten")

st.markdown(
    "Stel per categorie een maximaal bedrag per maand in."
)

budgets = load_budgets(user_id)

with st.expander("➕ Budget instellen"):

    budget_category = st.selectbox(
        "Categorie",
        [
            category
            for category in CATEGORIES
            if category != "Inkomen"
        ],
        key="budget_category",
    )

    budget_amount = st.number_input(
        "Maandelijks budget",
        min_value=0.0,
        step=25.0,
        value=250.0,
        format="%.2f",
        key="budget_amount",
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
                f"✅ Budget voor {budget_category} opgeslagen."
            )

            st.rerun()


# ============================================================
# BUDGET OVERVIEW
# ============================================================

if budgets and not transaction_df.empty:

    budget_status = calculate_budget_status(
        transaction_df,
        budgets,
        selected_period,
    )

    st.subheader(
        f"🎯 Budgetten voor "
        f"{selected_period.strftime('%B %Y')}"
    )

    for budget in budget_status:

        category = budget["category"]
        budget_amount = budget["budget"]
        spent = budget["spent"]
        remaining = budget["remaining"]
        percentage = budget["percentage"]

        st.markdown(
            f"### {category}"
        )

        col1, col2, col3 = st.columns(3)

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
            max(percentage / 100, 0),
            1,
        )

        st.progress(progress)

        if budget["over_budget"]:

            st.error(
                f"🔴 Budget overschreden met "
                f"{euro(abs(remaining))}"
            )

        elif percentage >= 80:

            st.warning(
                f"🟠 {percentage:.0f}% van het "
                "budget gebruikt."
            )

        else:

            st.success(
                f"🟢 {percentage:.0f}% van het "
                "budget gebruikt."
            )

        st.divider()

elif not budgets:

    st.info(
        "Je hebt nog geen budgetten ingesteld."
    )

# ============================================================
# TRANSACTION MANAGEMENT
# ============================================================

def update_transaction(
    transaction_id,
    category,
    merchant=None,
):
    """
    Werk een bestaande transactie bij.
    """

    try:

        update_data = {
            "category": category,
        }

        if merchant is not None:
            update_data["merchant"] = merchant.strip()

        result = (
            supabase
            .table("transactions")
            .update(update_data)
            .eq("id", transaction_id)
            .eq("user_id", user_id)
            .execute()
        )

        return result.data

    except Exception as e:

        st.error(
            f"❌ Transactie kon niet worden bijgewerkt: {e}"
        )

        return None


def delete_transaction(transaction_id):
    """
    Verwijder een transactie.
    """

    try:

        result = (
            supabase
            .table("transactions")
            .delete()
            .eq("id", transaction_id)
            .eq("user_id", user_id)
            .execute()
        )

        return result.data

    except Exception as e:

        st.error(
            f"❌ Transactie kon niet worden verwijderd: {e}"
        )

        return None


# ============================================================
# ALL TRANSACTIONS
# ============================================================

st.divider()

st.header(
    "💳 Mijn transacties"
)

if transactions:

    transactions_display = pd.DataFrame(
        transactions
    ).copy()

    # --------------------------------------------------------
    # PREPARE DATA
    # --------------------------------------------------------

    transactions_display["date"] = pd.to_datetime(
        transactions_display["date"],
        errors="coerce",
    )

    transactions_display["amount"] = pd.to_numeric(
        transactions_display["amount"],
        errors="coerce",
    )

    # --------------------------------------------------------
    # FILTERS
    # --------------------------------------------------------

    filter_col1, filter_col2, filter_col3 = st.columns(3)

    with filter_col1:

        search_term = st.text_input(
            "🔎 Zoek",
            placeholder="Bijv. Albert Heijn",
        )

    with filter_col2:

        categories_available = sorted(
            transactions_display[
                "category"
            ]
            .dropna()
            .astype(str)
            .unique()
            .tolist()
        )

        selected_category = st.selectbox(
            "Categorie",
            ["Alle categorieën"]
            + categories_available,
        )

    with filter_col3:

        selected_flow = st.selectbox(
            "Type",
            [
                "Alles",
                "Inkomsten",
                "Uitgaven",
            ],
        )

    # --------------------------------------------------------
    # APPLY FILTERS
    # --------------------------------------------------------

    filtered_df = transactions_display.copy()

    if search_term:

        search_mask = (
            filtered_df[
                "description"
            ]
            .astype(str)
            .str.contains(
                search_term,
                case=False,
                na=False,
            )
            |
            filtered_df[
                "merchant"
            ]
            .astype(str)
            .str.contains(
                search_term,
                case=False,
                na=False,
            )
        )

        filtered_df = filtered_df[
            search_mask
        ]

    if selected_category != "Alle categorieën":

        filtered_df = filtered_df[
            filtered_df["category"]
            == selected_category
        ]

    if selected_flow == "Inkomsten":

        filtered_df = filtered_df[
            filtered_df["flow"]
            == "Inkomst"
        ]

    elif selected_flow == "Uitgaven":

        filtered_df = filtered_df[
            filtered_df["flow"]
            == "Uitgave"
        ]

    # --------------------------------------------------------
    # RESULT COUNT
    # --------------------------------------------------------

    st.caption(
        f"{len(filtered_df):,} transacties gevonden"
    )

    # --------------------------------------------------------
    # TRANSACTION EDITOR
    # --------------------------------------------------------

    for _, transaction in filtered_df.iterrows():

        transaction_id = transaction.get(
            "id"
        )

        date = transaction.get(
            "date"
        )

        description = str(
            transaction.get(
                "description",
                "",
            )
        )

        merchant = str(
            transaction.get(
                "merchant",
                "",
            )
        )

        amount = float(
            transaction.get(
                "amount",
                0,
            ) or 0
        )

        flow = transaction.get(
            "flow",
            "",
        )

        category = transaction.get(
            "category",
            "Overig",
        )

        # ----------------------------------------------------
        # DISPLAY
        # ----------------------------------------------------

        with st.container(
            border=True
        ):

            col1, col2, col3, col4 = st.columns(
                [
                    1.2,
                    3,
                    1.5,
                    1.8,
                ]
            )

            with col1:

                if pd.notna(date):

                    st.write(
                        date.strftime(
                            "%d-%m-%Y"
                        )
                    )

            with col2:

                st.markdown(
                    f"**{merchant.title()}**"
                )

                if description != merchant:

                    st.caption(
                        description
                    )

            with col3:

                if flow == "Inkomst":

                    st.metric(
                        "Bedrag",
                        euro(amount),
                    )

                else:

                    st.metric(
                        "Bedrag",
                        euro(abs(amount)),
                    )

            with col4:

                if flow == "Inkomst":

                    st.success(
                        "Inkomst"
                    )

                else:

                    st.caption(
                        "Uitgave"
                    )

            # ------------------------------------------------
            # EDIT
            # ------------------------------------------------

            edit_col1, edit_col2, edit_col3 = st.columns(
                [
                    3,
                    3,
                    1.5,
                ]
            )

            with edit_col1:

                new_category = st.selectbox(
                    "Categorie",
                    CATEGORIES,
                    index=(
                        CATEGORIES.index(category)
                        if category in CATEGORIES
                        else CATEGORIES.index("Overig")
                    ),
                    key=f"category_{transaction_id}",
                )

            with edit_col2:

                new_merchant = st.text_input(
                    "Merchant",
                    value=merchant,
                    key=f"merchant_{transaction_id}",
                )

            with edit_col3:

                st.write("")

                if st.button(
                    "💾 Opslaan",
                    key=f"save_transaction_{transaction_id}",
                    use_container_width=True,
                ):

                    result = update_transaction(
                        transaction_id,
                        new_category,
                        new_merchant,
                    )

                    if result is not None:

                        st.success(
                            "Opgeslagen"
                        )

                        st.rerun()

            # ------------------------------------------------
            # DELETE
            # ------------------------------------------------

            with st.expander(
                "⚙️ Meer opties"
            ):

                if st.button(
                    "🗑️ Transactie verwijderen",
                    key=f"delete_transaction_{transaction_id}",
                ):

                    result = delete_transaction(
                        transaction_id
                    )

                    if result is not None:

                        st.success(
                            "Transactie verwijderd."
                        )

                        st.rerun()

else:

    st.info(
        "Nog geen transacties voor deze rekening."
    )
