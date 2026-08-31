import streamlit as st
import pandas as pd
import hashlib
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

supabase = create_client(
    st.secrets["SUPABASE_URL"],
    st.secrets["SUPABASE_KEY"]
)


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
    date,
    description,
    amount,
    transaction_type
):

    raw = (
        f"{date}|"
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
        "flow"
    ]

    for column in required_columns:

        if column not in df.columns:
            return []

    # --------------------------------------------------------
    # CLEAN DATA
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # ONLY EXPENSES
    # --------------------------------------------------------

    df = df[
        df["flow"] == "Uitgave"
    ].copy()

    if df.empty:
        return []

    df["amount_abs"] = (
        df["amount"].abs()
    )

    recurring = []

    # --------------------------------------------------------
    # ANALYSE PER MERCHANT
    # --------------------------------------------------------

    for merchant, group in df.groupby("merchant"):

        if len(group) < 2:
            continue

        group = group.sort_values(
            "date"
        ).copy()

        dates = list(
            group["date"]
        )

        amounts = list(
            group["amount_abs"]
        )

        # ----------------------------------------------------
        # INTERVALS
        # ----------------------------------------------------

        intervals = []

        for i in range(
            1,
            len(dates)
        ):

            days = (
                dates[i]
                - dates[i - 1]
            ).days

            intervals.append(
                days
            )

        if not intervals:
            continue

        average_interval = (
            sum(intervals)
            / len(intervals)
        )

        # ----------------------------------------------------
        # FREQUENCY
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # AMOUNT CONSISTENCY
        # ----------------------------------------------------

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

        if percentage_difference <= 0.15:

            reliability = "Hoog"

        elif percentage_difference <= 0.30:

            reliability = "Gemiddeld"

        else:

            continue

        # ----------------------------------------------------
        # CATEGORY
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # NEXT OCCURRENCE
        # ----------------------------------------------------

        last_date = dates[-1]

        next_date = (
            last_date
            + pd.Timedelta(
                days=round(
                    average_interval
                )
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
                "occurrences": len(
                    group
                ),
                "last_occurrence":
                    last_date.strftime(
                        "%Y-%m-%d"
                    ),
                "next_occurrence":
                    next_date.strftime(
                        "%Y-%m-%d"
                    ),
                "reliability":
                    reliability
            }
        )

    return recurring


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
                    "monthly_limit": float(
                        monthly_limit
                    )
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
            "Account aanmaken"
        ]
    )


    # ========================================================
    # LOGIN
    # ========================================================

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


    # ========================================================
    # REGISTER
    # ========================================================

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
                    f"❌ Rekening kon niet worden toegevoegd: {e}"
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

        df = pd.read_csv(
            uploaded_file,
            sep=None,
            engine="python"
        )


        # ----------------------------------------------------
        # CLEAN COLUMNS
        # ----------------------------------------------------

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


        # ----------------------------------------------------
        # COLUMN OPTIONS
        # ----------------------------------------------------

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


        # ----------------------------------------------------
        # FIND COLUMNS
        # ----------------------------------------------------

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


        # ----------------------------------------------------
        # VALIDATION
        # ----------------------------------------------------

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

        df[date_column] = pd.to_datetime(
            df[date_column]
            .astype(str)
            .str.strip(),
            format="%Y%m%d",
            errors="coerce"
        )


        # ----------------------------------------------------
        # AMOUNT
        # ----------------------------------------------------

        df[amount_column] = (
            df[amount_column]
            .astype(str)
            .str.strip()
            .str.replace(
                "€",
                "",
                regex=False
            )
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
            df[amount_column],
            errors="coerce"
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
                    row["transaction_type"]
                ),
            axis=1
        )


        # ----------------------------------------------------
        # REMOVE DUPLICATES
        # ----------------------------------------------------

        before_count = len(df)

        df = df.drop_duplicates(
            subset=["transaction_hash"],
            keep="first"
        )

        duplicate_count = (
            before_count - len(df)
        )

        if duplicate_count > 0:

            st.info(
                f"ℹ️ {duplicate_count} dubbele "
                f"transacties overgeslagen."
            )


        # ----------------------------------------------------
        # REMOVE INVALID ROWS
        # ----------------------------------------------------

        df = df[
            df[date_column].notna()
            & df[amount_column].notna()
        ].copy()


        # ----------------------------------------------------
        # PREVIEW
        # ----------------------------------------------------

        st.success(
            f"✅ {len(df):,} geldige transacties gevonden"
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


        # ----------------------------------------------------
        # SAVE
        # ----------------------------------------------------

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
                        f"✅ {len(result.data)} "
                        f"transacties verwerkt."
                    )

                    st.rerun()


                except Exception as e:

                    st.error(
                        "❌ Transacties konden niet "
                        f"worden opgeslagen: {e}"
                    )

            else:

                st.error(
                    "❌ Geen geldige transacties gevonden."
                )


    except Exception as e:

        st.error(
            "❌ Het CSV-bestand kon niet "
            f"worden verwerkt: {e}"
        )


