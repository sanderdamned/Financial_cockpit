import streamlit as st
import pandas as pd


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
        "supermarkt"
    ],
    "Vervoer": [
        "shell",
        "esso",
        "bp",
        "total",
        "ns ",
        "ov-chipkaart",
        "uber",
        "bolt",
        "anwb"
    ],
    "Entertainment": [
        "netflix",
        "spotify",
        "disney",
        "prime video",
        "pathe",
        "bioscoop"
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
    "Inkomen": [
        "salaris",
        "salary",
        "loon"
    ]
}


# ==========================================
# CATEGORISATIE
# ==========================================

def categorize_transaction(description):
    description = str(description).lower()

    for category, keywords in CATEGORY_RULES.items():
        for keyword in keywords:
            if keyword in description:
                return category

    return "Overig"


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

        # Lege kolommen verwijderen
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
            "naam",
            "details",
            "merchant",
            "transaction",
            "transactie"
        ]

        amount_options = [
            "amount",
            "bedrag",
            "waarde",
            "transactiebedrag"
        ]

        description_column = None
        amount_column = None

        for column in description_options:
            if column in df.columns:
                description_column = column
                break

        for column in amount_options:
            if column in df.columns:
                amount_column = column
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
                ", ".join(df.columns)
            )

            st.stop()

        if amount_column is None:

            st.error(
                "❌ Ik kan de bedragkolom niet herkennen."
            )

            st.write("Kolommen gevonden:")

            st.code(
                ", ".join(df.columns)
            )

            st.stop()

        # ==================================
        # BEDRAGEN NORMALISEREN
        # ==================================

        df[amount_column] = (
            df[amount_column]
            .astype(str)
            .str.replace("€", "", regex=False)
            .str.replace(".", "", regex=False)
            .str.replace(",", ".", regex=False)
        )

        df[amount_column] = pd.to_numeric(
            df[amount_column],
            errors="coerce"
        )

        # ==================================
        # CATEGORIE TOEVOEGEN
        # ==================================

        df["category"] = df[
            description_column
        ].apply(
            categorize_transaction
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

        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True
        )

        # ==================================
        # SAMENVATTING
        # ==================================

        st.subheader("📊 Samenvatting")

        income = df.loc[
            df[amount_column] > 0,
            amount_column
        ].sum()

        expenses = df.loc[
            df[amount_column] < 0,
            amount_column
        ].sum()

        balance = income + expenses

        col1, col2, col3 = st.columns(3)

        with col1:
            st.metric(
                "💰 Inkomsten",
                f"€ {income:,.2f}"
            )

        with col2:
            st.metric(
                "💸 Uitgaven",
                f"€ {abs(expenses):,.2f}"
            )

        with col3:
            st.metric(
                "📈 Netto",
                f"€ {balance:,.2f}"
            )

        # ==================================
        # UITGAVEN PER CATEGORIE
        # ==================================

        st.subheader("💸 Uitgaven per categorie")

        expense_df = df[
            df[amount_column] < 0
        ].copy()

        category_summary = (
            expense_df
            .groupby("category")[amount_column]
            .sum()
            .abs()
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

        st.subheader("📋 Overzicht categorieën")

        category_table = (
            expense_df
            .groupby("category")[amount_column]
            .agg(
                aantal="count",
                totaal="sum"
            )
            .reset_index()
        )

        category_table["totaal"] = (
            category_table["totaal"].abs()
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

        st.write