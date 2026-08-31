import pandas as pd


def prepare_transactions(transactions):
    """
    Zet Supabase-transacties om naar een bruikbare DataFrame.
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


def calculate_period_metrics(
    df,
    period=None
):
    """
    Bereken inkomsten, uitgaven en netto resultaat
    voor een bepaalde maand.

    period:
        pandas Period("2026-08", freq="M")
    """

    if df.empty:
        return {
            "income": 0.0,
            "expenses": 0.0,
            "net": 0.0
        }

    period_df = df.copy()

    if period is not None:

        period_df = period_df[
            period_df["date"].dt.to_period("M")
            == period
        ]

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
        "net": float(
            income - expenses
        )
    }


def calculate_category_spending(
    df,
    period=None
):
    """
    Geeft uitgaven per categorie terug.
    """

    if df.empty:
        return {}

    period_df = df.copy()

    if period is not None:

        period_df = period_df[
            period_df["date"].dt.to_period("M")
            == period
        ]

    period_df = period_df[
        period_df["flow"] == "Uitgave"
    ].copy()

    if period_df.empty:
        return {}

    period_df["expense_amount"] = (
        period_df["amount"].abs()
    )

    return (
        period_df
        .groupby("category")["expense_amount"]
        .sum()
        .to_dict()
    )


def calculate_budget_status(
    df,
    budgets,
    period
):
    """
    Vergelijk werkelijke uitgaven met budgetten.
    """

    spending = calculate_category_spending(
        df,
        period
    )

    results = []

    for budget in budgets:

        category = budget.get(
            "category"
        )

        limit = float(
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

        remaining = limit - spent

        percentage = (
            spent / limit * 100
            if limit > 0
            else 0
        )

        results.append(
            {
                "category": category,
                "budget": limit,
                "spent": spent,
                "remaining": remaining,
                "percentage": percentage,
                "over_budget": spent > limit
            }
        )

    def calculate_monthly_recurring_cost(
    recurring_transactions
):
    """
    Zet alle recurring payments om naar
    een geschatte maandelijkse kostenpost.
    """

    monthly_cost = 0.0

    for item in recurring_transactions:

        if not item.get(
            "active",
            True
        ):
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

    return float(monthly_cost)

    return results
