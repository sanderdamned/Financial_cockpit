import pandas as pd


# ============================================================
# BASIC FINANCIAL METRICS
# ============================================================

def calculate_monthly_metrics(df, period):
    """
    Bereken inkomsten, uitgaven en netto resultaat
    voor een specifieke maand.
    """

    if df.empty:
        return {
            "income": 0.0,
            "expenses": 0.0,
            "net": 0.0
        }

    month_df = df[
        df["date"].dt.to_period("M") == period
    ].copy()

    income = month_df.loc[
        month_df["flow"] == "Inkomst",
        "amount"
    ].sum()

    expenses = month_df.loc[
        month_df["flow"] == "Uitgave",
        "amount"
    ].abs().sum()

    return {
        "income": float(income),
        "expenses": float(expenses),
        "net": float(income - expenses)
    }


# ============================================================
# CURRENT MONTH
# ============================================================

def get_current_period():
    """
    Geeft de huidige maand terug als pandas Period.
    """

    return pd.Timestamp.today().to_period("M")


# ============================================================
# TRANSACTION DATA
# ============================================================

def prepare_transaction_dataframe(transactions):
    """
    Zet Supabase transacties om naar een bruikbaar DataFrame.
    """

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

    df = df[
        df["date"].notna()
        & df["amount"].notna()
    ].copy()

    return df


# ============================================================
# RECURRING MONTHLY COST
# ============================================================

def calculate_monthly_recurring_cost(
    recurring_transactions
):
    """
    Zet wekelijkse, maandelijkse, kwartaal- en
    jaarlijkse recurring payments om naar een
    gemiddelde maandlast.
    """

    monthly_cost = 0.0

    for item in recurring_transactions:

        if not item.get("active", True):
            continue

        amount = float(
            item.get("expected_amount", 0) or 0
        )

        frequency = item.get(
            "frequency",
            ""
        )

        if frequency == "Wekelijks":

            monthly_cost += (
                amount * 52 / 12
            )

        elif frequency == "Maandelijks":

            monthly_cost += amount

        elif frequency == "Per kwartaal":

            monthly_cost += (
                amount / 3
            )

        elif frequency == "Jaarlijks":

            monthly_cost += (
                amount / 12
            )

    return float(monthly_cost)


# ============================================================
# MONTH FORECAST
# ============================================================

def calculate_month_forecast(
    df,
    selected_period,
    recurring_transactions
):
    """
    Baseline forecast voor de geselecteerde maand.

    Dit is bewust nog geen 'smart forecast'.
    Die bouwen we in de volgende stap.
    """

    if df.empty:
        return None

    current_period = get_current_period()

    if selected_period != current_period:
        return None

    month_df = df[
        df["date"].dt.to_period("M")
        == selected_period
    ].copy()

    today = pd.Timestamp.today()

    days_elapsed = today.day
    days_in_month = today.days_in_month

    if days_elapsed <= 0:
        return None

    expenses_so_far = month_df.loc[
        month_df["flow"] == "Uitgave",
        "amount"
    ].abs().sum()

    income_so_far = month_df.loc[
        month_df["flow"] == "Inkomst",
        "amount"
    ].sum()

    projected_expenses = (
        expenses_so_far
        / days_elapsed
        * days_in_month
    )

    projected_income = (
        income_so_far
        / days_elapsed
        * days_in_month
    )

    recurring_remaining = 0.0

    for item in recurring_transactions:

        if not item.get("active", True):
            continue

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
                == selected_period
                and next_date >= today
            ):

                recurring_remaining += float(
                    item.get(
                        "expected_amount",
                        0
                    ) or 0
                )

        except Exception:
            pass

    projected_expenses += recurring_remaining

    projected_net = (
        projected_income
        - projected_expenses
    )

    return {
        "income_so_far": float(
            income_so_far
        ),

        "expenses_so_far": float(
            expenses_so_far
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

        "recurring_remaining": float(
            recurring_remaining
        )
    }
