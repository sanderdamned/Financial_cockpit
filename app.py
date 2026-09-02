import pandas as pd
import streamlit as st
from supabase import create_client

from categorization import (
    CATEGORIES,
    EXPENSE_CATEGORIES,
    prepare_import_dataframe,
    dataframe_to_transaction_records,
)

from database import Database

from ui_helpers import (
    euro,
    metric_columns,
    month_selectbox,
    without_transfers,
    render_transaction_metrics,
)

from financial_engine import (
    prepare_transactions,
    detect_transfer_transactions,
    detect_recurring_transactions,
    calculate_monthly_metrics,
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

db = Database(
    supabase
)


# ============================================================
# DATABASE ERROR HANDLING
# ============================================================

def db_call(
    label,
    function,
    *args,
    **kwargs,
):
    """
    Executes database function with user-friendly error handling.
    """

    try:

        return function(
            *args,
            **kwargs,
        )

    except Exception as exc:

        st.error(
            f"{label}: {exc}"
        )

        return None


# ============================================================
# DATA LOADERS
# ============================================================

def load_user_rules(
    user_id,
):

    return (
        db_call(
            "Fout bij laden van merchantregels",
            db.load_merchant_category_rules,
            user_id,
        )
        or {}
    )


def load_accounts(
    user_id,
):

    return (
        db_call(
            "Fout bij laden van rekeningen",
            db.load_accounts,
            user_id,
        )
        or []
    )


def load_transactions(
    user_id,
    account_id=None,
):

    if account_id:

        rows = db_call(
            "Fout bij laden van transacties",
            db.load_transactions,
            user_id,
            account_id,
        ) or []

    else:

        rows = db_call(
            "Fout bij laden van transacties",
            db.load_all_transactions,
            user_id,
        ) or []

    return pd.DataFrame(
        rows
    )


def load_budgets(
    user_id,
):

    return (
        db_call(
            "Fout bij laden van budgetten",
            db.load_budgets,
            user_id,
        )
        or []
    )


def load_recurring(
    user_id,
    account_id=None,
):

    return (
        db_call(
            "Fout bij laden van terugkerende transacties",
            db.load_recurring_transactions,
            user_id,
            account_id,
        )
        or []
    )


# ============================================================
# RECURRING DETECTION
# ============================================================

def detect_recurring_transactions(
    df,
):
    """
    Detects recurring expenses.

    Frequency:
        25-35 days   = monthly
        6-8 days     = weekly
        80-100 days  = quarterly
        350-380 days = yearly
    """

    if df is None or df.empty:
        return []

    required = {
        "date",
        "merchant",
        "amount",
        "flow",
    }

    if not required.issubset(
        df.columns
    ):
        return []

    data = df.copy()

    data["date"] = pd.to_datetime(
        data["date"],
        errors="coerce",
    )

    data["amount"] = pd.to_numeric(
        data["amount"],
        errors="coerce",
    )

    data = data.dropna(
        subset=[
            "date",
            "amount",
        ]
    )

    # Recurring detection currently focuses
    # on expenses.
    data = data[
        data["flow"] == "Uitgave"
    ]

    if data.empty:
        return []

    results = []

    for merchant, group in data.groupby(
        "merchant"
    ):

        group = group.sort_values(
            "date"
        )

        if len(group) < 2:
            continue

        dates = group[
            "date"
        ].tolist()

        intervals = [
            (
                dates[index]
                - dates[index - 1]
            ).days
            for index in range(
                1,
                len(dates),
            )
        ]

        if not intervals:
            continue

        median_interval = float(
            pd.Series(
                intervals
            ).median()
        )

        # Frequency
        if 25 <= median_interval <= 35:

            frequency = "Maandelijks"
            days = 30

        elif 6 <= median_interval <= 8:

            frequency = "Wekelijks"
            days = 7

        elif 80 <= median_interval <= 100:

            frequency = "Per kwartaal"
            days = 90

        elif 350 <= median_interval <= 380:

            frequency = "Jaarlijks"
            days = 365

        else:
            continue

        amounts = (
            group["amount"]
            .abs()
        )

        mean_amount = float(
            amounts.mean()
        )

        if mean_amount == 0:
            continue

        variation = float(
            (
                amounts.max()
                - amounts.min()
            )
            / mean_amount
        )

        if variation <= 0.15:

            reliability = "Hoog"

        elif variation <= 0.30:

            reliability = "Gemiddeld"

        else:

            reliability = "Laag"

        # Determine category
        if (
            "category" in group.columns
            and not group["category"].mode().empty
        ):

            category = (
                group["category"]
                .mode()
                .iloc[0]
            )

        else:

            category = "Overig"

        last_occurrence = (
            group["date"].max()
        )

        next_occurrence = (
            last_occurrence
            + pd.Timedelta(
                days=days
            )
        )

        results.append(
            {
                "merchant": merchant,
                "category": category,
                "frequency": frequency,
                "expected_amount": mean_amount,
                "last_occurrence": (
                    last_occurrence
                    .date()
                    .isoformat()
                ),
                "next_occurrence": (
                    next_occurrence
                    .date()
                    .isoformat()
                ),
                "reliability": reliability,
                "flow": "Uitgave",
            }
        )

    return results


# ============================================================
# LOGIN
# ============================================================

def show_login():

    st.title(
        "💰 Financial Cockpit"
    )

    st.write(
        "Log in om je financiële overzicht te bekijken."
    )

    login_tab, register_tab = st.tabs(
        [
            "Inloggen",
            "Account aanmaken",
        ]
    )

    # ========================================================
    # LOGIN
    # ========================================================

    with login_tab:

        with st.form(
            "login_form"
        ):

            email = st.text_input(
                "E-mailadres"
            )

            password = st.text_input(
                "Wachtwoord",
                type="password",
            )

            submitted = st.form_submit_button(
                "Inloggen",
                type="primary",
            )

        if submitted:

            try:

                response = (
                    supabase.auth
                    .sign_in_with_password(
                        {
                            "email": email,
                            "password": password,
                        }
                    )
                )

                session = response.session
                user = response.user

                if not session or not user:

                    st.error(
                        "Inloggen is niet gelukt."
                    )

                    return

                st.session_state[
                    "user"
                ] = user

                st.session_state[
                    "access_token"
                ] = session.access_token

                st.session_state[
                    "refresh_token"
                ] = session.refresh_token

                supabase.auth.set_session(
                    session.access_token,
                    session.refresh_token,
                )

                st.rerun()

            except Exception as exc:

                st.error(
                    f"Inloggen mislukt: {exc}"
                )

    # ========================================================
    # REGISTER
    # ========================================================

    with register_tab:

        with st.form(
            "register_form"
        ):

            email = st.text_input(
                "E-mailadres",
                key="register_email",
            )

            password = st.text_input(
                "Wachtwoord",
                type="password",
                key="register_password",
            )

            password2 = st.text_input(
                "Wachtwoord herhalen",
                type="password",
            )

            submitted = st.form_submit_button(
                "Account aanmaken"
            )

        if submitted:

            if len(password) < 8:

                st.error(
                    "Gebruik minimaal 8 tekens."
                )

            elif password != password2:

                st.error(
                    "De wachtwoorden komen niet overeen."
                )

            else:

                try:

                    response = (
                        supabase.auth
                        .sign_up(
                            {
                                "email": email,
                                "password": password,
                            }
                        )
                    )

                    if (
                        response.user
                        and not response.session
                    ):

                        st.success(
                            "Account aangemaakt. "
                            "Controleer je e-mail om je account te bevestigen."
                        )

                    else:

                        st.success(
                            "Account aangemaakt. "
                            "Je kunt nu inloggen."
                        )

                except Exception as exc:

                    st.error(
                        f"Registreren mislukt: {exc}"
                    )


# ============================================================
# AUTHENTICATION
# ============================================================

if "user" not in st.session_state:

    show_login()

    st.stop()


user = st.session_state[
    "user"
]

user_id = user.id

access_token = st.session_state.get(
    "access_token"
)

refresh_token = st.session_state.get(
    "refresh_token"
)


if (
    not access_token
    or not refresh_token
):

    st.warning(
        "Je sessie is verlopen. Log opnieuw in."
    )

    if st.button(
        "Opnieuw inloggen"
    ):

        st.session_state.clear()

        st.rerun()

    st.stop()


try:

    supabase.auth.set_session(
        access_token,
        refresh_token,
    )

except Exception:

    st.session_state.clear()

    st.rerun()


# ============================================================
# SHARED DATA
# ============================================================

merchant_rules = load_user_rules(
    user_id
)

accounts = load_accounts(
    user_id
)


# ============================================================
# FIRST ACCOUNT
# ============================================================

if not accounts:

    st.title(
        "Welkom bij Financial Cockpit"
    )

    st.write(
        "Maak eerst je eerste bankrekening aan."
    )

    with st.form(
        "first_account"
    ):

        name = st.text_input(
            "Naam rekening",
            placeholder="Betaalrekening",
        )

        bank = st.text_input(
            "Bank",
            placeholder="ING",
        )

        account_type = st.selectbox(
            "Type rekening",
            [
                "checking",
                "savings",
                "creditcard",
                "other",
            ],
            format_func=lambda value: {
                "checking": "Betaalrekening",
                "savings": "Spaarrekening",
                "creditcard": "Creditcard",
                "other": "Overig",
            }[value],
        )

        submitted = st.form_submit_button(
            "Rekening toevoegen",
            type="primary",
        )

    if submitted:

        if not name.strip():

            st.error(
                "Geef de rekening een naam."
            )

        else:

            result = db_call(
                "Rekening kon niet worden aangemaakt",
                db.create_account,
                user_id,
                name.strip(),
                bank.strip(),
                account_type,
            )

            if result is not None:

                st.success(
                    "Rekening aangemaakt."
                )

                st.rerun()

    st.stop()


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.title(
    "💰 Financial Cockpit"
)

st.sidebar.caption(
    user.email or ""
)


page = st.sidebar.radio(
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


account_labels = [
    "Alle rekeningen"
] + [
    account["name"]
    for account in accounts
]


selected_account_label = (
    st.sidebar.selectbox(
        "Rekening",
        account_labels,
    )
)


selected_account = next(
    (
        account
        for account in accounts
        if account["name"]
        == selected_account_label
    ),
    None,
)


selected_account_id = (
    selected_account["id"]
    if selected_account
    else None
)


if st.sidebar.button(
    "Uitloggen"
):

    st.session_state.clear()

    try:
        supabase.auth.sign_out()

    except Exception:
        pass

    st.rerun()


# ============================================================
# LOAD SCOPED DATA
# ============================================================

transaction_df = load_transactions(
    user_id,
    selected_account_id,
)


if not transaction_df.empty:

    transaction_df = (
        prepare_transactions(
            transaction_df
        )
    )

    transaction_df = (
        detect_transfer_transactions(
            transaction_df
        )
    )


# ============================================================
# RECURRING
# ============================================================

if selected_account_id:

    recurring_rows = load_recurring(
        user_id,
        selected_account_id,
    )

else:

    recurring_rows = []

    for account in accounts:

        recurring_rows.extend(
            load_recurring(
                user_id,
                account["id"],
            )
        )


# ============================================================
# BUDGETS
# ============================================================

budgets = load_budgets(
    user_id
)


# ============================================================
# PAGE: OVERVIEW
# ============================================================

def page_overview():

    st.title(
        "Overzicht"
    )

    st.caption(
        "Je financiële cockpit in één scherm."
    )

    if transaction_df.empty:

        st.info(
            "Nog geen transacties. "
            "Importeer eerst een CSV."
        )

        return

    selected_period = month_selectbox(
        transaction_df,
        key="overview_period",
    )

    if selected_period is None:
        return

    # ========================================================
    # ACTUAL MONTHLY METRICS
    # ========================================================

    metrics = calculate_monthly_metrics(
        transaction_df,
        selected_period,
        exclude_internal_transfers=True,
    )

    metric_columns(
        [
            (
                "Inkomsten",
                euro(
                    metrics.get(
                        "income",
                        0,
                    )
                ),
            ),
            (
                "Uitgaven",
                euro(
                    metrics.get(
                        "expenses",
                        0,
                    )
                ),
            ),
            (
                "Netto",
                euro(
                    metrics.get(
                        "net",
                        0,
                    )
                ),
            ),
            (
                "Spaarquote",
                f"{metrics.get('savings_rate', 0):.1f}%",
            ),
        ]
    )

    # ========================================================
    # MONTH DATA
    # ========================================================

    month_df = transaction_df[
        pd.to_datetime(
            transaction_df["date"]
        ).dt.to_period("M")
        == selected_period
    ].copy()

    month_normal = without_transfers(
        month_df
    )

    expenses = month_normal[
        month_normal["flow"]
        == "Uitgave"
    ].copy()

    # ========================================================
    # CHARTS
    # ========================================================

    col1, col2 = st.columns(
        2
    )

    with col1:

        st.subheader(
            "Uitgaven per categorie"
        )

        if not expenses.empty:

            chart = (
                expenses
                .assign(
                    amount=expenses[
                        "amount"
                    ].abs()
                )
                .groupby(
                    "category"
                )["amount"]
                .sum()
                .sort_values(
                    ascending=False
                )
            )

            st.bar_chart(
                chart
            )

        else:

            st.info(
                "Geen uitgaven in deze maand."
            )

    with col2:

        st.subheader(
            "Grootste merchants"
        )

        if not expenses.empty:

            chart = (
                expenses
                .assign(
                    amount=expenses[
                        "amount"
                    ].abs()
                )
                .groupby(
                    "merchant"
                )["amount"]
                .sum()
                .sort_values(
                    ascending=False
                )
                .head(10)
            )

            st.bar_chart(
                chart
            )

        else:

            st.info(
                "Geen uitgaven in deze maand."
            )

    # ========================================================
    # FORECAST
    # ========================================================

    forecast = calculate_month_forecast(
        transaction_df,
        selected_period,
        recurring_rows,
        budgets,
    )

    budget_status = calculate_budget_status(
        transaction_df,
        budgets,
        selected_period,
    )

    health = calculate_financial_health(
        forecast,
        budget_status,
    )

    st.subheader(
        "📈 Verwachting"
    )

    metric_columns(
        [
            (
                "Verwachte inkomsten",
                euro(
                    forecast.get(
                        "projected_income",
                        0,
                    )
                ),
            ),
            (
                "Verwachte uitgaven",
                euro(
                    forecast.get(
                        "projected_expenses",
                        0,
                    )
                ),
            ),
            (
                "Verwacht netto",
                euro(
                    forecast.get(
                        "projected_net",
                        0,
                    )
                ),
            ),
            (
                "Financiële gezondheid",
                str(
                    health.get(
                        "status",
                        "Onbekend",
                    )
                ),
            ),
        ]
    )

    # ========================================================
    # RECURRING / TRANSFER DETAILS
    # ========================================================

    active_recurring = [
        row
        for row in recurring_rows
        if row.get(
            "active",
            True,
        )
    ]

    detail_cols = st.columns(
        4
    )

    detail_cols[0].metric(
        "Terugkerende kosten",
        euro(
            calculate_monthly_recurring_cost(
                active_recurring
            )
        ),
    )

    detail_cols[1].metric(
        "Terugkerende inkomsten",
        euro(
            calculate_monthly_recurring_income(
                active_recurring
            )
        ),
    )

    detail_cols[2].metric(
        "Actieve recurring items",
        str(
            len(
                active_recurring
            )
        ),
    )

    transfer_count = 0

    if "is_transfer" in month_df.columns:

        transfer_count = int(
            month_df[
                "is_transfer"
            ]
            .fillna(False)
            .sum()
        )

    detail_cols[3].metric(
        "Overboekingen",
        str(
            transfer_count
        ),
    )

    # ========================================================
    # SAFE TO SPEND
    # ========================================================

    safe_to_spend = calculate_safe_to_spend(
        forecast,
        buffer=500,
    )

    if safe_to_spend >= 0:

        st.success(
            f"Veilig te besteden: **{euro(safe_to_spend)}**"
        )

    else:

        st.error(
            "Let op: je verwachte ruimte is "
            f"**{euro(safe_to_spend)}**."
        )

    # ========================================================
    # HEALTH WARNINGS
    # ========================================================

    warnings = health.get(
        "warnings",
        [],
    )

    if warnings:

        st.subheader(
            "Aandachtspunten"
        )

        for warning in warnings:

            st.warning(
                str(warning)
            )


# ============================================================
# PAGE: TRANSACTIONS
# ============================================================

def page_transactions():

    st.title(
        "Transacties"
    )

    # ========================================================
    # CSV IMPORT
    # ========================================================

    if selected_account_id is None:

        st.info(
            "Selecteer een specifieke rekening "
            "in de sidebar om een CSV te importeren."
        )

    else:

        with st.expander(
            "📥 CSV importeren"
        ):

            uploaded_file = st.file_uploader(
                "Kies een CSV-bestand",
                type=["csv"],
            )

            if uploaded_file is not None:

                try:

                    raw_df = pd.read_csv(
                        uploaded_file,
                        sep=None,
                        engine="python",
                    )

                    prepared_df, mapping = (
                        prepare_import_dataframe(
                            raw_df,
                            merchant_rules,
                        )
                    )

                    st.caption(
                        "Herkende kolommen: "
                        f"datum={mapping['date']}, "
                        f"omschrijving={mapping['description']}, "
                        f"bedrag={mapping['amount']}, "
                        f"debit/credit={mapping['debit_credit']}"
                    )

                    preview_columns = [
                        column
                        for column in [
                            "date",
                            "description",
                            "merchant",
                            "amount",
                            "flow",
                            "category",
                        ]
                        if column
                        in prepared_df.columns
                    ]

                    st.dataframe(
                        prepared_df[
                            preview_columns
                        ],
                        use_container_width=True,
                        hide_index=True,
                    )

                    if st.button(
                        f"💾 {len(prepared_df)} transacties opslaan",
                        type="primary",
                    ):

                        records = (
                            dataframe_to_transaction_records(
                                prepared_df,
                                user_id,
                                selected_account_id,
                            )
                        )

                        saved = db_call(
                            "Transacties konden niet worden opgeslagen",
                            db.save_transactions,
                            records,
                        )

                        if saved is not None:

                            st.success(
                                f"{len(records)} transacties verwerkt."
                            )

                            st.rerun()

                except Exception as exc:

                    st.error(
                        f"Fout bij verwerken van CSV-bestand: {exc}"
                    )

    # ========================================================
    # TRANSACTION LIST
    # ========================================================

    if transaction_df.empty:

        st.info(
            "Nog geen transacties."
        )

        return

    render_transaction_metrics(
        transaction_df
    )

    display_df = transaction_df.copy()

    if "is_transfer" in display_df.columns:

        display_df["Type"] = (
            display_df[
                "is_transfer"
            ]
            .fillna(False)
            .map(
                {
                    True: "Overboeking",
                    False: "Normaal",
                }
            )
        )

    else:

        display_df["Type"] = "Normaal"

    columns = [
        column
        for column in [
            "date",
            "description",
            "merchant",
            "amount",
            "flow",
            "category",
            "Type",
        ]
        if column in display_df.columns
    ]

    st.dataframe(
        display_df[
            columns
        ],
        use_container_width=True,
        hide_index=True,
    )


# ============================================================
# PAGE: CATEGORIES
# ============================================================

def page_categories():

    st.title(
        "Categorieën"
    )

    all_transactions = load_transactions(
        user_id
    )

    if all_transactions.empty:

        st.info(
            "Nog geen transacties."
        )

        return

    all_transactions = (
        prepare_transactions(
            all_transactions
        )
    )

    all_transactions = (
        detect_transfer_transactions(
            all_transactions
        )
    )

    all_transactions = (
        without_transfers(
            all_transactions
        )
    )

    expenses = all_transactions[
        all_transactions["flow"]
        == "Uitgave"
    ].copy()

    if expenses.empty:

        st.info(
            "Nog geen uitgaven."
        )

        return

    # ========================================================
    # MERCHANT SUMMARY
    # ========================================================

    summary = (
        expenses
        .assign(
            amount=expenses[
                "amount"
            ].abs()
        )
        .groupby(
            "merchant"
        )
        .agg(
            transacties=(
                "amount",
                "count",
            ),
            totaal=(
                "amount",
                "sum",
            ),
        )
        .sort_values(
            "totaal",
            ascending=False,
        )
        .reset_index()
    )

    search = st.text_input(
        "Zoek merchant"
    )

    only_rules = st.checkbox(
        "Alleen merchants met eigen regel"
    )

    if search:

        summary = summary[
            summary["merchant"]
            .astype(str)
            .str.contains(
                search,
                case=False,
                na=False,
            )
        ]

    if only_rules:

        summary = summary[
            summary["merchant"].isin(
                merchant_rules
            )
        ]

    # ========================================================
    # MERCHANTS
    # ========================================================

    for _, row in summary.iterrows():

        merchant = row[
            "merchant"
        ]

        current_rule = (
            merchant_rules.get(
                merchant
            )
        )

        if current_rule is None:

            merchant_rows = expenses[
                expenses["merchant"]
                == merchant
            ]

            mode = (
                merchant_rows[
                    "category"
                ].mode()
            )

            if not mode.empty:

                current_category = mode.iloc[0]

            else:

                current_category = "Overig"

        else:

            current_category = current_rule

        with st.container(
            border=True
        ):

            left, middle, right = st.columns(
                [
                    2,
                    2,
                    1,
                ]
            )

            with left:

                st.write(
                    f"**{merchant}**"
                )

                st.caption(
                    f"{int(row['transacties'])} transacties · "
                    f"{euro(row['totaal'])}"
                )

            with middle:

                if current_category not in EXPENSE_CATEGORIES:

                    current_category = "Overig"

                new_category = st.selectbox(
                    "Categorie",
                    EXPENSE_CATEGORIES,
                    index=EXPENSE_CATEGORIES.index(
                        current_category
                    ),
                    key=f"category_{merchant}",
                )

            with right:

                st.write("")

                if st.button(
                    "Opslaan",
                    key=f"save_{merchant}",
                ):

                    result = db_call(
                        "Merchantregel kon niet worden opgeslagen",
                        db.save_merchant_category_rule,
                        user_id,
                        merchant,
                        new_category,
                    )

                    if result is not None:

                        db_call(
                            "Transacties konden niet worden bijgewerkt",
                            db.update_transactions_for_merchant,
                            user_id,
                            merchant,
                            new_category,
                        )

                        st.success(
                            "Opgeslagen."
                        )

                        st.rerun()

    # ========================================================
    # CUSTOM RULE
    # ========================================================

    st.subheader(
        "Eigen categorisatieregel toevoegen"
    )

    with st.form(
        "custom_rule"
    ):

        merchant = st.text_input(
            "Merchant"
        )

        category = st.selectbox(
            "Categorie",
            EXPENSE_CATEGORIES,
        )

        submitted = st.form_submit_button(
            "Regel opslaan"
        )

    if submitted:

        if not merchant.strip():

            st.error(
                "Vul een merchant in."
            )

        else:

            result = db_call(
                "Regel kon niet worden opgeslagen",
                db.save_merchant_category_rule,
                user_id,
                merchant.strip(),
                category,
            )

            if result is not None:

                st.success(
                    "Regel opgeslagen."
                )

                st.rerun()

    # ========================================================
    # EXISTING RULES
    # ========================================================

    if merchant_rules:

        st.subheader(
            "Mijn regels"
        )

        for (
            merchant,
            category,
        ) in sorted(
            merchant_rules.items()
        ):

            col1, col2, col3 = st.columns(
                [
                    3,
                    2,
                    1,
                ]
            )

            col1.write(
                merchant
            )

            col2.write(
                category
            )

            if col3.button(
                "Verwijder",
                key=f"delete_rule_{merchant}",
            ):

                db_call(
                    "Regel kon niet worden verwijderd",
                    db.delete_merchant_category_rule,
                    user_id,
                    merchant,
                )

                st.rerun()


# ============================================================
# PAGE: RECURRING
# ============================================================

def page_recurring():

    st.title(
        "Terugkerend"
    )

    # ========================================================
    # DETECT
    # ========================================================

    if st.button(
        "🔎 Terugkerende transacties opnieuw detecteren"
    ):

        # ----------------------------------------------------
        # SINGLE ACCOUNT
        # ----------------------------------------------------

        if selected_account_id:

            source = load_transactions(
                user_id,
                selected_account_id,
            )

            if not source.empty:

                source = prepare_transactions(
                    source
                )

            detected = (
                detect_recurring_transactions(
                    source
                )
            )

            records = []

            for item in detected:

                records.append(
                    {
                        "user_id": user_id,
                        "account_id": selected_account_id,
                        **item,
                        "active": True,
                    }
                )

            if records:

                result = db_call(
                    "Terugkerende transacties konden niet worden opgeslagen",
                    db.save_recurring_transactions,
                    records,
                )

                if result is not None:

                    st.success(
                        f"{len(records)} terugkerende items gevonden."
                    )

                    st.rerun()

            else:

                st.info(
                    "Geen terugkerende transacties gevonden."
                )

        # ----------------------------------------------------
        # ALL ACCOUNTS
        # ----------------------------------------------------

        else:

            total = 0

            for account in accounts:

                source = load_transactions(
                    user_id,
                    account["id"],
                )

                if source.empty:
                    continue

                source = prepare_transactions(
                    source
                )

                detected = (
                    detect_recurring_transactions(
                        source
                    )
                )

                records = [
                    {
                        "user_id": user_id,
                        "account_id": account["id"],
                        **item,
                        "active": True,
                    }
                    for item in detected
                ]

                if records:

                    result = db_call(
                        "Terugkerende transacties konden niet worden opgeslagen",
                        db.save_recurring_transactions,
                        records,
                    )

                    if result is not None:

                        total += len(
                            records
                        )

            if total:

                st.success(
                    f"{total} terugkerende items gevonden."
                )

                st.rerun()

            else:

                st.info(
                    "Geen terugkerende transacties gevonden."
                )

    # ========================================================
    # SPLIT ACTIVE / INACTIVE
    # ========================================================

    active = [
        row
        for row in recurring_rows
        if row.get(
            "active",
            True,
        )
    ]

    inactive = [
        row
        for row in recurring_rows
        if not row.get(
            "active",
            True,
        )
    ]

    metric_columns(
        [
            (
                "Maandelijkse kosten",
                euro(
                    calculate_monthly_recurring_cost(
                        active
                    )
                ),
            ),
            (
                "Maandelijkse inkomsten",
                euro(
                    calculate_monthly_recurring_income(
                        active
                    )
                ),
            ),
            (
                "Actief",
                str(
                    len(active)
                ),
            ),
            (
                "Inactief",
                str(
                    len(inactive)
                ),
            ),
        ]
    )

    # ========================================================
    # ACTIVE
    # ========================================================

    if active:

        st.subheader(
            "Actief"
        )

        for item in active:

            with st.container(
                border=True
            ):

                cols = st.columns(
                    [
                        3,
                        2,
                        1,
                        1,
                        1,
                    ]
                )

                cols[0].write(
                    f"**{item.get('merchant', 'Onbekend')}**"
                )

                cols[0].caption(
                    f"{item.get('category', 'Overig')} · "
                    f"{item.get('frequency', 'Maandelijks')}"
                )

                cols[1].write(
                    euro(
                        item.get(
                            "expected_amount",
                            0,
                        )
                    )
                )

                cols[1].caption(
                    "Volgende: "
                    f"{item.get('next_occurrence', '-')}"
                )

                cols[2].write(
                    item.get(
                        "reliability",
                        "-",
                    )
                )

                if cols[3].button(
                    "Pauzeer",
                    key=f"pause_{item['id']}",
                ):

                    db_call(
                        "Item kon niet worden aangepast",
                        db.update_recurring_active,
                        item["id"],
                        False,
                    )

                    st.rerun()

                if cols[4].button(
                    "Verwijder",
                    key=f"delete_recurring_{item['id']}",
                ):

                    db_call(
                        "Item kon niet worden verwijderd",
                        db.delete_recurring_transaction,
                        item["id"],
                    )

                    st.rerun()

    # ========================================================
    # INACTIVE
    # ========================================================

    if inactive:

        with st.expander(
            "Inactief"
        ):

            for item in inactive:

                cols = st.columns(
                    [
                        4,
                        2,
                        1,
                    ]
                )

                cols[0].write(
                    f"**{item.get('merchant', 'Onbekend')}** · "
                    f"{item.get('category', 'Overig')}"
                )

                cols[1].write(
                    euro(
                        item.get(
                            "expected_amount",
                            0,
                        )
                    )
                )

                if cols[2].button(
                    "Activeer",
                    key=f"activate_{item['id']}",
                ):

                    db_call(
                        "Item kon niet worden geactiveerd",
                        db.update_recurring_active,
                        item["id"],
                        True,
                    )

                    st.rerun()


# ============================================================
# PAGE: BUDGETS
# ============================================================

def page_budgets():

    st.title(
        "Budgetten"
    )

    # ========================================================
    # CREATE / UPDATE BUDGET
    # ========================================================

    with st.expander(
        "➕ Budget instellen"
    ):

        with st.form(
            "budget_form"
        ):

            category = st.selectbox(
                "Categorie",
                EXPENSE_CATEGORIES,
            )

            monthly_limit = st.number_input(
                "Maandbudget",
                min_value=0.0,
                step=25.0,
                value=500.0,
            )

            submitted = st.form_submit_button(
                "Budget opslaan",
                type="primary",
            )

        if submitted:

            result = db_call(
                "Budget kon niet worden opgeslagen",
                db.save_budget,
                user_id,
                category,
                monthly_limit,
            )

            if result is not None:

                st.success(
                    "Budget opgeslagen."
                )

                st.rerun()

    # ========================================================
    # NO BUDGETS
    # ========================================================

    if not budgets:

        st.info(
            "Je hebt nog geen budgetten ingesteld."
        )

        return

    if transaction_df.empty:

        st.info(
            "Er zijn nog geen transacties "
            "om tegen je budgetten af te zetten."
        )

        return

    selected_period = month_selectbox(
        transaction_df,
        key="budget_period",
    )

    if selected_period is None:
        return

    # ========================================================
    # BUDGET STATUS
    # ========================================================

    status = calculate_budget_status(
        transaction_df,
        budgets,
        selected_period,
    )

    if not status:

        st.info(
            "Geen budgetstatus beschikbaar."
        )

        return

    for item in status:

        category = item.get(
            "category",
            "Overig",
        )

        budget = float(
            item.get(
                "budget",
                0,
            )
            or 0
        )

        spent = float(
            item.get(
                "spent",
                0,
            )
            or 0
        )

        remaining = float(
            item.get(
                "remaining",
                budget - spent,
            )
            or 0
        )

        percentage = float(
            item.get(
                "percentage",
                0,
            )
            or 0
        )

        st.write(
            f"**{category}** — "
            f"{euro(spent)} / "
            f"{euro(budget)}"
        )

        st.progress(
            min(
                max(
                    percentage / 100,
                    0,
                ),
                1,
            )
        )

        if item.get(
            "over_budget"
        ):

            st.error(
                "Budget overschreden met "
                f"{euro(abs(remaining))}."
            )

        else:

            st.caption(
                f"Resterend: {euro(remaining)}"
            )


# ============================================================
# PAGE: SETTINGS
# ============================================================

def page_settings():

    st.title(
        "Instellingen"
    )

    # ========================================================
    # ACCOUNTS
    # ========================================================

    st.subheader(
        "Rekeningen"
    )

    for account in accounts:

        st.write(
            f"**{account.get('name', 'Onbekend')}** — "
            f"{account.get('bank', '')} — "
            f"{account.get('account_type', '')}"
        )

    # ========================================================
    # USER
    # ========================================================

    st.subheader(
        "Account"
    )

    st.write(
        user.email or ""
    )

    # ========================================================
    # CATEGORIES
    # ========================================================

    st.subheader(
        "Categorieën"
    )

    st.write(
        f"{len(CATEGORIES)} categorieën beschikbaar."
    )

    st.caption(
        "Inkomsten: "
        + ", ".join(
            [
                "Salaris",
                "Belasting",
                "Rente",
                "Overboeking spaargeld",
                "Tikkies",
                "Overige inkomsten",
            ]
        )
    )

    st.divider()

    st.caption(
        "Financial Cockpit"
    )


# ============================================================
# PAGE ROUTER
# ============================================================

PAGES = {
    "Overzicht": page_overview,
    "Transacties": page_transactions,
    "Categorieën": page_categories,
    "Terugkerend": page_recurring,
    "Budgetten": page_budgets,
    "Instellingen": page_settings,
}


PAGES[page]()
