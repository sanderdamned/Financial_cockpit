import pandas as pd
import numpy as np


# ============================================================
# TRANSACTION PREPARATION
# ============================================================

def prepare_transactions(transactions):
    """
    Convert raw Supabase transactions into a clean DataFrame.
    """

    if transactions is None:
        return pd.DataFrame()

    if isinstance(transactions, pd.DataFrame):
        if transactions.empty:
            return pd.DataFrame()

        df = transactions.copy()

    else:
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
        df["merchant"] = ""

    df = df[
        df["date"].notna() &
        df["amount"].notna()
    ].copy()

    return df

    df = pd.DataFrame(transactions)

    if df.empty:
        return df

    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")

    if "amount" in df.columns:
        df["amount"] = pd.to_numeric(df["amount"], errors="coerce")

    if "flow" not in df.columns:
        df["flow"] = "Onbekend"

    if "category" not in df.columns:
        df["category"] = "Overig"

    if "merchant" not in df.columns:
        df["merchant"] = ""

    df = df[
        df["date"].notna() &
        df["amount"].notna()
    ].copy()

    return df


# ============================================================
# TRANSFER DETECTION
# ============================================================

def detect_transfer_transactions(df, days_tolerance=1, amount_tolerance=0.01):
    """
    Detect likely internal transfers.

    A transfer is typically:
    - an income on one account
    - an expense on another account
    - same or almost same amount
    - close date
    - different account_id

    Returns a copy with:
    - is_transfer
    - original_flow
    """

    if df.empty:
        return df.copy()

    result = df.copy()

    result["is_transfer"] = False
    result["original_flow"] = result["flow"]

    if "account_id" not in result.columns:
        return result

    if result["account_id"].isna().all():
        return result

    income = result[result["flow"] == "Inkomst"].copy()
    expenses = result[result["flow"] == "Uitgave"].copy()

    if income.empty or expenses.empty:
        return result

    income["_amount_abs"] = income["amount"].abs()
    expenses["_amount_abs"] = expenses["amount"].abs()

    for income_idx, income_row in income.iterrows():

        candidates = expenses[
            (expenses["account_id"] != income_row["account_id"]) &
            (
                (
                    expenses["_amount_abs"] -
                    income_row["_amount_abs"]
                ).abs() <= amount_tolerance
            ) &
            (
                (
                    expenses["date"] -
                    income_row["date"]
                ).abs().dt.days <= days_tolerance
            )
        ]

        if not candidates.empty:

            expense_idx = candidates.index[0]

            result.loc[income_idx, "is_transfer"] = True
            result.loc[expense_idx, "is_transfer"] = True

    return result


# ============================================================
# FILTER REAL CASHFLOW
# ============================================================

def exclude_transfers(df):
    """
    Remove detected internal transfers from income/expense
    calculations.
    """

    if df.empty:
        return df.copy()

    if "is_transfer" not in df.columns:
        return df.copy()

    return df[~df["is_transfer"]].copy()


# ============================================================
# MONTHLY METRICS
# ============================================================

def calculate_monthly_metrics(
    df,
    period=None,
    exclude_internal_transfers=True
):

    if df.empty:
        return {
            "income": 0.0,
            "expenses": 0.0,
            "net": 0.0,
            "savings_rate": 0.0,
        }

    period_df = df.copy()

    if period is not None:
        period_df = period_df[
            period_df["date"].dt.to_period("M") == period
        ]

    if exclude_internal_transfers:
        period_df = exclude_transfers(period_df)

    income = period_df.loc[
        period_df["flow"] == "Inkomst",
        "amount"
    ].sum()

    expenses = period_df.loc[
        period_df["flow"] == "Uitgave",
        "amount"
    ].abs().sum()

    net = income - expenses

    savings_rate = (
        (net / income) * 100
        if income > 0
        else 0.0
    )

    return {
        "income": float(income),
        "expenses": float(expenses),
        "net": float(net),
        "savings_rate": float(savings_rate),
    }


# ============================================================
# CATEGORY SPENDING
# ============================================================

def calculate_category_spending(
    df,
    period=None,
    exclude_internal_transfers=True
):

    if df.empty:
        return {}

    period_df = df.copy()

    if period is not None:
        period_df = period_df[
            period_df["date"].dt.to_period("M") == period
        ]

    if exclude_internal_transfers:
        period_df = exclude_transfers(period_df)

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


# ============================================================
# BUDGET STATUS
# ============================================================

