
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

    description = str(description).lower()

    for category, keywords in CATEGORY_RULES.items():

        for keyword in keywords:

            if keyword in description:
                return category

    return "Overig"


def normalize_merchant(description):

    description = str(description).lower().strip()

    # Try to identify a known merchant
    for keywords in CATEGORY_RULES.values():

        for keyword in keywords:

            if keyword in description:
                return keyword.strip()

    return description


def create_transaction_hash(
    date,
    description,
    amount
):

    raw = (
        f"{date}|"
        f"{description}|"
        f"{amount}"
    )

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()


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

        return result.data

    except Exception as e:

        st.error(
            f"❌ Transacties konden niet worden geladen: {e}"
        )

        return []


# ============================================================
# LOGIN
# ============================================================

def show_login():

    st.title("💰 Financial Cockpit")

    login_tab, register_tab = st.tabs(
        [
            "Inloggen",
            "Account aanmaken"
        ]
    )

    # --------------------------------------------------------
    # LOGIN
    # --------------------------------------------------------

    with login_tab:

        email = st.text_input(
            "E-mailadres"
        )

        password = st.text_input(
            "Wachtwoord",
            type="password"
        )

        if st.button(
            "Inloggen",
            use_container_width=True
        ):

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

                if response.user:

                    st.session_state["user"] = (
                        response.user
                    )

                    st.rerun()

            except Exception as e:

                st.error(
                    f"❌ Inloggen mislukt: {e}"
                )

    # --------------------------------------------------------
    # REGISTER
    # --------------------------------------------------------

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
# LOGIN CHECK
# ============================================================

if "user" not in st.session_state:

    show_login()

    st.stop()


user = st.session_state["user"]

user_id = user.id


# ============================================================
# HEADER
# ============================================================

header_col1, header_col2 = st.columns(
    [5, 1]
)

with header_col1:

    st.title("💰 Financial Cockpit")

with header_col2:

    if st.button(
        "Uitloggen"
    ):

        supabase.auth.sign_out()

        st.session_state.pop(
            "user",
            None
        )

        st.rerun()


st.caption(
    f"Ingelogd als {user.email}"
)


# ============================================================
# ACCOUNTS
# ============================================================

st.subheader("🏦 Mijn rekeningen")


try:

    accounts_result = (
        supabase
        .table("accounts")
        .select("*")
        .eq("user_id", user_id)
        .execute()
    )

    accounts = accounts_result.data

except Exception as e:

    st.error(
        f"❌ Rekeningen konden niet worden geladen: {e}"
    )

    st.stop()


# ============================================================
# NO ACCOUNT YET
# ============================================================

if not accounts:

    st.info(
        "Je hebt nog geen bankrekening toegevoegd."
    )

    st.markdown(
        "### Voeg je eerste rekening toe"
    )

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

        if not account_name:

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
                            "name": account_name,
                            "bank": bank_name,
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

    st.stop()


# ============================================================
# ACCOUNT SELECTOR
# ============================================================

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

st.subheader("📁 Transacties importeren")


uploaded_file = st.file_uploader(
    "Upload je banktransacties als CSV",
    type=["csv"]
)


if uploaded_file is not None:

    try:

        # ----------------------------------------------------
        # READ CSV
        # ----------------------------------------------------

        df = pd.read_csv(
            uploaded_file,
            sep=None,
            engine="python"
        )

        # ----------------------------------------------------
        # CLEAN COLUMN NAMES
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
        # POSSIBLE COLUMN NAMES
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
        # DEBIT / CREDIT
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
        # TRANSACTION HASH
        # ----------------------------------------------------

        df["transaction_hash"] = df.apply(
            lambda row:
                create_transaction_hash(
                    row[date_column],
                    row[description_column],
                    row[amount_column]
                ),
            axis=1
        )


        # ----------------------------------------------------
        # PREVIEW
        # ----------------------------------------------------

        st.success(
            f"✅ {len(df):,} transacties gevonden"
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

                transaction_date = None

                if pd.notna(
                    row[date_column]
                ):

                    transaction_date = (
                        row[date_column].date()
                    )

                transactions_to_insert.append(
                    {
                        "user_id": user_id,

                        "account_id":
                            selected_account_id,

                        "date":
                            transaction_date,

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
                    f"✅ {len(result.data)} transacties verwerkt."
                )

                st.rerun()

            except Exception as e:

                st.error(
                    f"❌ Transacties konden niet worden opgeslagen: {e}"
                )


    except Exception as e:

        st.error(
            f"❌ Het CSV-bestand kon niet worden verwerkt: {e}"
        )


# ============================================================
# TRANSACTIONS
# ============================================================

st.divider()

st.subheader("💳 Mijn transacties")


transactions = load_transactions(
    user_id,
    selected_account_id
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
# DASHBOARD
# ============================================================

st.divider()

st.subheader("📊 Overzicht")


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
        "Upload transacties om je financiële overzicht te zien."
    )