# ============================================================
# LOAD TRANSACTIONS
# ============================================================

transactions = load_transactions(
    user_id,
    selected_account_id
)


# ============================================================
# TRANSACTIONS
# ============================================================

st.divider()

st.subheader(
    "💳 Mijn transacties"
)


if transactions:

    transactions_df = pd.DataFrame(
        transactions
    )


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
        if column in transactions_df.columns
    ]


    st.dataframe(
        transactions_df[
            available_columns
        ],
        use_container_width=True,
        hide_index=True
    )


else:

    st.info(
        "Nog geen transacties voor deze rekening."
    )
# ============================================================
# RECURRING TRANSACTIONS
# ============================================================

st.divider()

st.subheader(
    "🔄 Terugkerende transacties"
)

st.caption(
    "De app zoekt automatisch naar terugkerende betalingen "
    "op basis van je transactiehistorie."
)

if st.button(
    "🔍 Terugkerende transacties detecteren",
    use_container_width=True
):

    recurring_transactions = (
        detect_recurring_transactions(
            transactions
        )
    )

    st.session_state[
        "detected_recurring_transactions"
    ] = recurring_transactions

    if recurring_transactions:

        saved = save_recurring_transactions(
            user_id,
            selected_account_id,
            recurring_transactions
        )

        if saved:

            st.success(
                f"✅ {len(saved)} terugkerende "
                "transacties opgeslagen."
            )

        else:

            st.warning(
                "Er zijn transacties gevonden, "
                "maar ze konden niet worden opgeslagen."
            )


# ------------------------------------------------------------
# SHOW RESULTS
# ------------------------------------------------------------

if (
    "detected_recurring_transactions"
    in st.session_state
):

    recurring_transactions = (
        st.session_state[
            "detected_recurring_transactions"
        ]
    )

    if recurring_transactions:

        st.success(
            f"✅ {len(recurring_transactions)} "
            "mogelijke terugkerende betalingen gevonden."
        )

        recurring_df = pd.DataFrame(
            recurring_transactions
        )

        recurring_df = recurring_df.rename(
            columns={
                "merchant": "Leverancier",
                "category": "Categorie",
                "frequency": "Frequentie",
                "expected_amount": "Verwacht bedrag",
                "occurrences": "Aantal keer",
                "last_occurrence": "Laatste keer",
                "next_occurrence": "Volgende keer",
                "reliability": "Betrouwbaarheid"
            }
        )

        st.dataframe(
            recurring_df,
            use_container_width=True,
            hide_index=True
        )

    else:

        st.info(
            "Geen duidelijke terugkerende transacties gevonden."
        )

# ============================================================
# DASHBOARD
# ============================================================

st.divider()

st.subheader(
    "📊 Overzicht"
)


if transactions:

    dashboard_df = pd.DataFrame(
        transactions
    )


    income = dashboard_df.loc[
        dashboard_df["flow"] == "Inkomst",
        "amount"
    ].sum()


    expenses = dashboard_df.loc[
        dashboard_df["flow"] == "Uitgave",
        "amount"
    ].sum()


    balance = income - expenses


    # --------------------------------------------------------
    # KPI
    # --------------------------------------------------------

    col1, col2, col3 = st.columns(3)


    with col1:

        st.metric(
            "💰 Inkomsten",
            f"€ {income:,.2f}"
        )


    with col2:

        st.metric(
            "💸 Uitgaven",
            f"€ {expenses:,.2f}"
        )


    with col3:

        st.metric(
            "📈 Netto",
            f"€ {balance:,.2f}"
        )


    # --------------------------------------------------------
    # EXPENSES BY CATEGORY
    # --------------------------------------------------------

    st.subheader(
        "💸 Uitgaven per categorie"
    )


    expense_df = dashboard_df[
        dashboard_df["flow"] == "Uitgave"
    ].copy()


    if not expense_df.empty:

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
            "Er zijn nog geen uitgaven."
        )


