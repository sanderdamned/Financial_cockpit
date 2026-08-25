import streamlit as st
import pandas as pd
from supabase import create_client


# ==========================================
# CONFIGURATIE
# ==========================================

st.set_page_config(
    page_title="Financial Cockpit",
    page_icon="💰",
    layout="wide"
)

st.title("💰 Financial Cockpit")

st.markdown(
    """
    Upload hieronder je banktransacties als CSV.
    De transacties worden automatisch ingelezen en gecategoriseerd.
    """
)


# ==========================================
# SUPABASE
# ==========================================

try:

    supabase = create_client(
        st.secrets["SUPABASE_URL"],
        st.secrets["SUPABASE_KEY"]
    )

    supabase_available = True

except Exception as e:

    supabase_available = False

    st.warning(
        "⚠️ Supabase is niet beschikbaar. "
        "De app werkt zonder opgeslagen categorisatieregels."
    )


# ==========================================
# CATEGORIEËN
# ==========================================

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


# ==========================================
# BESCHIKBARE CATEGORIEËN
# ==========================================

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


# ==========================================
# AUTOMATISCHE CATEGORISATIE
# ==========================================

def categorize_transaction(description):

    description = str(description).lower()

    for category, keywords in CATEGORY_RULES.items():

        for keyword in keywords:

            if keyword in description:
                return category

    return "Overig"


# ==========================================
# MERCHANT HERKENNEN
# ==========================================

def normalize_merchant(description):

    description = str(description).lower().strip()

    # Eerst bekende merchants proberen te herkennen
    for keywords in CATEGORY_RULES.values():

        for keyword in keywords:

            if keyword in description:

                return keyword.strip()

    # Als merchant onbekend is:
    # volledige omschrijving gebruiken
    return description


# ==========================================
# MERCHANT RULES UIT SUPABASE OPHALEN
# ==========================================

def get_merchant_rules():

    if not supabase_available:
        return {}

    try:

        result = (
            supabase
            .table("merchant_rules")
            .select("merchant, category")
            .execute()
        )

        rules = {}

        for row in result.data:

            merchant = str(
                row["merchant"]
            ).lower().strip()

            rules[merchant] = row["category"]

        return rules

    except Exception as e:

        st.warning(
            f"⚠️ Merchant rules konden niet worden geladen: {e}"
        )

        return {}


# ==========================================
# MERCHANT RULE OPSLAAN
# ==========================================

def save_merchant_rule(merchant, category):

    if not supabase_available:
        return False

    try:

        (
            supabase
            .table("merchant_rules")
            .upsert(
                {
                    "merchant": merchant,
                    "category": category
                },
                on_conflict="merchant"
            )
            .execute()
        )

        return True

    except Exception as e:

        st.error(
            f"❌ Kon categorie niet opslaan: {e}"
        )

        return False


# ==========================================
# CSV UPLOAD
# ==========================================

uploaded_file = st.file_uploader(
    "Upload je banktransacties",
    type=["csv"]
)


