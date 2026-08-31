import streamlit as st
import pandas as pd
import hashlib
from datetime import date
from supabase import create_client


# ============================================================
# CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="Financial Cockpit",
    page_icon="💰",
    layout="wide"
)


# ============================================================
# SUPABASE
# ============================================================

@st.cache_resource
def get_supabase():

    return create_client(
        st.secrets["SUPABASE_URL"],
        st.secrets["SUPABASE_KEY"]
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
        "supermarkt"
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
        "anwb"
    ],

    "Horeca": [
        "restaurant",
        "cafe",
        "café",
        "mcdonald",
        "burger king",
        "starbucks",
        "thuisbezorgd",
        "uber eats"
    ],

    "Entertainment": [
        "netflix",
        "spotify",
        "disney",
        "prime video",
        "pathe",
        "bioscoop",
        "youtube"
    ],

    "Abonnementen": [
        "subscription",
        "membership",
        "abonnement"
    ],

    "Wonen": [
        "vattenfall",
        "essent",
        "eneco",
        "ziggo",
        "kpn",
        "huur",
        "hypotheek"
    ],

    "Verzekeringen": [
        "verzekering",
        "verzekeringen",
        "achmea",
        "interpolis",
        "ohra"
    ],

    "Gezondheid": [
        "apotheek",
        "ziekenhuis",
        "tandarts",
        "dokter",
        "huisarts"
    ],

    "Kleding": [
        "zara",
        "h&m",
        "uniqlo",
        "nike",
        "adidas"
    ],

    "Persoonlijke verzorging": [
        "kapper",
        "barber",
        "rituals",
        "douglas"
    ],

    "Kinderen": [
        "school",
        "kinderopvang",
        "creche",
        "crèche",
        "kinderdagverblijf"
    ],

    "Vakantie": [
        "booking.com",
        "airbnb",
        "hotel",
        "camping"
    ],

    "Inkomen": [
        "salaris",
        "salary",
        "loon"
    ]
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
    "Overig"
]


# ============================================================
# HELPER FUNCTIONS
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
    transaction_type
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
# DATABASE FUNCTIONS
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


def load_transactions(
    user_id,
    account_id
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
    monthly_limit
):

    try:

        result = (
            supabase
            .table("budgets")
            .upsert(
                {
                    "user_id": user_id,
                    "category": category,
                    "monthly_limit": float(monthly_limit)
                },
                on_conflict="user_id,category"
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
# RECURRING TRANSACTIONS
# ============================================================

def load_recurring_transactions(
    user_id,
    account_id
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


def detect_recurring_transactions(
    transactions
):

    if not transactions:
        return []

    df = pd.DataFrame(transactions)

    if df.empty:
        return []

    required_columns = [
        "date",
        "merchant",
        "amount",
        "flow"
    ]

    for column in required_columns:

        if column not in df.columns:
            return []

    df = df.copy()

    df["date"] = pd.to_datetime(
        df["date"],
        errors="coerce"
    )

    df["amount"] = pd.to_numeric(
        df["amount"],
        errors="coerce"
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
                    2
                ),
                "occurrences": len(group),
                "last_occurrence":
                    last_date.strftime("%Y-%m-%d"),
                "next_occurrence":
                    next_date.strftime("%Y-%m-%d"),
                "reliability": reliability
            }
        )

    return recurring


def save_recurring_transactions(
    user_id,
    account_id,
    recurring_transactions
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
                "last_occurrence":
                    recurring["last_occurrence"],
                "next_occurrence":
                    recurring["next_occurrence"],
                "active": True
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
                )
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
    active
):

    try:

        result = (
            supabase
            .table("recurring_transactions")
            .update(
                {
                    "active": active
                }
            )
            .eq(
                "id",
                recurring_id
            )
            .execute()
        )

        return result.data

    except Exception as e:

        st.error(
            f"❌ Status kon niet worden gewijzigd: {e}"
        )

        return None


