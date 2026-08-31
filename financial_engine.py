import pandas as pd
from datetime import datetime


# ============================================================
# GENERAL HELPERS
# ============================================================

def prepare_transactions(transactions):
    """
    Convert database transactions into a clean DataFrame.
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
# MONTHLY FINANCIALS
# ============================================================

def calculate_monthly_metrics(
    df,
    period
):
    """
    Calculate income, expenses and net result
    for a specific month.
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
# RECURRING COSTS
# ============================================================

def calculate_monthly_recurring_cost(
    recurring_transactions
):
    """
    Convert recurring payments into an estimated
    monthly cost.
    """

    monthly_cost = 0.0

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

    return round(
        monthly_cost,
        2
    )


# ============================================================
# RECURRING PAYMENTS DUE THIS MONTH
# ============================================================

def calculate_recurring_remaining(
    recurring_transactions,
    selected_period,
    today=None
):
    """
    Calculate recurring payments that are still expected
    during the selected month.
    """

    if today is None:
        today = pd.Timestamp.today()

    if not isinstance(today, pd.Timestamp):
        today = pd.Timestamp(today)

    total = 0.0

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

        except Exception:
            continue

        if (
            next_date.to_period("M")
            == selected_period
            and next_date >= today
        ):

            total += float(
                item.get(
                    "expected_amount",
                    0
                ) or 0
            )

    return round(
        total,
        2
    )


# ============================================================
# CURRENT MONTH FORECAST
# ============================================================

def calculate_month_forecast(
    df,
    selected_period,
    recurring_transactions,
    budgets=None,
    today=None
):
    """
    Intelligent monthly forecast.

    Calculates:

    - income so far
    - expenses so far
    - projected income
    - projected expenses
    - remaining recurring payments
    - projected net
    """

    if df.empty:
        return None

    if today is None:
        today = pd.Timestamp.today()

    if not isinstance(today, pd.Timestamp):
        today = pd.Timestamp(today)

    month_df = df[
        df["date"].dt.to_period("M")
        == selected_period
    ].copy()

    if month_df.empty:
        return None

    # --------------------------------------------------------
    # Only forecast the current month
    # --------------------------------------------------------

    if (
        selected_period
        != today.to_period("M")
    ):
        return None

    days_elapsed = today.day
    days_in_month = today.days_in_month

    # --------------------------------------------------------
    # Actual income
    # --------------------------------------------------------

    income_so_far = month_df.loc[
        month_df["flow"] == "Inkomst",
        "amount"
    ].sum()

    # --------------------------------------------------------
    # Actual expenses
    # --------------------------------------------------------

    expenses_so_far = month_df.loc[
        month_df["flow"] == "Uitgave",
        "amount"
    ].abs().sum()

    # --------------------------------------------------------
    # Project income
    # --------------------------------------------------------

    projected_income = (
        income_so_far
        / days_elapsed
        * days_in_month
    )

    # --------------------------------------------------------
    # Project expenses
    # --------------------------------------------------------

    projected_expenses = (
        expenses_so_far
        / days_elapsed
        * days_in_month
    )

    # --------------------------------------------------------
    # Add remaining recurring payments
    # --------------------------------------------------------

    recurring_remaining = (
        calculate_recurring_remaining(
            recurring_transactions,
            selected_period,
            today
        )
    )

    projected_expenses += (
        recurring_remaining
    )

    # --------------------------------------------------------
    # Net
    # --------------------------------------------------------

    projected_net = (
        projected_income
        - projected_expenses
    )

    # --------------------------------------------------------
    # Savings rate
    # --------------------------------------------------------

    savings_rate = (
        projected_net
        / projected_income
        * 100
        if projected_income > 0
        else 0
    )

    return {
        "income_so_far": round(
            float(income_so_far),
            2
        ),

        "expenses_so_far": round(
            float(expenses_so_far),
            2
        ),

        "projected_income": round(
            float(projected_income),
            2
        ),

        "projected_expenses": round(
            float(projected_expenses),
            2
        ),

        "recurring_remaining": round(
            float(recurring_remaining),
            2
        ),

        "projected_net": round(
            float(projected_net),
            2
        ),

        "projected_savings_rate": round(
            float(savings_rate),
            1
        )
    }


# ============================================================
# BUDGET ANALYSIS
# ============================================================

def calculate_budget_status(
    df,
    budgets,
    selected_period
):
    """
    Compare actual spending with monthly budgets.
    """

    if not budgets:
        return []

    if df.empty:
        return []

    month_df = df[
        df["date"].dt.to_period("M")
        == selected_period
    ].copy()

    month_df = month_df[
        month_df["flow"] == "Uitgave"
    ].copy()

    if month_df.empty:
        spending = {}

    else:

        month_df["expense_amount"] = (
            month_df["amount"].abs()
        )

        spending = (
            month_df
            .groupby("category")[
                "expense_amount"
            ]
            .sum()
            .to_dict()
        )

    results = []

    for budget in budgets:

        category = budget.get(
            "category"
        )

        budget_amount = float(
            budget.get(
                "monthly_limit",
                0
            ) or 0
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

        results.append(
            {
                "category": category,

                "budget": round(
                    budget_amount,
                    2
                ),

                "spent": round(
                    spent,
                    2
                ),

                "remaining": round(
                    remaining,
                    2
                ),

                "percentage": round(
                    percentage,
                    1
                ),

                "over_budget":
                    spent > budget_amount
            }
        )

    return results


# ============================================================
# FINANCIAL HEALTH
# ============================================================

def calculate_financial_health(
    forecast,
    budget_status
):
    """
    Create a simple Financial Health score.

    This is deliberately simple for now.
    Later we can make this significantly smarter.
    """

    if not forecast:
        return None

    score = 100
    warnings = []

    # --------------------------------------------------------
    # Negative forecast
    # --------------------------------------------------------

    if forecast["projected_net"] < 0:

        score -= 40

        warnings.append(
            "Je verwachte maandresultaat is negatief."
        )

    # --------------------------------------------------------
    # Low savings rate
    # --------------------------------------------------------

    savings_rate = forecast[
        "projected_savings_rate"
    ]

    if 0 <= savings_rate < 10:

        score -= 15

        warnings.append(
            "Je verwachte spaarpercentage is laag."
        )

    # --------------------------------------------------------
    # Budgets
    # --------------------------------------------------------

    for budget in budget_status:

        if budget["over_budget"]:

            score -= 10

            warnings.append(
                f"Je budget voor "
                f"{budget['category']} "
                f"is overschreden."
            )

    score = max(
        0,
        min(
            100,
            score
        )
    )

    if score >= 80:

        status = "Gezond"

    elif score >= 60:

        status = "Redelijk"

    elif score >= 40:

        status = "Aandacht nodig"

    else:

        status = "Kritiek"

    return {
        "score": score,
        "status": status,
        "warnings": warnings
    }


# ============================================================
# SAFE SPENDING
# ============================================================

def calculate_safe_to_spend(
    forecast,
    buffer=0
):
    """
    First version of 'Je kunt veilig €X uitgeven'.

    Later this will also incorporate:
    - actual bank balance
    - upcoming salary
    - recurring payments
    - budgets
    - 30/60/90 day obligations
    """

    if not forecast:
        return 0.0

    projected_net = float(
        forecast.get(
            "projected_net",
            0
        )
    )

    safe_amount = (
        projected_net
        - float(buffer)
    )

    return round(
        max(
            safe_amount,
            0
        ),
        2
    )