def calculate_budget_status(df, budgets, period):

    spending = calculate_category_spending(
        df,
        period
    )

    results = []

    for budget in budgets:

        category = budget.get(
            "category",
            "Overig"
        )

        limit = float(
            budget.get("monthly_limit", 0) or 0
        )

        spent = float(
            spending.get(category, 0)
        )

        remaining = limit - spent

        percentage = (
            spent / limit * 100
            if limit > 0
            else 0
        )

        results.append({
            "category": category,
            "budget": limit,
            "spent": spent,
            "remaining": remaining,
            "percentage": percentage,
            "over_budget": spent > limit,
        })

    return results


# ============================================================
# RECURRING FREQUENCY HELPERS
# ============================================================

def _frequency_interval(frequency):

    frequency = str(
        frequency or ""
    ).lower()

    if frequency in (
        "wekelijks",
        "weekly"
    ):
        return pd.Timedelta(days=7)

    if frequency in (
        "maandelijks",
        "monthly"
    ):
        return pd.DateOffset(months=1)

    if frequency in (
        "per kwartaal",
        "quarterly"
    ):
        return pd.DateOffset(months=3)

    if frequency in (
        "jaarlijks",
        "yearly",
        "annually"
    ):
        return pd.DateOffset(years=1)

    return None


def _monthly_frequency_multiplier(frequency):

    frequency = str(
        frequency or ""
    ).lower()

    if frequency in (
        "wekelijks",
        "weekly"
    ):
        return 52 / 12

    if frequency in (
        "maandelijks",
        "monthly"
    ):
        return 1

    if frequency in (
        "per kwartaal",
        "quarterly"
    ):
        return 1 / 3

    if frequency in (
        "jaarlijks",
        "yearly",
        "annually"
    ):
        return 1 / 12

    return 0


# ============================================================
# MONTHLY RECURRING COST
# ============================================================

def calculate_monthly_recurring_cost(
    recurring_transactions
):

    monthly_cost = 0.0

    for item in recurring_transactions:

        if not item.get("active", True):
            continue

        if item.get("flow", "Uitgave") != "Uitgave":
            continue

        amount = float(
            item.get("expected_amount", 0) or 0
        )

        multiplier = _monthly_frequency_multiplier(
            item.get("frequency")
        )

        monthly_cost += (
            amount * multiplier
        )

    return float(monthly_cost)


# ============================================================
# MONTHLY RECURRING INCOME
# ============================================================

def calculate_monthly_recurring_income(
    recurring_transactions
):

    monthly_income = 0.0

    for item in recurring_transactions:

        if not item.get("active", True):
            continue

        if item.get("flow") != "Inkomst":
            continue

        amount = float(
            item.get("expected_amount", 0) or 0
        )

        multiplier = _monthly_frequency_multiplier(
            item.get("frequency")
        )

        monthly_income += (
            amount * multiplier
        )

    return float(monthly_income)


# ============================================================
# RECURRING OCCURRENCES IN PERIOD
# ============================================================

def get_recurring_occurrences(
    item,
    period
):

    occurrences = []

    if not item.get("active", True):
        return occurrences

    next_occurrence = item.get(
        "next_occurrence"
    )

    if not next_occurrence:
        return occurrences

    occurrence = pd.to_datetime(
        next_occurrence,
        errors="coerce"
    )

    if pd.isna(occurrence):
        return occurrences

    month_start = period.start_time.normalize()
    month_end = period.end_time.normalize()

    interval = _frequency_interval(
        item.get("frequency")
    )

    if interval is None:
        return occurrences

    # Move forward until we reach the selected month.
    safety_counter = 0

    while occurrence < month_start:

        occurrence = occurrence + interval

        safety_counter += 1

        if safety_counter > 100:
            return occurrences

    # Collect ALL occurrences inside the month.
    safety_counter = 0

    while occurrence <= month_end:

        occurrences.append(
            occurrence
        )

        occurrence = occurrence + interval

        safety_counter += 1

        if safety_counter > 100:
            break

    return occurrences


# ============================================================
# RECURRING PAYMENTS REMAINING
# ============================================================

def calculate_recurring_remaining(
    recurring_transactions,
    period,
    today=None
):

    if not recurring_transactions:
        return 0.0

    if today is None:
        today = pd.Timestamp.today().normalize()

    total = 0.0

    for item in recurring_transactions:

        if not item.get("active", True):
            continue

        if item.get("flow", "Uitgave") != "Uitgave":
            continue

        amount = float(
            item.get("expected_amount", 0) or 0
        )

        occurrences = get_recurring_occurrences(
            item,
            period
        )

        for occurrence in occurrences:

            # Historical months:
            # nothing remains.
            if period < today.to_period("M"):
                continue

            # Current month:
            # only future occurrences remain.
            if (
                period == today.to_period("M")
                and occurrence <= today
            ):
                continue

            total += amount

    return float(total)