def delete_recurring_transaction(
    recurring_id
):

    try:

        result = (
            supabase
            .table("recurring_transactions")
            .delete()
            .eq(
                "id",
                recurring_id
            )
            .execute()
        )

        return result.data

    except Exception as e:

        st.error(
            f"❌ Terugkerende transactie kon "
            f"niet worden verwijderd: {e}"
        )

        return None


# ============================================================
# FORECAST FUNCTIONS
# ============================================================

def monthly_recurring_cost(
    recurring_transactions
):

    total = 0.0

    for item in recurring_transactions:

        if not item.get("active", True):
            continue

        amount = float(
            item.get(
                "expected_amount",
                0
            ) or 0
        )

        frequency = item.get(
            "frequency",
            ""
        )

        if frequency == "Wekelijks":

            total += amount * 52 / 12

        elif frequency == "Maandelijks":

            total += amount

        elif frequency == "Per kwartaal":

            total += amount / 3

        elif frequency == "Jaarlijks":

            total += amount / 12

    return total


def calculate_forecast(
    transactions_df,
    selected_period,
    recurring_transactions
):

    if transactions_df.empty:
        return None

    df = transactions_df.copy()

    df["date"] = pd.to_datetime(
        df["date"],
        errors="coerce"
    )

    df["amount"] = pd.to_numeric(
        df["amount"],
        errors="coerce"
    )

    df = df[df["date"].notna()].copy()

    if df.empty:
        return None

    monthly = (
        df
        .groupby(
            df["date"].dt.to_period("M")
        )
        .apply(
            lambda x: pd.Series(
                {
                    "income": x.loc[
                        x["flow"] == "Inkomst",
                        "amount"
                    ].sum(),

                    "expenses": x.loc[
                        x["flow"] == "Uitgave",
                        "amount"
                    ].abs().sum()
                }
            )
        )
    )

    if monthly.empty:
        return None

    current = selected_period

    current_month = df[
        df["date"].dt.to_period("M") == current
    ]

    income_current = current_month.loc[
        current_month["flow"] == "Inkomst",
        "amount"
    ].sum()

    expenses_current = current_month.loc[
        current_month["flow"] == "Uitgave",
        "amount"
    ].abs().sum()

    today = pd.Timestamp.today()

    if current == today.to_period("M"):

        days_in_month = today.days_in_month

        elapsed_days = max(
            today.day,
            1
        )

        projected_expenses = (
            expenses_current
            / elapsed_days
            * days_in_month
        )

        projected_income = (
            income_current
            if income_current > 0
            else 0
        )

    else:

        projected_expenses = expenses_current
        projected_income = income_current

    recurring_monthly = monthly_recurring_cost(
        recurring_transactions
    )

    projected_expenses = max(
        projected_expenses,
        recurring_monthly
    )

    projected_net = (
        projected_income
        - projected_expenses
    )

    return {
        "income": projected_income,
        "expenses": projected_expenses,
        "net": projected_net,
        "recurring": recurring_monthly
    }


# ============================================================
# CSV IMPORT
# ============================================================

