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
# GENERAL HELPERS
# ============================================================

def euro(value):
    try:
        return f"€ {float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "€ 0,00"


def percentage(value):
    return f"{float(value):.1f}%"


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


def create_account(
    user_id,
    name,
    bank,
    account_type
):

    try:

        result = (
            supabase
            .table("accounts")
            .insert(
                {
                    "user_id": user_id,
                    "name": name,
                    "bank": bank,
                    "account_type": account_type
                }
            )
            .execute()
        )

        return result.data

    except Exception as e:

        st.error(
            f"❌ Rekening kon niet worden toegevoegd: {e}"
        )

        return None


# ============================================================
# DATABASE - TRANSACTIONS
# ============================================================

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


def prepare_transaction_dataframe(transactions):

    if not transactions:
        return pd.DataFrame()

    df = pd.DataFrame(transactions)

    if df.empty:
        return df

    if "date" in df.columns:

        df["date"] = pd.to_datetime(
            df["date"],
            errors="coerce"
        )

    if "amount" in df.columns:

        df["amount"] = pd.to_numeric(
            df["amount"],
            errors="coerce"
        )

    if "flow" not in df.columns:
        df["flow"] = "Onbekend"

    if "category" not in df.columns:
        df["category"] = "Overig"

    if "merchant" not in df.columns:
        df["merchant"] = df.get(
            "description",
            ""
        )

    df = df[
        df["date"].notna()
        & df["amount"].notna()
    ].copy()

    return df


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
# DATABASE - RECURRING
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
            "❌ Terugkerende transactie kon "
            f"niet worden verwijderd: {e}"
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
            sum(amounts)
            / len(amounts)
        )

        if average_amount == 0:
            continue

        max_difference = max(
            abs(amount - average_amount)
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
                "occurrences": len(group),
                "last_occurrence":
                    last_date.strftime("%Y-%m-%d"),
                "next_occurrence":
                    next_date.strftime("%Y-%m-%d"),
                "reliability": reliability
            }
        )

    return recurring


# ============================================================
# PERIOD METRICS
# ============================================================

def calculate_metrics(
    df,
    period_type,
    selected_period
):

    if df.empty:
        return {
            "income": 0,
            "expenses": 0,
            "net": 0
        }

    if period_type == "Maand":

        mask = (
            df["date"].dt.to_period("M")
            == selected_period
        )

    else:

        mask = (
            df["date"].dt.year
            == selected_period
        )

    period_df = df[mask].copy()

    income = period_df.loc[
        period_df["flow"] == "Inkomst",
        "amount"
    ].sum()

    expenses = period_df.loc[
        period_df["flow"] == "Uitgave",
        "amount"
    ].abs().sum()

    return {
        "income": float(income),
        "expenses": float(expenses),
        "net": float(income - expenses)
    }


def get_period_dataframe(
    df,
    period_type,
    selected_period
):

    if df.empty:
        return pd.DataFrame()

    if period_type == "Maand":

        return df[
            df["date"].dt.to_period("M")
            == selected_period
        ].copy()

    return df[
        df["date"].dt.year
        == selected_period
    ].copy()


# ============================================================
# SMART FORECAST
# ============================================================