# ============================================================
# RECURRING INCOME REMAINING
# ============================================================

def calculate_recurring_income_remaining(
    recurring_transactions,
    period,
    today=None
):

    if not recurring_transactions:
        return 0.0

    if today is None:
        today = pd.Timestamp.today().normalize()

    total = 0.0

    for item in recurring_transactions:

        if not item.get("active", True):
            continue

        if item.get("flow") != "Inkomst":
            continue

        amount = float(
            item.get("expected_amount", 0) or 0
        )

        occurrences = get_recurring_occurrences(
            item,
            period
        )

        for occurrence in occurrences:

            if period < today.to_period("M"):
                continue

            if (
                period == today.to_period("M")
                and occurrence <= today
            ):
                continue

            total += amount

    return float(total)


# ============================================================
# HISTORICAL MONTHLY AVERAGES
# ============================================================

def calculate_historical_monthly_average(
    df,
    months=6
):

    if df.empty:
        return {
            "income": 0.0,
            "expenses": 0.0,
        }

    clean_df = exclude_transfers(df)

    clean_df = clean_df.copy()

    clean_df["month"] = (
        clean_df["date"]
        .dt.to_period("M")
    )

    latest_month = clean_df["month"].max()

    if pd.isna(latest_month):
        return {
            "income": 0.0,
            "expenses": 0.0,
        }

    start_month = (
        latest_month - (months - 1)
    )

    clean_df = clean_df[
        clean_df["month"] >= start_month
    ]

    monthly_income = (
        clean_df[
            clean_df["flow"] == "Inkomst"
        ]
        .groupby("month")["amount"]
        .sum()
    )

    monthly_expenses = (
        clean_df[
            clean_df["flow"] == "Uitgave"
        ]
        .groupby("month")["amount"]
        .apply(lambda x: x.abs().sum())
    )

    return {
        "income": float(
            monthly_income.mean()
            if not monthly_income.empty
            else 0
        ),
        "expenses": float(
            monthly_expenses.mean()
            if not monthly_expenses.empty
            else 0
        ),
    }


# ============================================================
# VARIABLE EXPENSE AVERAGE
# ============================================================

def calculate_variable_expense_average(
    df,
    recurring_transactions=None,
    months=6
):

    if df.empty:
        return 0.0

    clean_df = exclude_transfers(df)

    clean_df = clean_df[
        clean_df["flow"] == "Uitgave"
    ].copy()

    if clean_df.empty:
        return 0.0

    clean_df["month"] = (
        clean_df["date"]
        .dt.to_period("M")
    )

    # Remove recurring merchants where possible.
    recurring_merchants = set()

    for item in recurring_transactions or []:

        if item.get("active", True):

            merchant = str(
                item.get("merchant", "")
            ).strip().lower()

            if merchant:
                recurring_merchants.add(
                    merchant
                )

    if recurring_merchants:

        clean_df["_merchant"] = (
            clean_df["merchant"]
            .fillna("")
            .astype(str)
            .str.strip()
            .str.lower()
        )

        clean_df = clean_df[
            ~clean_df["_merchant"].isin(
                recurring_merchants
            )
        ]

    latest_month = clean_df["month"].max()

    if pd.isna(latest_month):
        return 0.0

    start_month = (
        latest_month - (months - 1)
    )

    clean_df = clean_df[
        clean_df["month"] >= start_month
    ]

    monthly = (
        clean_df
        .groupby("month")["amount"]
        .apply(lambda x: x.abs().sum())
    )

    if monthly.empty:
        return 0.0

    return float(
        monthly.mean()
    )


# ============================================================
# MONTH FORECAST 2.0
# ============================================================