def parse_csv(uploaded_file):

    df = pd.read_csv(
        uploaded_file,
        sep=None,
        engine="python"
    )

    df.columns = (
        df.columns
        .astype(str)
        .str.strip()
        .str.lower()
    )

    df = df.dropna(
        axis=1,
        how="all"
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
        "transactie"
    ]

    amount_options = [
        "amount",
        "amount (eur)",
        "amount (euro)",
        "bedrag",
        "waarde",
        "transactiebedrag"
    ]

    date_options = [
        "date",
        "datum",
        "transaction date",
        "transactiedatum"
    ]

    debit_credit_options = [
        "debit/credit",
        "debit credit",
        "debit_credit",
        "type"
    ]

    description_column = next(
        (
            column
            for column in description_options
            if column in df.columns
        ),
        None
    )

    amount_column = next(
        (
            column
            for column in amount_options
            if column in df.columns
        ),
        None
    )

    date_column = next(
        (
            column
            for column in date_options
            if column in df.columns
        ),
        None
    )

    debit_credit_column = next(
        (
            column
            for column in debit_credit_options
            if column in df.columns
        ),
        None
    )

    missing = []

    if description_column is None:
        missing.append("omschrijving")

    if amount_column is None:
        missing.append("bedrag")

    if date_column is None:
        missing.append("datum")

    if debit_credit_column is None:
        missing.append("debit/credit")

    if missing:

        raise ValueError(
            "Deze kolommen konden niet worden gevonden: "
            + ", ".join(missing)
            + "\n\nGevonden kolommen:\n"
            + ", ".join(df.columns)
        )

    # DATE

    raw_dates = (
        df[date_column]
        .astype(str)
        .str.strip()
    )

    parsed_dates = pd.to_datetime(
        raw_dates,
        format="%Y%m%d",
        errors="coerce"
    )

    fallback_dates = pd.to_datetime(
        raw_dates,
        errors="coerce",
        dayfirst=True
    )

    df[date_column] = parsed_dates.fillna(
        fallback_dates
    )

    # AMOUNT

    amount_text = (
        df[amount_column]
        .astype(str)
        .str.strip()
        .str.replace(
            "€",
            "",
            regex=False
        )
        .str.replace(
            " ",
            "",
            regex=False
        )
    )

    # European format:
    # 1.234,56 -> 1234.56

    amount_text = (
        amount_text
        .str.replace(
            ".",
            "",
            regex=False
        )
        .str.replace(
            ",",
            ".",
            regex=False
        )
    )

    df[amount_column] = pd.to_numeric(
        amount_text,
        errors="coerce"
    )

    # FLOW

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
            if x in [
                "credit",
                "cr",
                "c",
                "income"
            ]
            else
            "Uitgave"
            if x in [
                "debit",
                "dr",
                "d",
                "expense"
            ]
            else
            "Onbekend"
    )

    # MERCHANT

    df["merchant"] = df[
        description_column
    ].apply(
        normalize_merchant
    )

    # CATEGORY

    df["category"] = df[
        description_column
    ].apply(
        categorize_transaction
    )

    # HASH

    df["transaction_hash"] = df.apply(
        lambda row:
            create_transaction_hash(
                row[date_column],
                row[description_column],
                row[amount_column],
                row["transaction_type"]
            ),
        axis=1
    )

    # REMOVE DUPLICATES

    df = df.drop_duplicates(
        subset=["transaction_hash"],
        keep="first"
    )

    # REMOVE INVALID

    df = df[
        df[date_column].notna()
        & df[amount_column].notna()
    ].copy()

    return (
        df,
        date_column,
        description_column,
        amount_column
    )


# ============================================================
# LOGIN
# ============================================================