def calculate_smart_forecast(
    df,
    selected_month,
    active_recurring
):

    if df.empty:
        return None

    today = pd.Timestamp.today()

    if selected_month != today.to_period("M"):
        return None

    month_df = df[
        df["date"].dt.to_period("M")
        == selected_month
    ].copy()

    if month_df.empty:
        return None

    days_elapsed = today.day
    days_in_month = today.days_in_month
    days_remaining = (
        days_in_month
        - days_elapsed
    )

    income_so_far = month_df.loc[
        month_df["flow"] == "Inkomst",
        "amount"
    ].sum()

    expenses_so_far = month_df.loc[
        month_df["flow"] == "Uitgave",
        "amount"
    ].abs().sum()

    # --------------------------------------------------------
    # HISTORICAL MONTHLY DATA
    # --------------------------------------------------------

    historical = df[
        df["date"] < today
    ].copy()

    historical["month"] = (
        historical["date"]
        .dt.to_period("M")
    )

    monthly_expenses = (
        historical[
            historical["flow"] == "Uitgave"
        ]
        .groupby("month")["amount"]
        .apply(lambda x: x.abs().sum())
    )

    monthly_income = (
        historical[
            historical["flow"] == "Inkomst"
        ]
        .groupby("month")["amount"]
        .sum()
    )

    # --------------------------------------------------------
    # BASE VARIABLE FORECAST
    # --------------------------------------------------------

    if len(monthly_expenses) >= 3:

        recent_expenses = (
            monthly_expenses
            .tail(6)
        )

        historical_average = (
            recent_expenses.mean()
        )

        historical_median = (
            recent_expenses.median()
        )

        baseline_expenses = (
            historical_average * 0.4
            + historical_median * 0.6
        )

    elif len(monthly_expenses) > 0:

        baseline_expenses = (
            monthly_expenses.mean()
        )

    else:

        baseline_expenses = expenses_so_far

    # --------------------------------------------------------
    # CURRENT MONTH PACE
    # --------------------------------------------------------

    daily_expense_rate = (
        expenses_so_far
        / days_elapsed
        if days_elapsed > 0
        else 0
    )

    pace_projection = (
        expenses_so_far
        + daily_expense_rate
        * days_remaining
    )

    # Weighted combination.
    # Historical behaviour gets more weight than simple
    # day-by-day extrapolation.

    remaining_variable_by_history = max(
        baseline_expenses - expenses_so_far,
        0
    )

    remaining_variable_by_pace = (
        daily_expense_rate
        * days_remaining
    )

    remaining_variable = (
        remaining_variable_by_history * 0.65
        + remaining_variable_by_pace * 0.35
    )

    # --------------------------------------------------------
    # RECURRING PAYMENTS
    # --------------------------------------------------------

    recurring_remaining = 0.0
    recurring_items = []

    for item in active_recurring:

        next_occurrence = item.get(
            "next_occurrence"
        )

        if not next_occurrence:
            continue

        try:

            next_date = pd.Timestamp(
                next_occurrence
            )

            if (
                next_date.to_period("M")
                == selected_month
                and next_date >= today
            ):

                amount = float(
                    item.get(
                        "expected_amount",
                        0
                    ) or 0
                )

                recurring_remaining += amount

                recurring_items.append(
                    {
                        "merchant":
                            item.get(
                                "merchant",
                                "Onbekend"
                            ),
                        "amount": amount,
                        "date": next_date
                    }
                )

        except Exception:
            continue

    projected_expenses = (
        expenses_so_far
        + remaining_variable
        + recurring_remaining
    )

    # --------------------------------------------------------
    # INCOME FORECAST
    # --------------------------------------------------------

    if len(monthly_income) >= 3:

        recent_income = (
            monthly_income
            .tail(6)
        )

        historical_income = (
            recent_income.mean()
        )

        projected_income = max(
            income_so_far,
            historical_income
        )

    elif len(monthly_income) > 0:

        projected_income = max(
            income_so_far,
            monthly_income.mean()
        )

    else:

        projected_income = income_so_far

    projected_net = (
        projected_income
        - projected_expenses
    )

    # --------------------------------------------------------
    # CONFIDENCE
    # --------------------------------------------------------

    history_score = min(
        len(monthly_expenses) / 6,
        1
    )

    recurring_score = (
        1
        if len(active_recurring) > 0
        else 0.5
    )

    confidence_score = (
        history_score * 0.65
        + recurring_score * 0.35
    )

    if confidence_score >= 0.75:

        confidence = "Hoog"

        lower = projected_net * 0.90
        upper = projected_net * 1.10

    elif confidence_score >= 0.45:

        confidence = "Gemiddeld"

        lower = projected_net * 0.80
        upper = projected_net * 1.20

    else:

        confidence = "Laag"

        lower = projected_net * 0.65
        upper = projected_net * 1.35

    # Correct range when net is negative

    if projected_net < 0:

        lower, upper = (
            projected_net * 1.35,
            projected_net * 0.65
        )

    return {
        "income_so_far": float(income_so_far),
        "expenses_so_far": float(expenses_so_far),
        "remaining_variable": float(
            remaining_variable
        ),
        "recurring_remaining": float(
            recurring_remaining
        ),
        "projected_income": float(
            projected_income
        ),
        "projected_expenses": float(
            projected_expenses
        ),
        "projected_net": float(
            projected_net
        ),
        "lower": float(lower),
        "upper": float(upper),
        "confidence": confidence,
        "recurring_items": recurring_items
    }