def calculate_month_forecast(
    df,
    period,
    recurring_transactions=None,
    budgets=None
):

    recurring_transactions = (
        recurring_transactions or []
    )

    today = pd.Timestamp.today().normalize()

    # --------------------------------------------------------
    # Empty dataset
    # --------------------------------------------------------

    if df.empty:

        recurring_income = (
            calculate_monthly_recurring_income(
                recurring_transactions
            )
        )

        recurring_expenses = (
            calculate_monthly_recurring_cost(
                recurring_transactions
            )
        )

        return {
            "projected_income": float(
                recurring_income
            ),
            "projected_expenses": float(
                recurring_expenses
            ),
            "projected_net": float(
                recurring_income -
                recurring_expenses
            ),
            "actual_income": 0.0,
            "actual_expenses": 0.0,
            "remaining_days": 0,
            "recurring_remaining": 0.0,
            "recurring_income_remaining": 0.0,
            "variable_expenses_remaining": 0.0,
        }

    # --------------------------------------------------------
    # Current month transactions
    # --------------------------------------------------------

    period_df = df[
        df["date"].dt.to_period("M") == period
    ].copy()

    period_df = exclude_transfers(
        period_df
    )

    actual_income = float(
        period_df.loc[
            period_df["flow"] == "Inkomst",
            "amount"
        ].sum()
    )

    actual_expenses = float(
        period_df.loc[
            period_df["flow"] == "Uitgave",
            "amount"
        ].abs().sum()
    )

    # --------------------------------------------------------
    # Historical averages
    # --------------------------------------------------------

    historical = (
        calculate_historical_monthly_average(
            df,
            months=6
        )
    )

    historical_income = historical[
        "income"
    ]

    historical_expenses = historical[
        "expenses"
    ]

    variable_monthly = (
        calculate_variable_expense_average(
            df,
            recurring_transactions,
            months=6
        )
    )

    # --------------------------------------------------------
    # Historical / recurring income
    # --------------------------------------------------------

    recurring_income_monthly = (
        calculate_monthly_recurring_income(
            recurring_transactions
        )
    )

    recurring_expense_monthly = (
        calculate_monthly_recurring_cost(
            recurring_transactions
        )
    )

    # --------------------------------------------------------
    # Determine days
    # --------------------------------------------------------

    month_start = (
        period.start_time.normalize()
    )

    month_end = (
        period.end_time.normalize()
    )

    days_in_month = (
        month_end - month_start
    ).days + 1

    if period == today.to_period("M"):

        effective_today = min(
            max(today, month_start),
            month_end
        )

        days_elapsed = (
            effective_today -
            month_start
        ).days + 1

        remaining_days = max(
            0,
            days_in_month -
            days_elapsed
        )

    elif period < today.to_period("M"):

        days_elapsed = days_in_month
        remaining_days = 0

    else:

        days_elapsed = 0
        remaining_days = days_in_month

    # --------------------------------------------------------
    # HISTORICAL MONTH
    # --------------------------------------------------------

    if period < today.to_period("M"):

        projected_income = actual_income
        projected_expenses = actual_expenses

        recurring_remaining = 0.0
        recurring_income_remaining = 0.0
        variable_expenses_remaining = 0.0

    # --------------------------------------------------------
    # FUTURE MONTH
    # --------------------------------------------------------

    elif period > today.to_period("M"):

        projected_income = max(
            historical_income,
            recurring_income_monthly
        )

        projected_expenses = max(
            historical_expenses,
            recurring_expense_monthly +
            variable_monthly
        )

        recurring_remaining = (
            calculate_recurring_remaining(
                recurring_transactions,
                period,
                today
            )
        )

        recurring_income_remaining = (
            calculate_recurring_income_remaining(
                recurring_transactions,
                period,
                today
            )
        )

        variable_expenses_remaining = (
            variable_monthly
        )

    # --------------------------------------------------------
    # CURRENT MONTH
    # --------------------------------------------------------

    else:

        # Income:
        #
        # Do NOT extrapolate today's income
        # by multiplying it by the number of
        # remaining days.
        #
        # Instead estimate the expected full
        # monthly income from history / recurring.

        expected_monthly_income = max(
            historical_income,
            recurring_income_monthly,
            actual_income
        )

        recurring_income_remaining = (
            calculate_recurring_income_remaining(
                recurring_transactions,
                period,
                today
            )
        )

        # Actual income + expected future income.
        projected_income = max(
            actual_income +
            recurring_income_remaining,

            expected_monthly_income
        )

        # ----------------------------------------------------
        # Expenses
        # ----------------------------------------------------

        recurring_remaining = (
            calculate_recurring_remaining(
                recurring_transactions,
                period,
                today
            )
        )

        # Variable spending already made this month.
        actual_non_recurring_expenses = (
            actual_expenses
            - (
                calculate_recurring_cost_in_period(
                    recurring_transactions,
                    period,
                    today,
                    only_future=False
                )
            )
        )

        actual_non_recurring_expenses = max(
            0,
            actual_non_recurring_expenses
        )

        # Estimate remaining variable spending.
        #
        # Instead of daily extrapolation from day 1,
        # use historical monthly average.
        #
        # If we have already spent more than average,
        # don't add another full monthly average.

        expected_variable_total = max(
            0,
            variable_monthly
        )

        variable_remaining = max(
            0,
            expected_variable_total -
            actual_non_recurring_expenses
        )

        variable_expenses_remaining = (
            variable_remaining
        )

        projected_expenses = (
            actual_expenses
            + variable_expenses_remaining
            + recurring_remaining
        )

    projected_net = (
        projected_income -
        projected_expenses
    )

    return {
        "projected_income": float(
            projected_income
        ),
        "projected_expenses": float(
            projected_expenses
        ),
        "projected_net": float(
            projected_net
        ),
        "actual_income": float(
            actual_income
        ),
        "actual_expenses": float(
            actual_expenses
        ),
        "remaining_days": int(
            remaining_days
        ),
        "recurring_remaining": float(
            recurring_remaining
        ),
        "recurring_income_remaining": float(
            recurring_income_remaining
        ),
        "variable_expenses_remaining": float(
            variable_expenses_remaining
        ),
    }