def show_login():

    st.title(
        "💰 Financial Cockpit"
    )

    st.markdown(
        "Log in om je persoonlijke financiële dashboard te bekijken."
    )

    login_tab, register_tab = st.tabs(
        [
            "Inloggen",
            "Account aanmaken"
        ]
    )

    with login_tab:

        email = st.text_input(
            "E-mailadres",
            key="login_email"
        )

        password = st.text_input(
            "Wachtwoord",
            type="password",
            key="login_password"
        )

        if st.button(
            "Inloggen",
            type="primary",
            use_container_width=True
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
                            "password": password
                        }
                    )
                )

                if (
                    response.user
                    and response.session
                ):

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
                        response.session.refresh_token
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
            key="register_email"
        )

        password = st.text_input(
            "Wachtwoord",
            type="password",
            key="register_password"
        )

        password_repeat = st.text_input(
            "Wachtwoord herhalen",
            type="password",
            key="register_password_repeat"
        )

        if st.button(
            "Account aanmaken",
            use_container_width=True
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
                            "password": password
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
    "access_token" not in st.session_state
    or
    "refresh_token" not in st.session_state
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
        st.session_state["access_token"],
        st.session_state["refresh_token"]
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

header_left, header_right = st.columns(
    [5, 1]
)

with header_left:

    st.title(
        "💰 Financial Cockpit"
    )

with header_right:

    if st.button(
        "Uitloggen"
    ):

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

accounts = load_accounts(
    user_id
)

st.subheader(
    "🏦 Mijn rekeningen"
)

with st.expander(
    "➕ Bankrekening toevoegen",
    expanded=len(accounts) == 0
):

    account_name = st.text_input(
        "Naam rekening",
        placeholder="ING Betaalrekening"
    )

    bank_name = st.text_input(
        "Bank",
        placeholder="ING"
    )

    account_type = st.selectbox(
        "Type rekening",
        [
            "Betaalrekening",
            "Spaarrekening",
            "Creditcard",
            "Beleggingsrekening",
            "Anders"
        ]
    )

    if st.button(
        "🏦 Rekening toevoegen",
        type="primary",
        use_container_width=True
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
                            "account_type": account_type
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
                    "❌ Rekening kon niet worden toegevoegd: "
                    f"{e}"
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
    list(account_names.keys())
)

selected_account_id = account_names[
    selected_account_name
]


# ============================================================
# CSV IMPORT
# ============================================================

st.divider()

st.subheader(
    "📁 Transacties importeren"
)

uploaded_file = st.file_uploader(
    "Upload je banktransacties als CSV",
    type=["csv"]
)

if uploaded_file is not None:

    try:

        (
            df,
            date_column,
            description_column,
            amount_column
        ) = parse_csv(
            uploaded_file
        )

        st.success(
            f"✅ {len(df):,} geldige transacties gevonden."
        )

        preview_columns = [
            date_column,
            description_column,
            "merchant",
            amount_column,
            "flow",
            "category"
        ]

        st.dataframe(
            df[preview_columns],
            use_container_width=True,
            hide_index=True
        )

        if st.button(
            "💾 Transacties opslaan",
            type="primary",
            use_container_width=True
        ):

            transactions_to_insert = []

            for _, row in df.iterrows():

                transactions_to_insert.append(
                    {
                        "user_id":
                            user_id,

                        "account_id":
                            selected_account_id,

                        "date":
                            row[date_column].strftime(
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
                                row["merchant"]
                            ),

                        "amount":
                            float(
                                row[amount_column]
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
                            ]
                    }
                )

            if transactions_to_insert:

                try:

                    result = (
                        supabase
                        .table("transactions")
                        .upsert(
                            transactions_to_insert,
                            on_conflict=(
                                "user_id,"
                                "transaction_hash"
                            )
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
                        "❌ Transacties konden niet worden opgeslagen: "
                        f"{e}"
                    )

    except Exception as e:

        st.error(
            f"❌ Het CSV-bestand kon niet worden verwerkt: {e}"
        )


# ============================================================
# LOAD DATA
# ============================================================

transactions = load_transactions(
    user_id,
    selected_account_id
)

saved_recurring = load_recurring_transactions(
    user_id,
    selected_account_id
)

budgets = load_budgets(
    user_id
)


# ============================================================
# PREPARE DATAFRAME
# ============================================================

if transactions:

    transaction_df = pd.DataFrame(
        transactions
    )

    transaction_df["date"] = pd.to_datetime(
        transaction_df["date"],
        errors="coerce"
    )

    transaction_df["amount"] = pd.to_numeric(
        transaction_df["amount"],
        errors="coerce"
    )

    transaction_df = transaction_df[
        transaction_df["date"].notna()
        & transaction_df["amount"].notna()
    ].copy()

else:

    transaction_df = pd.DataFrame()


# ============================================================
# DASHBOARD
# ============================================================

st.divider()

st.header(
    "📊 Financial Dashboard"
)

if not transaction_df.empty:

    available_months = sorted(
        transaction_df[
            "date"
        ]
        .dt.to_period("M")
        .unique(),
        reverse=True
    )

    month_labels = [
        period.strftime("%B %Y")
        for period in available_months
    ]

    selected_month_index = st.selectbox(
        "📅 Maand",
        range(len(available_months)),
        format_func=lambda x:
            month_labels[x]
    )

    selected_period = available_months[
        selected_month_index
    ]

    current_month_df = transaction_df[
        transaction_df["date"]
        .dt.to_period("M")
        == selected_period
    ].copy()

    income = current_month_df.loc[
        current_month_df["flow"] == "Inkomst",
        "amount"
    ].sum()

    expenses = current_month_df.loc[
        current_month_df["flow"] == "Uitgave",
        "amount"
    ].abs().sum()

    net = income - expenses

    savings_rate = (
        net / income * 100
        if income > 0
        else 0
    )

    # --------------------------------------------------------
    # PREVIOUS MONTH
    # --------------------------------------------------------

    previous_period = (
        selected_period - 1
    )

    previous_df = transaction_df[
        transaction_df["date"]
        .dt.to_period("M")
        == previous_period
    ]

    previous_income = previous_df.loc[
        previous_df["flow"] == "Inkomst",
        "amount"
    ].sum()

    previous_expenses = previous_df.loc[
        previous_df["flow"] == "Uitgave",
        "amount"
    ].abs().sum()

    previous_net = (
        previous_income
        - previous_expenses
    )

    # --------------------------------------------------------
    # KPI
    # --------------------------------------------------------

    col1, col2, col3, col4 = st.columns(4)

    with col1:

        st.metric(
            "💰 Inkomsten",
            f"€ {income:,.2f}",
            delta=(
                f"€ {income - previous_income:,.2f}"
                if previous_income != 0
                else None
            )
        )

    with col2:

        st.metric(
            "💸 Uitgaven",
            f"€ {expenses:,.2f}",
            delta=(
                f"€ {expenses - previous_expenses:,.2f}"
                if previous_expenses != 0
                else None
            ),
            delta_color="inverse"
        )

    with col3:

        st.metric(
            "📈 Netto",
            f"€ {net:,.2f}",
            delta=(
                f"€ {net - previous_net:,.2f}"
                if previous_net != 0
                else None
            )
        )

    with col4:

        st.metric(
            "🏦 Spaarratio",
            f"{savings_rate:.1f}%"
        )

    # --------------------------------------------------------
    # INCOME VS EXPENSES
    # --------------------------------------------------------

    st.subheader(
        "📈 Inkomsten vs. uitgaven"
    )

    chart_data = pd.DataFrame(
        {
            "Inkomsten": [
                income
            ],

            "Uitgaven": [
                expenses
            ],

            "Netto": [
                net
            ]
        }
    )

    st.bar_chart(
        chart_data
    )

    # --------------------------------------------------------
    # EXPENSE CATEGORIES
    # --------------------------------------------------------

    st.subheader(
        "💸 Uitgaven per categorie"
    )

    expense_df = current_month_df[
        current_month_df["flow"] == "Uitgave"
    ].copy()

    if not expense_df.empty:

        expense_df["amount"] = (
            expense_df["amount"].abs()
        )

        category_summary = (
            expense_df
            .groupby("category")["amount"]
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

    # --------------------------------------------------------
    # FORECAST
    # --------------------------------------------------------

    st.subheader(
        "🔮 Forecast"
    )

    forecast = calculate_forecast(
        transaction_df,
        selected_period,
        saved_recurring
    )

    if forecast:

        forecast_col1, forecast_col2, forecast_col3 = (
            st.columns(3)
        )

        with forecast_col1:

            st.metric(
                "Verwachte inkomsten",
                f"€ {forecast['income']:,.2f}"
            )

        with forecast_col2:

            st.metric(
                "Verwachte uitgaven",
                f"€ {forecast['expenses']:,.2f}"
            )

        with forecast_col3:

            st.metric(
                "Verwacht netto",
                f"€ {forecast['net']:,.2f}"
            )

        if forecast["net"] >= 0:

            st.success(
                f"💰 Op basis van je huidige patroon "
                f"houd je naar verwachting "
                f"€ {forecast['net']:,.2f} over."
            )

        else:

            st.error(
                f"⚠️ Op basis van je huidige patroon "
                f"kom je naar verwachting "
                f"€ {abs(forecast['net']):,.2f} tekort."
            )

else:

    st.info(
        "Upload transacties om je dashboard te bekijken."
    )


# ============================================================
# RECURRING TRANSACTIONS
# ============================================================

st.divider()

st.header(
    "🔄 Terugkerende betalingen"
)

st.caption(
    "Financial Cockpit zoekt automatisch naar betalingen "
    "die regelmatig terugkomen."
)

if st.button(
    "🔍 Terugkerende betalingen detecteren",
    type="primary",
    use_container_width=True
):

    detected = detect_recurring_transactions(
        transactions
    )

    if detected:

        saved = save_recurring_transactions(
            user_id,
            selected_account_id,
            detected
        )

        if saved:

            st.success(
                f"✅ {len(saved)} terugkerende betalingen opgeslagen."
            )

            st.rerun()

        else:

            st.warning(
                "Betalingen gevonden, maar opslaan is mislukt."
            )

    else:

        st.info(
            "Geen duidelijke terugkerende betalingen gevonden."
        )


saved_recurring = load_recurring_transactions(
    user_id,
    selected_account_id
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

    recurring_monthly = monthly_recurring_cost(
        saved_recurring
    )

    col1, col2, col3 = st.columns(3)

    with col1:

        st.metric(
            "🔄 Actieve betalingen",
            len(active_recurring)
        )

    with col2:

        st.metric(
            "💸 Maandelijkse kosten",
            f"€ {recurring_monthly:,.2f}"
        )

    with col3:

        st.metric(
            "⏸️ Inactief",
            len(inactive_recurring)
        )

    st.subheader(
        "📋 Mijn terugkerende betalingen"
    )

    for recurring in active_recurring:

        merchant = recurring.get(
            "merchant",
            "Onbekend"
        )

        category = recurring.get(
            "category",
            "Overig"
        )

        frequency = recurring.get(
            "frequency",
            "Onbekend"
        )

        expected_amount = float(
            recurring.get(
                "expected_amount",
                0
            ) or 0
        )

        next_occurrence = recurring.get(
            "next_occurrence",
            "-"
        )

        last_occurrence = recurring.get(
            "last_occurrence",
            "-"
        )

        recurring_id = recurring.get(
            "id"
        )

        with st.container(
            border=True
        ):

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
                    f"€ {expected_amount:,.2f}"
                )

            with col3:

                st.metric(
                    "Volgende",
                    next_occurrence
                )

            with col4:

                st.metric(
                    "Laatste",
                    last_occurrence
                )

            button_col1, button_col2 = st.columns(2)

            with button_col1:

                if st.button(
                    "⏸️ Deactiveren",
                    key=f"deactivate_{recurring_id}",
                    use_container_width=True
                ):

                    update_recurring_active(
                        recurring_id,
                        False
                    )

                    st.rerun()

            with button_col2:

                if st.button(
                    "🗑️ Verwijderen",
                    key=f"delete_{recurring_id}",
                    use_container_width=True
                ):

                    delete_recurring_transaction(
                        recurring_id
                    )

                    st.rerun()

    if inactive_recurring:

        with st.expander(
            "⏸️ Inactieve betalingen"
        ):

            for recurring in inactive_recurring:

                recurring_id = recurring.get(
                    "id"
                )

                merchant = recurring.get(
                    "merchant",
                    "Onbekend"
                )

                expected_amount = float(
                    recurring.get(
                        "expected_amount",
                        0
                    ) or 0
                )

                frequency = recurring.get(
                    "frequency",
                    "Onbekend"
                )

                col1, col2, col3 = st.columns(
                    [4, 2, 2]
                )

                with col1:

                    st.markdown(
                        f"**{merchant.title()}**"
                    )

                    st.caption(
                        frequency
                    )

                with col2:

                    st.write(
                        f"€ {expected_amount:,.2f}"
                    )

                with col3:

                    if st.button(
                        "▶️ Activeren",
                        key=f"activate_{recurring_id}",
                        use_container_width=True
                    ):

                        update_recurring_active(
                            recurring_id,
                            True
                        )

                        st.rerun()

else:

    st.info(
        "Nog geen terugkerende betalingen gevonden."
    )


# ============================================================
# TRANSACTIONS
# ============================================================

st.divider()

st.header(
    "💳 Mijn transacties"
)

if not transaction_df.empty:

    display_columns = [
        "date",
        "description",
        "merchant",
        "amount",
        "flow",
        "category"
    ]

    available_columns = [
        column
        for column in display_columns
        if column in transaction_df.columns
    ]

    st.dataframe(
        transaction_df[
            available_columns
        ],
        use_container_width=True,
        hide_index=True
    )

else:

    st.info(
        "Nog geen transacties."
    )


# ============================================================
# BUDGETS
# ============================================================

st.divider()

st.header(
    "🎯 Mijn budgetten"
)

st.caption(
    "Stel per categorie een maximaal bedrag per maand in."
)

with st.expander(
    "➕ Budget instellen"
):

    budget_category = st.selectbox(
        "Categorie",
        [
            category
            for category in CATEGORIES
            if category != "Inkomen"
        ]
    )

    budget_amount = st.number_input(
        "Maandelijks budget",
        min_value=0.0,
        step=25.0,
        value=250.0,
        format="%.2f"
    )

    if st.button(
        "💾 Budget opslaan",
        type="primary",
        use_container_width=True
    ):

        result = save_budget(
            user_id,
            budget_category,
            budget_amount
        )

        if result is not None:

            st.success(
                f"✅ Budget voor {budget_category} opgeslagen."
            )

            st.rerun()


budgets = load_budgets(
    user_id
)

if budgets and not transaction_df.empty:

    valid_dates = transaction_df[
        transaction_df["date"].notna()
    ]

    available_months = sorted(
        valid_dates["date"]
        .dt.to_period("M")
        .unique(),
        reverse=True
    )

    selected_budget_index = st.selectbox(
        "📅 Budgetmaand",
        range(len(available_months)),
        format_func=lambda x:
            available_months[x].strftime("%B %Y"),
        key="budget_month"
    )

    budget_period = available_months[
        selected_budget_index
    ]

    monthly_transactions = transaction_df[
        transaction_df["date"]
        .dt.to_period("M")
        == budget_period
    ].copy()

    monthly_expenses = monthly_transactions[
        monthly_transactions["flow"] == "Uitgave"
    ].copy()

    monthly_expenses["expense_amount"] = (
        monthly_expenses["amount"].abs()
    )

    spending = (
        monthly_expenses
        .groupby("category")["expense_amount"]
        .sum()
        .to_dict()
    )

    for budget in budgets:

        category = budget[
            "category"
        ]

        budget_amount = float(
            budget[
                "monthly_limit"
            ]
        )

        spent = float(
            spending.get(
                category,
                0
            )
        )

        remaining = (
            budget_amount
            - spent
        )

        percentage = (
            spent / budget_amount * 100
            if budget_amount > 0
            else 0
        )

        st.markdown(
            f"### {category}"
        )

        col1, col2, col3 = st.columns(3)

        with col1:

            st.metric(
                "Budget",
                f"€ {budget_amount:,.2f}"
            )

        with col2:

            st.metric(
                "Uitgegeven",
                f"€ {spent:,.2f}"
            )

        with col3:

            st.metric(
                "Resterend",
                f"€ {remaining:,.2f}"
            )

        progress = min(
            max(
                percentage / 100,
                0
            ),
            1
        )

        st.progress(
            progress
        )

        if percentage > 100:

            st.error(
                f"🔴 Budget overschreden met "
                f"€ {abs(remaining):,.2f}"
            )

        elif percentage >= 80:

            st.warning(
                f"🟠 {percentage:.0f}% van het budget gebruikt."
            )

        else:

            st.success(
                f"🟢 {percentage:.0f}% van het budget gebruikt."
            )

else:

    if not budgets:

        st.info(
            "Je hebt nog geen budgetten ingesteld."
        )

    else:

        st.info(
            "Upload transacties om je budgetten te vergelijken."
        )


# ============================================================
# END
# ============================================================

st.divider()

st.caption(
    "Financial Cockpit · Persoonlijk financieel overzicht"
)