# ============================================================
# MONTHLY YEAR SUMMARY
# ============================================================

def calculate_year_monthly_summary(
    df,
    year
):

    year_df = df[
        df["date"].dt.year == year
    ].copy()

    if year_df.empty:
        return pd.DataFrame()

    year_df["month"] = (
        year_df["date"]
        .dt.month
    )

    income = (
        year_df[
            year_df["flow"] == "Inkomst"
        ]
        .groupby("month")["amount"]
        .sum()
    )

    expenses = (
        year_df[
            year_df["flow"] == "Uitgave"
        ]
        .groupby("month")["amount"]
        .sum()
        .abs()
    )

    result = pd.DataFrame(
        {
            "Inkomsten": income,
            "Uitgaven": expenses
        }
    ).fillna(0)

    result["Netto"] = (
        result["Inkomsten"]
        - result["Uitgaven"]
    )

    result.index = [
        pd.Timestamp(
            year=year,
            month=int(month),
            day=1
        ).strftime("%b")
        for month in result.index
    ]

    return result


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

                    st.session_state[
                        "access_token"
                    ] = (
                        response.session.access_token
                    )

                    st.session_state[
                        "refresh_token"
                    ] = (
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


# ============================================================
# RESTORE SESSION
# ============================================================

if (
    "access_token" not in st.session_state
    or
    "refresh_token" not in st.session_state
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

    st.title("💰 Financial Cockpit")

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

accounts = load_accounts(user_id)

with st.expander(
    "🏦 Rekeningen",
    expanded=len(accounts) == 0
):

    if accounts:

        account_names = {
            account["name"]: account["id"]
            for account in accounts
        }

        selected_account_name = st.selectbox(
            "Actieve rekening",
            list(account_names.keys())
        )

        selected_account_id = (
            account_names[
                selected_account_name
            ]
        )

    else:

        st.info(
            "Voeg eerst een bankrekening toe."
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

            if not account_name.strip():

                st.error(
                    "Vul een naam voor de rekening in."
                )

            else:

                result = create_account(
                    user_id,
                    account_name.strip(),
                    bank_name.strip(),
                    account_type
                )

                if result:

                    st.success(
                        "✅ Rekening toegevoegd!"
                    )

                    st.rerun()

    if not accounts:
        st.stop()


# ============================================================
# LOAD DATA
# ============================================================

transactions = load_transactions(
    user_id,
    selected_account_id
)

transaction_df = prepare_transaction_dataframe(
    transactions
)

saved_recurring = load_recurring_transactions(
    user_id,
    selected_account_id
)

budgets = load_budgets(user_id)


# ============================================================
# SIDEBAR NAVIGATION
# ============================================================

st.sidebar.title(
    "💰 Financial Cockpit"
)

page = st.sidebar.radio(
    "Navigatie",
    [
        "📊 Dashboard",
        "🎯 Budgetten",
        "🔄 Terugkerend",
        "🔮 Forecast",
        "💳 Transacties"
    ]
)

st.sidebar.divider()

st.sidebar.caption(
    f"Rekening: {selected_account_name}"
)


# ============================================================
# PERIOD SELECTOR
# ============================================================

available_months = []

available_years = []

if not transaction_df.empty:

    available_months = sorted(
        transaction_df["date"]
        .dt.to_period("M")
        .unique(),
        reverse=True
    )

    available_years = sorted(
        transaction_df["date"]
        .dt.year
        .unique(),
        reverse=True
    )


current_month = (
    pd.Timestamp.today()
    .to_period("M")
)

current_year = (
    pd.Timestamp.today()
    .year
)


# ============================================================
# DASHBOARD
# ============================================================

if page == "📊 Dashboard":

    st.header("📊 Dashboard")

    if transaction_df.empty:

        st.info(
            "Upload eerst transacties via 💳 Transacties."
        )

    else:

        period_type = st.radio(
            "Periode",
            ["Maand", "Jaar"],
            horizontal=True,
            key="dashboard_period_type"
        )

        if period_type == "Maand":

            if current_month in available_months:

                default_index = (
                    available_months.index(
                        current_month
                    )
                )

            else:

                default_index = 0

            selected_period = st.selectbox(
                "Selecteer maand",
                available_months,
                index=default_index,
                format_func=lambda x:
                    x.strftime("%B %Y")
            )

        else:

            default_year_index = (
                available_years.index(current_year)
                if current_year in available_years
                else 0
            )

            selected_period = st.selectbox(
                "Selecteer jaar",
                available_years,
                index=default_year_index
            )

        metrics = calculate_metrics(
            transaction_df,
            period_type,
            selected_period
        )

        income = metrics["income"]
        expenses = metrics["expenses"]
        net = metrics["net"]

        savings_rate = (
            net / income * 100
            if income > 0
            else 0
        )

        # ----------------------------------------------------
        # KPI
        # ----------------------------------------------------

        col1, col2, col3, col4 = st.columns(4)

        with col1:

            st.metric(
                "💰 Inkomsten",
                euro(income)
            )

        with col2:

            st.metric(
                "💸 Uitgaven",
                euro(expenses)
            )

        with col3:

            st.metric(
                "📈 Netto",
                euro(net)
            )

        with col4:

            st.metric(
                "🏦 Spaarpercentage",
                percentage(savings_rate)
            )

        st.divider()

        # ----------------------------------------------------
        # YEAR VIEW
        # ----------------------------------------------------

        if period_type == "Jaar":

            st.subheader(
                f"📈 Overzicht {selected_period}"
            )

            summary = calculate_year_monthly_summary(
                transaction_df,
                selected_period
            )

            if not summary.empty:

                st.line_chart(
                    summary[
                        [
                            "Inkomsten",
                            "Uitgaven",
                            "Netto"
                        ]
                    ]
                )

                left, right = st.columns(2)

                with left:

                    st.subheader(
                        "💸 Uitgaven per categorie"
                    )

                    year_expenses = transaction_df[
                        (
                            transaction_df["date"]
                            .dt.year
                            == selected_period
                        )
                        &
                        (
                            transaction_df["flow"]
                            == "Uitgave"
                        )
                    ].copy()

                    if not year_expenses.empty:

                        category_summary = (
                            year_expenses
                            .assign(
                                amount_abs=
                                year_expenses[
                                    "amount"
                                ].abs()
                            )
                            .groupby(
                                "category"
                            )[
                                "amount_abs"
                            ]
                            .sum()
                            .sort_values(
                                ascending=False
                            )
                        )

                        st.bar_chart(
                            category_summary
                        )

                with right:

                    st.subheader(
                        "🏆 Grootste uitgaven"
                    )

                    if not year_expenses.empty:

                        merchant_summary = (
                            year_expenses
                            .assign(
                                amount_abs=
                                year_expenses[
                                    "amount"
                                ].abs()
                            )
                            .groupby(
                                "merchant"
                            )[
                                "amount_abs"
                            ]
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

        # ----------------------------------------------------
        # MONTH VIEW
        # ----------------------------------------------------

        else:

            month_df = get_period_dataframe(
                transaction_df,
                "Maand",
                selected_period
            )

            st.subheader(
                "📈 Cashflow"
            )

            daily = (
                month_df
                .groupby("date")
                .apply(
                    lambda x:
                        x.loc[
                            x["flow"] == "Inkomst",
                            "amount"
                        ].sum()
                        -
                        x.loc[
                            x["flow"] == "Uitgave",
                            "amount"
                        ].abs().sum()
                )
            )

            if not daily.empty:

                cumulative = daily.cumsum()

                st.line_chart(
                    cumulative
                )

            left, right = st.columns(2)

            with left:

                st.subheader(
                    "💸 Uitgaven per categorie"
                )

                expense_df = month_df[
                    month_df["flow"] == "Uitgave"
                ].copy()

                if not expense_df.empty:

                    category_summary = (
                        expense_df
                        .assign(
                            amount_abs=
                            expense_df[
                                "amount"
                            ].abs()
                        )
                        .groupby(
                            "category"
                        )[
                            "amount_abs"
                        ]
                        .sum()
                        .sort_values(
                            ascending=False
                        )
                    )

                    st.bar_chart(
                        category_summary
                    )

            with right:

                st.subheader(
                    "🏪 Grootste uitgaven"
                )

                if not expense_df.empty:

                    merchant_summary = (
                        expense_df
                        .assign(
                            amount_abs=
                            expense_df[
                                "amount"
                            ].abs()
                        )
                        .groupby(
                            "merchant"
                        )[
                            "amount_abs"
                        ]
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
# BUDGETS
# ============================================================

elif page == "🎯 Budgetten":

    st.header("🎯 Budgetten")

    st.caption(
        "Stel per categorie een maximaal bedrag per maand in."
    )

    budgets = load_budgets(user_id)

    with st.expander(
        "➕ Budget instellen"
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

    if not transaction_df.empty and budgets:

        budget_period_type = st.radio(
            "Budgetweergave",
            ["Maand", "Jaar"],
            horizontal=True
        )

        if budget_period_type == "Maand":

            available_months_budget = sorted(
                transaction_df["date"]
                .dt.to_period("M")
                .unique(),
                reverse=True
            )

            selected_budget_month = st.selectbox(
                "Selecteer maand",
                available_months_budget,
                format_func=lambda x:
                    x.strftime("%B %Y")
            )

            budget_transactions = (
                transaction_df[
                    (
                        transaction_df["date"]
                        .dt.to_period("M")
                        == selected_budget_month
                    )
                    &
                    (
                        transaction_df["flow"]
                        == "Uitgave"
                    )
                ]
            )

        else:

            selected_budget_year = st.selectbox(
                "Selecteer jaar",
                available_years
            )

            budget_transactions = (
                transaction_df[
                    (
                        transaction_df["date"]
                        .dt.year
                        == selected_budget_year
                    )
                    &
                    (
                        transaction_df["flow"]
                        == "Uitgave"
                    )
                ]
            )

        if not budget_transactions.empty:

            spending = (
                budget_transactions
                .assign(
                    expense_amount=
                    budget_transactions[
                        "amount"
                    ].abs()
                )
                .groupby(
                    "category"
                )[
                    "expense_amount"
                ]
                .sum()
                .to_dict()
            )

        else:

            spending = {}

        for budget in budgets:

            category = budget["category"]

            monthly_budget = float(
                budget["monthly_limit"]
            )

            if budget_period_type == "Maand":

                budget_amount_display = (
                    monthly_budget
                )

            else:

                budget_amount_display = (
                    monthly_budget * 12
                )

            spent = float(
                spending.get(
                    category,
                    0
                )
            )

            remaining = (
                budget_amount_display
                - spent
            )

            percentage_used = (
                spent
                / budget_amount_display
                * 100
                if budget_amount_display > 0
                else 0
            )

            st.markdown(
                f"### {category}"
            )

            col1, col2, col3 = st.columns(3)

            with col1:

                st.metric(
                    "Budget",
                    euro(
                        budget_amount_display
                    )
                )

            with col2:

                st.metric(
                    "Uitgegeven",
                    euro(spent)
                )

            with col3:

                st.metric(
                    "Resterend",
                    euro(remaining)
                )

            progress = min(
                max(
                    percentage_used / 100,
                    0
                ),
                1
            )

            st.progress(progress)

            if percentage_used > 100:

                st.error(
                    f"🔴 Budget overschreden met "
                    f"{euro(abs(remaining))}"
                )

            elif percentage_used >= 80:

                st.warning(
                    f"🟠 {percentage_used:.0f}% "
                    "van het budget gebruikt."
                )

            else:

                st.success(
                    f"🟢 {percentage_used:.0f}% "
                    "van het budget gebruikt."
                )

            st.divider()

    elif not budgets:

        st.info(
            "Je hebt nog geen budgetten ingesteld."
        )


# ============================================================
# RECURRING
# ============================================================

elif page == "🔄 Terugkerend":

    st.header("🔄 Terugkerende betalingen")

    st.caption(
        "Financial Cockpit zoekt naar betalingen die regelmatig terugkomen."
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

        monthly_recurring_cost = 0.0

        for item in active_recurring:

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

                monthly_recurring_cost += (
                    amount * 52 / 12
                )

            elif frequency == "Maandelijks":

                monthly_recurring_cost += amount

            elif frequency == "Per kwartaal":

                monthly_recurring_cost += (
                    amount / 3
                )

            elif frequency == "Jaarlijks":

                monthly_recurring_cost += (
                    amount / 12
                )

        col1, col2, col3 = st.columns(3)

        with col1:

            st.metric(
                "🔄 Actieve betalingen",
                len(active_recurring)
            )

        with col2:

            st.metric(
                "💸 Geschatte maandlasten",
                euro(monthly_recurring_cost)
            )

        with col3:

            st.metric(
                "⏸️ Inactief",
                len(inactive_recurring)
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
                        euro(expected_amount)
                    )

                with col3:

                    st.metric(
                        "Volgende",
                        next_occurrence
                    )

                with col4:

                    reliability = recurring.get(
                        "reliability",
                        "-"
                    )

                    st.metric(
                        "Betrouwbaarheid",
                        reliability
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
                "⏸️ Inactieve terugkerende betalingen"
            ):

                for recurring in inactive_recurring:

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

                    recurring_id = recurring.get(
                        "id"
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
                            euro(expected_amount)
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
# FORECAST
# ============================================================

elif page == "🔮 Forecast":

    st.header("🔮 Financiële forecast")

    st.caption(
        "Een inschatting van waar je financieel uitkomt aan het einde van deze maand."
    )

    if transaction_df.empty:

        st.info(
            "Upload eerst transacties om een forecast te maken."
        )

    else:

        active_recurring = [
            item
            for item in saved_recurring
            if item.get("active", True)
        ]

        current_month = (
            pd.Timestamp.today()
            .to_period("M")
        )

        forecast = calculate_smart_forecast(
            transaction_df,
            current_month,
            active_recurring
        )

        if forecast:

            projected_net = forecast[
                "projected_net"
            ]

            # ------------------------------------------------
            # MAIN FORECAST
            # ------------------------------------------------

            if projected_net >= 0:

                st.success(
                    f"### 🟢 Je hebt waarschijnlijk "
                    f"{euro(projected_net)} over "
                    "aan het einde van de maand."
                )

            else:

                st.error(
                    f"### 🔴 Je komt waarschijnlijk "
                    f"{euro(abs(projected_net))} tekort "
                    "aan het einde van de maand."
                )

            st.caption(
                f"Verwachte bandbreedte: "
                f"{euro(forecast['lower'])} "
                f"tot "
                f"{euro(forecast['upper'])}"
            )

            col1, col2, col3, col4 = st.columns(4)

            with col1:

                st.metric(
                    "Inkomsten tot nu toe",
                    euro(
                        forecast[
                            "income_so_far"
                        ]
                    )
                )

            with col2:

                st.metric(
                    "Uitgaven tot nu toe",
                    euro(
                        forecast[
                            "expenses_so_far"
                        ]
                    )
                )

            with col3:

                st.metric(
                    "Verwachte totale uitgaven",
                    euro(
                        forecast[
                            "projected_expenses"
                        ]
                    )
                )

            with col4:

                st.metric(
                    "Verwacht netto",
                    euro(
                        projected_net
                    )
                )

            st.divider()

            # ------------------------------------------------
            # FORECAST EXPLANATION
            # ------------------------------------------------

            st.subheader(
                "Waar komt de voorspelling vandaan?"
            )

            col1, col2 = st.columns(2)

            with col1:

                st.metric(
                    "Nog verwachte variabele uitgaven",
                    euro(
                        forecast[
                            "remaining_variable"
                        ]
                    )
                )

            with col2:

                st.metric(
                    "Nog komende vaste lasten",
                    euro(
                        forecast[
                            "recurring_remaining"
                        ]
                    )
                )

            st.info(
                "De forecast combineert je recente "
                "uitgavenpatroon met bekende terugkerende "
                "betalingen. Daardoor is deze minder "
                "gevoelig voor een uitzonderlijk dure dag "
                "dan een simpele daggemiddelde-berekening."
            )

            # ------------------------------------------------
            # RECURRING PAYMENTS
            # ------------------------------------------------

            recurring_items = forecast[
                "recurring_items"
            ]

            if recurring_items:

                st.subheader(
                    "🔄 Nog te verwachten deze maand"
                )

                recurring_display = pd.DataFrame(
                    [
                        {
                            "Betaling":
                                item["merchant"].title(),
                            "Bedrag":
                                euro(item["amount"]),
                            "Datum":
                                item["date"].strftime(
                                    "%d-%m-%Y"
                                )
                        }
                        for item in recurring_items
                    ]
                )

                st.dataframe(
                    recurring_display,
                    use_container_width=True,
                    hide_index=True
                )

            st.subheader(
                "🎯 Betrouwbaarheid"
            )

            confidence = forecast[
                "confidence"
            ]

            if confidence == "Hoog":

                st.success(
                    "🟢 Hoge betrouwbaarheid — "
                    "er is voldoende historische data "
                    "om een redelijk stabiele voorspelling te maken."
                )

            elif confidence == "Gemiddeld":

                st.warning(
                    "🟡 Gemiddelde betrouwbaarheid — "
                    "de voorspelling is bruikbaar, maar "
                    "kan nog duidelijk veranderen."
                )

            else:

                st.warning(
                    "🔴 Lage betrouwbaarheid — "
                    "er is nog onvoldoende historische "
                    "data beschikbaar."
                )

        else:

            st.info(
                "De forecast is alleen beschikbaar "
                "voor de huidige maand."
            )


# ============================================================
# TRANSACTIONS
# ============================================================

elif page == "💳 Transacties":

    st.header("💳 Transacties")

    # --------------------------------------------------------
    # CSV IMPORT
    # --------------------------------------------------------

    with st.expander(
        "📁 Nieuwe transacties importeren"
    ):

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

                if description_column is None:

                    st.error(
                        "❌ Omschrijvingskolom niet gevonden."
                    )

                    st.code(
                        "\n".join(df.columns)
                    )

                elif amount_column is None:

                    st.error(
                        "❌ Bedragkolom niet gevonden."
                    )

                    st.code(
                        "\n".join(df.columns)
                    )

                elif date_column is None:

                    st.error(
                        "❌ Datumkolom niet gevonden."
                    )

                    st.code(
                        "\n".join(df.columns)
                    )

                elif debit_credit_column is None:

                    st.error(
                        "❌ Debit/Credit kolom niet gevonden."
                    )

                    st.code(
                        "\n".join(df.columns)
                    )

                else:

                    # ----------------------------------------
                    # DATE
                    # ----------------------------------------

                    raw_dates = (
                        df[date_column]
                        .astype(str)
                        .str.strip()
                    )

                    df[date_column] = pd.to_datetime(
                        raw_dates,
                        format="%Y%m%d",
                        errors="coerce"
                    )

                    missing_dates = (
                        df[date_column].isna()
                    )

                    if missing_dates.any():

                        df.loc[
                            missing_dates,
                            date_column
                        ] = pd.to_datetime(
                            raw_dates[
                                missing_dates
                            ],
                            errors="coerce",
                            dayfirst=True
                        )

                    # ----------------------------------------
                    # AMOUNT
                    # ----------------------------------------

                    amount_series = (
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

                    amount_series = (
                        amount_series
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
                        amount_series,
                        errors="coerce"
                    )

                    # ----------------------------------------
                    # FLOW
                    # ----------------------------------------

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

                    # ----------------------------------------
                    # MERCHANT
                    # ----------------------------------------

                    df["merchant"] = df[
                        description_column
                    ].apply(
                        normalize_merchant
                    )

                    # ----------------------------------------
                    # CATEGORY
                    # ----------------------------------------

                    df["category"] = df[
                        description_column
                    ].apply(
                        categorize_transaction
                    )

                    # ----------------------------------------
                    # HASH
                    # ----------------------------------------

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

                    # ----------------------------------------
                    # DUPLICATES
                    # ----------------------------------------

                    before_count = len(df)

                    df = df.drop_duplicates(
                        subset=[
                            "transaction_hash"
                        ],
                        keep="first"
                    )

                    duplicate_count = (
                        before_count
                        - len(df)
                    )

                    if duplicate_count > 0:

                        st.info(
                            f"ℹ️ {duplicate_count} dubbele "
                            "transacties overgeslagen."
                        )

                    # ----------------------------------------
                    # INVALID
                    # ----------------------------------------

                    df = df[
                        df[date_column].notna()
                        & df[amount_column].notna()
                    ].copy()

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

    # --------------------------------------------------------
    # FILTERS
    # --------------------------------------------------------

    if not transaction_df.empty:

        st.divider()

        filter_col1, filter_col2, filter_col3, filter_col4 = (
            st.columns(4)
        )

        with filter_col1:

            transaction_year = st.selectbox(
                "Jaar",
                ["Alle"] + available_years
            )

        with filter_col2:

            transaction_month = st.selectbox(
                "Maand",
                ["Alle"] + list(range(1, 13)),
                format_func=lambda x:
                    (
                        "Alle"
                        if x == "Alle"
                        else pd.Timestamp(
                            2026,
                            x,
                            1
                        ).strftime("%B")
                    )
            )

        with filter_col3:

            transaction_flow = st.selectbox(
                "Type",
                [
                    "Alle",
                    "Inkomst",
                    "Uitgave"
                ]
            )

        with filter_col4:

            categories = sorted(
                transaction_df[
                    "category"
                ]
                .dropna()
                .unique()
                .tolist()
            )

            transaction_category = st.selectbox(
                "Categorie",
                ["Alle"] + categories
            )

        search = st.text_input(
            "🔎 Zoek op omschrijving of merchant"
        )

        filtered = transaction_df.copy()

        if transaction_year != "Alle":

            filtered = filtered[
                filtered["date"].dt.year
                == transaction_year
            ]

        if transaction_month != "Alle":

            filtered = filtered[
                filtered["date"].dt.month
                == transaction_month
            ]

        if transaction_flow != "Alle":

            filtered = filtered[
                filtered["flow"]
                == transaction_flow
            ]

        if transaction_category != "Alle":

            filtered = filtered[
                filtered["category"]
                == transaction_category
            ]

        if search.strip():

            search_lower = (
                search
                .strip()
                .lower()
            )

            description_match = (
                filtered["description"]
                .astype(str)
                .str.lower()
                .str.contains(
                    search_lower,
                    na=False
                )
            )

            merchant_match = (
                filtered["merchant"]
                .astype(str)
                .str.lower()
                .str.contains(
                    search_lower,
                    na=False
                )
            )

            filtered = filtered[
                description_match
                | merchant_match
            ]

        st.caption(
            f"{len(filtered):,} transacties"
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
            if column in filtered.columns
        ]

        display_df = filtered[
            available_columns
        ].copy()

        if "date" in display_df.columns:

            display_df["date"] = (
                display_df["date"]
                .dt.strftime("%d-%m-%Y")
            )

        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True
        )

    else:

        st.info(
            "Nog geen transacties voor deze rekening."
        )