# ============================================================
# RECURRING COST IN PERIOD
# ============================================================

def calculate_recurring_cost_in_period(
    recurring_transactions,
    period,
    today=None,
    only_future=False
):

    if not recurring_transactions:
        return 0.0

    if today is None:
        today = pd.Timestamp.today().normalize()

    total = 0.0

    for item in recurring_transactions:

        if not item.get("active", True):
            continue

        if item.get("flow", "Uitgave") != "Uitgave":
            continue

        amount = float(
            item.get("expected_amount", 0) or 0
        )

        occurrences = get_recurring_occurrences(
            item,
            period
        )

        for occurrence in occurrences:

            if only_future:

                if occurrence <= today:
                    continue

            total += amount

    return float(total)


# ============================================================
# FINANCIAL HEALTH
# ============================================================

def calculate_financial_health(
    forecast,
    budget_status
):

    score = 100
    warnings = []

    projected_net = float(
        forecast.get(
            "projected_net",
            0
        )
    )

    projected_income = float(
        forecast.get(
            "projected_income",
            0
        )
    )

    projected_expenses = float(
        forecast.get(
            "projected_expenses",
            0
        )
    )

    # --------------------------------------------------------
    # Cashflow
    # --------------------------------------------------------

    if projected_net < 0:

        score -= 40

        warnings.append(
            "🔴 Je verwachte uitgaven liggen "
            "hoger dan je verwachte inkomsten."
        )

    elif projected_income > 0:

        savings_rate = (
            projected_net /
            projected_income *
            100
        )

        if savings_rate < 10:

            score -= 20

            warnings.append(
                "🟠 Je verwachte spaarpercentage "
                "is lager dan 10%."
            )

        elif savings_rate < 20:

            score -= 10

            warnings.append(
                "🟡 Je verwachte spaarpercentage "
                "ligt tussen 10% en 20%."
            )

    # --------------------------------------------------------
    # Budgets
    # --------------------------------------------------------

    over_budget_count = 0

    for budget in budget_status:

        percentage = float(
            budget.get(
                "percentage",
                0
            )
        )

        if budget.get(
            "over_budget",
            False
        ):

            over_budget_count += 1

            warnings.append(
                f"🔴 {budget['category']} zit "
                f"€{abs(budget['remaining']):.2f} "
                f"boven het budget."
            )

        elif percentage >= 80:

            warnings.append(
                f"🟠 {budget['category']} heeft "
                f"al {percentage:.0f}% van het "
                f"budget gebruikt."
            )

    score -= min(
        over_budget_count * 10,
        30
    )

    score = max(
        0,
        min(
            100,
            round(score)
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
        "warnings": warnings,
    }


# ============================================================
# SAFE TO SPEND 2.0
# ============================================================

def calculate_safe_to_spend(
    forecast,
    buffer=0,
    additional_reserved=0
):

    projected_net = float(
        forecast.get(
            "projected_net",
            0
        ) or 0
    )

    buffer = float(
        buffer or 0
    )

    additional_reserved = float(
        additional_reserved or 0
    )

    safe_amount = (
        projected_net
        - buffer
        - additional_reserved
    )

    return max(
        0.0,
        safe_amount
    )


# ============================================================
# BUDGET RESERVED AMOUNT
# ============================================================

def calculate_remaining_budget_reserve(
    budget_status
):

    reserve = 0.0

    for budget in budget_status:

        remaining = float(
            budget.get(
                "remaining",
                0
            ) or 0
        )

        if remaining > 0:
            reserve += remaining

    return float(reserve)


# ============================================================
# PROJECTED ENDING CASHFLOW
# ============================================================

def calculate_projected_ending_cashflow(
    current_cashflow,
    forecast
):

    return float(
        current_cashflow +
        forecast.get(
            "projected_net",
            0
        )
    )