if uploaded_file is not None:

    try:

        # ==================================
        # CSV INLEZEN
        # ==================================

        df = pd.read_csv(
            uploaded_file,
            sep=None,
            engine="python"
        )

        # ==================================
        # KOLOMNAMEN OPSCHONEN
        # ==================================

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

        # ==================================
        # KOLOMMEN HERKENNEN
        # ==================================

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

        description_column = None
        amount_column = None
        date_column = None
        debit_credit_column = None

        # Omschrijving
        for column in description_options:

            if column in df.columns:

                description_column = column
                break

        # Bedrag
        for column in amount_options:

            if column in df.columns:

                amount_column = column
                break

        # Datum
        for column in date_options:

            if column in df.columns:

                date_column = column
                break

        # Debit / Credit
        for column in debit_credit_options:

            if column in df.columns:

                debit_credit_column = column
                break

        # ==================================
        # CONTROLE
        # ==================================

        if description_column is None:

            st.error(
                "❌ Ik kan de omschrijvingskolom niet herkennen."
            )

            st.write("Kolommen gevonden:")

            st.code(
                "\n".join(df.columns)
            )

            st.stop()

        if amount_column is None:

            st.error(
                "❌ Ik kan de bedragkolom niet herkennen."
            )

            st.write("Kolommen gevonden:")

            st.code(
                "\n".join(df.columns)
            )

            st.stop()

        if debit_credit_column is None:

            st.error(
                "❌ Ik kan de debit/credit kolom niet herkennen."
            )

            st.write("Kolommen gevonden:")

            st.code(
                "\n".join(df.columns)
            )

            st.stop()

        # ==================================
        # DATUM VERWERKEN
        # ==================================

        if date_column is not None:

            df[date_column] = pd.to_datetime(
                df[date_column].astype(str),
                format="%Y%m%d",
                errors="coerce"
            )

        # ==================================
        # BEDRAG VERWERKEN
        # ==================================

        df[amount_column] = (
            df[amount_column]
            .astype(str)
            .str.strip()
            .str.replace("€", "", regex=False)
            .str.replace(".", "", regex=False)
            .str.replace(",", ".", regex=False)
        )

        df[amount_column] = pd.to_numeric(
            df[amount_column],
            errors="coerce"
        )

        # ==================================
        # DEBIT / CREDIT NORMALISEREN
        # ==================================

        df["transaction_type"] = (
            df[debit_credit_column]
            .astype(str)
            .str.strip()
            .str.lower()
        )

        df["flow"] = df["transaction_type"].apply(
            lambda x:
                "Inkomst"
                if x == "credit"
                else "Uitgave"
                if x == "debit"
                else "Onbekend"
        )

        # ==================================
        # MERCHANT HERKENNEN
        # ==================================

        df["merchant"] = df[
            description_column
        ].apply(
            normalize_merchant
        )

        # ==================================
        # BESTAANDE MERCHANT RULES LADEN
        # ==================================

        merchant_rules = get_merchant_rules()

        # ==================================
        # CATEGORIE BEPALEN
        # ==================================

        def determine_category(row):

            merchant = row["merchant"]

            # Eerst persoonlijke regel controleren
            if merchant in merchant_rules:

                return merchant_rules[merchant]

            # Anders automatische categorisatie
            return categorize_transaction(
                row[description_column]
            )

        df["category"] = df.apply(
            determine_category,
            axis=1
        )

        # ==================================
        # SUCCES
        # ==================================

        st.success(
            f"✅ {len(df):,} transacties gevonden"
        )

        # ==================================
        # TRANSACTIES
        # ==================================

        st.subheader("💳 Transacties")

        edited_df = st.data_editor(
            df,
            use_container_width=True,
            hide_index=True,
            column_config={

                "category":
                    st.column_config.SelectboxColumn(
                        "Categorie",
                        options=CATEGORIES,
                        required=True
                    ),

                "merchant":
                    st.column_config.TextColumn(
                        "Merchant",
                        disabled=True
                    )
            },
            disabled=[
                column
                for column in df.columns
                if column != "category"
            ]
        )

        # ==================================
        # CORRECTIES OPSLAAN
        # ==========================================

        changes_saved = 0

        for index, row in edited_df.iterrows():

            original_category = df.loc[
                index,
                "category"
            ]

            new_category = row["category"]

            merchant = row["merchant"]

            if (
                original_category != new_category
                and merchant
            ):

                if save_merchant_rule(
                    merchant,
                    new_category
                ):

                    changes_saved += 1

        if changes_saved > 0:

            st.success(
                f"✅ {changes_saved} categoriewijziging(en) opgeslagen."
            )

        # Vanaf hier werken we met de gewijzigde data
        df = edited_df

        # ==================================
        # INKOMSTEN
        # ==================================

        income = df.loc[
            df["flow"] == "Inkomst",
            amount_column
        ].sum()

        # ==================================
        # UITGAVEN
        # ==================================

        expenses = df.loc[
            df["flow"] == "Uitgave",
            amount_column
        ].sum()

        # ==================================
        # NETTO
        # ==================================

        balance = income - expenses

        # ==================================
        # DASHBOARD
        # ==================================

        st.subheader("📊 Samenvatting")

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

        # ==================================
        # UITGAVEN PER CATEGORIE
        # ==================================

        st.subheader(
            "💸 Uitgaven per categorie"
        )

        expense_df = df[
            df["flow"] == "Uitgave"
        ].copy()

        category_summary = (
            expense_df
            .groupby("category")[amount_column]
            .sum()
            .sort_values(
                ascending=False
            )
        )

        st.bar_chart(
            category_summary
        )

        # ==================================
        # CATEGORIE OVERZICHT
        # ==================================

        st.subheader(
            "📋 Overzicht categorieën"
        )

        category_table = (
            expense_df
            .groupby("category")[amount_column]
            .agg(
                aantal="count",
                totaal="sum"
            )
            .reset_index()
        )

        category_table = category_table.sort_values(
            "totaal",
            ascending=False
        )

        st.dataframe(
            category_table,
            use_container_width=True,
            hide_index=True
        )

    except Exception as e:

        st.error(
            f"❌ Het bestand kon niet worden gelezen: {e}"
        )