else:

    st.info(
        "Upload transacties om je financiële "
        "overzicht te zien."
    )


# ============================================================
# BUDGETTEN
# ============================================================

st.divider()

st.subheader(
    "🎯 Mijn budgetten"
)


st.markdown(
    "Stel per categorie een maximaal bedrag per maand in."
)


budgets = load_budgets(
    user_id
)

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
                "last_occurrence": recurring[
                    "last_occurrence"
                ],
                "next_occurrence": recurring[
                    "next_occurrence"
                ],
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

# ============================================================
# BUDGET INSTELLEN
# ============================================================

with st.expander(
    "➕ Budget instellen",
    expanded=False
):

    budget_category = st.selectbox(
        "Categorie",
        [
            category
            for category in CATEGORIES
            if category != "Inkomen"
        ],
        key="budget_category"
    )


    budget_amount = st.number_input(
        "Maandelijks budget",
        min_value=0.0,
        step=25.0,
        value=250.0,
        format="%.2f",
        key="budget_amount"
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


# ============================================================
# BUDGET OVERVIEW
# ============================================================

if budgets:

    budget_df = pd.DataFrame(
        budgets
    )


    # --------------------------------------------------------
    # AVAILABLE MONTHS
    # --------------------------------------------------------

    if transactions:

        transaction_df = pd.DataFrame(
            transactions
        )


        transaction_df["date"] = pd.to_datetime(
            transaction_df["date"],
            errors="coerce"
        )


        valid_dates = transaction_df[
            transaction_df["date"].notna()
        ]


        if not valid_dates.empty:

            available_months = sorted(
                valid_dates[
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
                "📅 Bekijk budget voor maand",
                range(len(available_months)),
                format_func=lambda x:
                    month_labels[x]
            )


            selected_period = (
                available_months[
                    selected_month_index
                ]
            )


            selected_month_label = (
                selected_period.strftime(
                    "%B %Y"
                )
            )


            # ------------------------------------------------
            # FILTER MONTH
            # ------------------------------------------------

            monthly_transactions = transaction_df[
                transaction_df["date"]
                .dt.to_period("M")
                == selected_period
            ].copy()


            monthly_expenses = monthly_transactions[
                monthly_transactions["flow"]
                == "Uitgave"
            ].copy()


            monthly_expenses[
                "expense_amount"
            ] = (
                monthly_expenses["amount"]
                .abs()
            )


            spending = (
                monthly_expenses
                .groupby("category")[
                    "expense_amount"
                ]
                .sum()
                .to_dict()
            )


            st.markdown(
                f"### 🎯 Budgetten voor {selected_month_label}"
            )


            # ------------------------------------------------
            # BUDGET CARDS
            # ------------------------------------------------

            for _, budget in budget_df.iterrows():

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
                    spent
                    / budget_amount
                    * 100
                    if budget_amount > 0
                    else 0
                )


                st.markdown(
                    f"#### {category}"
                )


                col1, col2, col3 = st.columns(
                    3
                )


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
                        f"🔴 Budget overschreden "
                        f"met € "
                        f"{abs(remaining):,.2f}"
                    )

                elif percentage >= 80:

                    st.warning(
                        f"🟠 {percentage:.0f}% "
                        f"van het budget gebruikt."
                    )

                else:

                    st.success(
                        f"🟢 {percentage:.0f}% "
                        f"van het budget gebruikt."
                    )


                st.divider()


        else:

            st.info(
                "Er zijn nog geen geldige transactiedatums beschikbaar."
            )


    else:

        st.info(
            "Upload eerst transacties om je budgetten te kunnen vergelijken."
        )


else:

    st.info(
        "Je hebt nog geen budgetten ingesteld. "
        "Gebruik hierboven '➕ Budget instellen' om je eerste budget toe te voegen."
    )
