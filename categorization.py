import hashlib
import re
from typing import Optional

import pandas as pd


# ============================================================
# CATEGORIES
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
# DEFAULT CATEGORY RULES
# ============================================================

CATEGORY_RULES = {

    # -------------------------
    # INCOME
    # -------------------------

    "Salaris": [
        "salaris",
        "salary",
        "loon",
        "payroll",
    ],

    "Belasting": [
        "belastingdienst",
        "toeslag",
        "teruggave",
        "tax refund",
    ],

    "Rente": [
        "rente",
        "interest",
    ],

    "Overboeking spaargeld": [
        "spaarrekening",
        "spaargeld",
        "savings",
    ],

    "Tikkies": [
        "tikkie",
        "tikkies",
    ],

    "Overige inkomsten": [
        "refund",
        "terugbetaling",
        "cashback",
        "vergoeding",
    ],

    # -------------------------
    # EXPENSES
    # -------------------------

    "Boodschappen": [
        "albert heijn",
        "albert heijn online",
        "ah ",
        "jumbo",
        "plus",
        "lidl",
        "aldi",
        "dirk",
        "coop",
        "supermarkt",
        "picnic",
        "hoogvliet",
        "vomar",
        "spar",
    ],

    "Wonen": [
        "vattenfall",
        "essent",
        "eneco",
        "huur",
        "hypotheek",
        "waternet",
    ],

    "Telecom": [
        "ziggo",
        "t-mobile",
        "tmobile",
        "odido",
        "kpn",
        "vodafone",
        "tele2",
        "ben",
        "simyo",
    ],

    "Vervoer": [
        "shell",
        "esso",
        "bp",
        "total",
        "texaco",
        "ns ",
        "ns international",
        "ov-chipkaart",
        "uber",
        "bolt",
        "anwb",
        "q-park",
        "parkmobile",
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

    "Gezondheid": [
        "apotheek",
        "ziekenhuis",
        "tandarts",
        "dokter",
        "huisarts",
    ],

    "Verzekeringen": [
        "verzekering",
        "verzekeringen",
        "achmea",
        "interpolis",
        "ohra",
        "aegon",
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
}


# ============================================================
# TEXT HELPERS
# ============================================================

def normalize_text(value) -> str:
    """
    Normalizes text for reliable matching.
    """

    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass

    text = str(value).strip().lower()

    return re.sub(r"\s+", " ", text)


# ============================================================
# MERCHANT
# ============================================================

def normalize_merchant(
    description: str,
    merchant_rules: Optional[dict] = None,
) -> str:
    """
    Attempts to convert a bank description into a merchant.

    User-defined merchant rules have priority.
    """

    text = normalize_text(description)

    if not text:
        return "Onbekend"

    # User-defined merchant rules first
    if merchant_rules:

        for merchant in merchant_rules:

            merchant_text = normalize_text(merchant)

            if merchant_text and merchant_text in text:
                return str(merchant)

    # Default keyword matching
    for keywords in CATEGORY_RULES.values():

        for keyword in keywords:

            keyword_text = normalize_text(keyword)

            if keyword_text and keyword_text in text:
                return keyword_text.strip()

    return str(description).strip()


# ============================================================
# CATEGORIZATION
# ============================================================

def categorize_transaction(
    description: str,
    merchant: Optional[str] = None,
    merchant_rules: Optional[dict] = None,
    flow: Optional[str] = None,
) -> str:
    """
    Categorizes a transaction.

    Priority:
        1. User-defined merchant rule
        2. Default category rules
        3. Fallback category
    """

    text = normalize_text(
        f"{description or ''} {merchant or ''}"
    )

    # User rules always win
    if merchant_rules:

        for rule_merchant, category in merchant_rules.items():

            rule_text = normalize_text(rule_merchant)

            if rule_text and rule_text in text:
                return category

    # Only search appropriate category group
    if flow == "Inkomst":
        allowed_categories = INCOME_CATEGORIES

    elif flow == "Uitgave":
        allowed_categories = EXPENSE_CATEGORIES

    else:
        allowed_categories = CATEGORIES

    for category in allowed_categories:

        for keyword in CATEGORY_RULES.get(category, []):

            if normalize_text(keyword) in text:
                return category

    if flow == "Inkomst":
        return "Overige inkomsten"

    return "Overig"


# ============================================================
# TRANSACTION HASH
# ============================================================

def create_transaction_hash(
    transaction_date,
    description,
    amount,
    transaction_type,
) -> str:
    """
    Creates a deterministic SHA256 hash.

    Used to prevent duplicate imports.
    """

    raw = "|".join(
        [
            str(transaction_date),
            str(description or ""),
            str(amount),
            str(transaction_type or ""),
        ]
    )

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()


# ============================================================
# CSV COLUMN DETECTION
# ============================================================

def _find_column(columns, candidates):

    normalized = {
        str(column).strip().lower(): column
        for column in columns
    }

    for candidate in candidates:

        if candidate in normalized:
            return normalized[candidate]

    return None


# ============================================================
# AMOUNT PARSING
# ============================================================

def _parse_amount_series(series: pd.Series) -> pd.Series:

    if pd.api.types.is_numeric_dtype(series):
        return pd.to_numeric(
            series,
            errors="coerce",
        )

    values = (
        series.astype(str)
        .str.strip()
        .str.replace("€", "", regex=False)
        .str.replace(" ", "", regex=False)
        .str.replace(".", "", regex=False)
        .str.replace(",", ".", regex=False)
    )

    return pd.to_numeric(
        values,
        errors="coerce",
    )


# ============================================================
# CSV PREPARATION
# ============================================================

def prepare_import_dataframe(
    raw_df: pd.DataFrame,
    merchant_rules: Optional[dict] = None,
):
    """
    Converts a raw bank CSV into the standard transaction structure.

    Returns:
        dataframe
        column mapping
    """

    df = raw_df.copy()

    # Normalize column names
    df.columns = [
        str(column).strip().lower()
        for column in df.columns
    ]

    # Remove empty columns
    df = df.dropna(
        axis=1,
        how="all",
    )

    # Find description
    description_col = _find_column(
        df.columns,
        [
            "description",
            "omschrijving",
            "beschrijving",
            "naam",
            "details",
            "memo",
        ],
    )

    # Find amount
    amount_col = _find_column(
        df.columns,
        [
            "amount",
            "bedrag",
            "waarde",
            "transaction amount",
        ],
    )

    # Find date
    date_col = _find_column(
        df.columns,
        [
            "date",
            "datum",
            "boekdatum",
            "transactiedatum",
        ],
    )

    # Find debit/credit
    debit_credit_col = _find_column(
        df.columns,
        [
            "debit/credit",
            "debit_credit",
            "debit credit",
            "credit/debit",
            "type",
        ],
    )

    missing = []

    if not description_col:
        missing.append("omschrijving")

    if not amount_col:
        missing.append("bedrag")

    if not date_col:
        missing.append("datum")

    if not debit_credit_col:
        missing.append("debit/credit")

    if missing:

        raise ValueError(
            "Kon de volgende verplichte kolommen niet herkennen: "
            + ", ".join(missing)
        )

    # ========================================================
    # DATE
    # ========================================================

    df["date"] = pd.to_datetime(
        df[date_col].astype(str),
        format="%Y%m%d",
        errors="coerce",
    )

    fallback = df["date"].isna()

    if fallback.any():

        df.loc[fallback, "date"] = pd.to_datetime(
            df.loc[fallback, date_col],
            dayfirst=True,
            errors="coerce",
        )

    # ========================================================
    # AMOUNT
    # ========================================================

    df["amount"] = _parse_amount_series(
        df[amount_col]
    )

    # ========================================================
    # DESCRIPTION
    # ========================================================

    df["description"] = (
        df[description_col]
        .astype(str)
        .str.strip()
    )

    # ========================================================
    # DEBIT / CREDIT
    # ========================================================

    df["transaction_type"] = (
        df[debit_credit_col]
        .astype(str)
        .str.strip()
        .str.lower()
    )

    debit_credit = df["transaction_type"]

    df["flow"] = "Onbekend"

    df.loc[
        debit_credit.str.contains(
            "credit",
            na=False,
        ),
        "flow",
    ] = "Inkomst"

    df.loc[
        debit_credit.str.contains(
            "debit",
            na=False,
        ),
        "flow",
    ] = "Uitgave"

    # ========================================================
    # MERCHANT
    # ========================================================

    df["merchant"] = df["description"].apply(
        lambda value: normalize_merchant(
            value,
            merchant_rules,
        )
    )

    # ========================================================
    # CATEGORY
    # ========================================================

    df["category"] = [
        categorize_transaction(
            description,
            merchant=merchant,
            merchant_rules=merchant_rules,
            flow=flow,
        )
        for description, merchant, flow in zip(
            df["description"],
            df["merchant"],
            df["flow"],
        )
    ]

    # ========================================================
    # HASH
    # ========================================================

    df["transaction_hash"] = [
        create_transaction_hash(
            transaction_date,
            description,
            amount,
            transaction_type,
        )
        for transaction_date, description, amount, transaction_type
        in zip(
            df["date"],
            df["description"],
            df["amount"],
            df["transaction_type"],
        )
    ]

    # Remove duplicate transactions inside CSV
    df = df.drop_duplicates(
        subset=["transaction_hash"]
    )

    # Remove invalid records
    df = df.dropna(
        subset=[
            "date",
            "amount",
        ]
    )

    df = df.reset_index(
        drop=True
    )

    mapping = {
        "description": description_col,
        "amount": amount_col,
        "date": date_col,
        "debit_credit": debit_credit_col,
    }

    return df, mapping


# ============================================================
# DATABASE RECORD CONVERSION
# ============================================================

def dataframe_to_transaction_records(
    df: pd.DataFrame,
    user_id: str,
    account_id: str,
):
    """
    Converts prepared dataframe rows into Supabase records.
    """

    records = []

    for _, row in df.iterrows():

        date_value = row["date"]

        if hasattr(
            date_value,
            "date",
        ):
            date_value = date_value.date()

        records.append(
            {
                "user_id": user_id,
                "account_id": account_id,
                "date": (
                    date_value.isoformat()
                    if hasattr(
                        date_value,
                        "isoformat",
                    )
                    else str(date_value)
                ),
                "description": str(
                    row["description"]
                ),
                "merchant": str(
                    row["merchant"]
                ),
                "amount": float(
                    row["amount"]
                ),
                "flow": str(
                    row["flow"]
                ),
                "category": str(
                    row["category"]
                ),
                "transaction_type": str(
                    row["transaction_type"]
                ),
                "transaction_hash": str(
                    row["transaction_hash"]
                ),
            }
        )

    return records
