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
# FINANCIAL PERIODS
# ============================================================

def get_financial_period_start(value, start_day=1, period_type="maandelijks"):
    """Return the start date of the financial period containing value.

    Monthly periods start on the configured day of each month. Four-week
    periods use a stable 28-day cycle anchored to that day in January 2000.
    """
    timestamp = pd.Timestamp(value).normalize()
    start_day = max(1, min(31, int(start_day or 1)))
    period_type = str(period_type or "maandelijks").strip().lower()

    if period_type in ("4 weken", "4-weken", "4_weken", "vier weken", "four weeks"):
        anchor = pd.Timestamp(year=2000, month=1, day=start_day)
        elapsed_days = (timestamp - anchor).days
        return anchor + pd.Timedelta(days=(elapsed_days // 28) * 28)

    day = min(start_day, pd.Period(timestamp, freq="M").days_in_month)
    candidate = pd.Timestamp(year=timestamp.year, month=timestamp.month, day=day)
    if timestamp < candidate:
        previous_month = timestamp - pd.DateOffset(months=1)
        previous_day = min(start_day, pd.Period(previous_month, freq="M").days_in_month)
        candidate = pd.Timestamp(
            year=previous_month.year,
            month=previous_month.month,
            day=previous_day,
        )
    return candidate


def _shift_financial_period_start(period_start, periods, start_day=1, period_type="maandelijks"):
    """Move a financial period start backwards or forwards by whole periods."""
    period_start = pd.Timestamp(period_start).normalize()
    period_type = str(period_type or "maandelijks").strip().lower()
    if period_type in ("4 weken", "4-weken", "4_weken", "vier weken", "four weeks"):
        return period_start + pd.Timedelta(days=28 * int(periods))

    target_month = period_start + pd.DateOffset(months=int(periods))
    day = min(max(1, int(start_day or 1)), pd.Period(target_month, freq="M").days_in_month)
    return pd.Timestamp(year=target_month.year, month=target_month.month, day=day)


# ============================================================
# RECURRING TRANSACTION DETECTION
# ============================================================

def detect_recurring_transactions(
    df,
    period_start_day=1,
    period_type="maandelijks",
    today=None,
):
    """Find expenses that occurred in each of the last 3 completed periods."""
    if df is None or df.empty:
        return []

    required = {"date", "merchant", "amount", "flow"}
    if not required.issubset(df.columns):
        return []

    data = df.copy()
    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    data["amount"] = pd.to_numeric(data["amount"], errors="coerce")
    data = data.dropna(subset=["date", "amount", "merchant"])
    data = data[data["flow"].astype(str).str.strip().eq("Uitgave")].copy()
    if data.empty:
        return []

    if "is_transfer" in data.columns:
        data = data[~data["is_transfer"].fillna(False).astype(bool)].copy()
    if "category" in data.columns:
        internal = data["category"].fillna("").astype(str).str.strip().str.lower().eq("overboeking spaargeld")
        data = data[~internal].copy()

    transfer_pattern = r"overboeking|eigen rekening|spaarrekening|spaargeld|transfer from|overgemaakt van|interne overboeking"
    descriptions = data.get("description", pd.Series("", index=data.index)).fillna("").astype(str)
    merchants = data["merchant"].fillna("").astype(str)
    data = data[~(descriptions + " " + merchants).str.contains(transfer_pattern, case=False, regex=True, na=False)].copy()
    data["merchant"] = data["merchant"].astype(str).str.strip()
    data = data[data["merchant"].ne("")]
    if data.empty:
        return []

    today_ts = pd.Timestamp(today if today is not None else pd.Timestamp.today()).normalize()
    current_start = get_financial_period_start(today_ts, period_start_day, period_type)
    completed_starts = [
        _shift_financial_period_start(current_start, -offset, period_start_day, period_type)
        for offset in (1, 2, 3)
    ]
    completed_start_set = set(completed_starts)
    last_completed_end = current_start - pd.Timedelta(days=1)

    data = data[(data["date"] <= last_completed_end)].copy()
    if data.empty:
        return []

    data["financial_period_start"] = data["date"].map(
        lambda value: get_financial_period_start(value, period_start_day, period_type)
    )
    data = data[data["financial_period_start"].isin(completed_start_set)].copy()
    if data.empty:
        return []

    results = []
    four_week = str(period_type or "").strip().lower() in (
        "4 weken", "4-weken", "4_weken", "vier weken", "four weeks"
    )
    interval_min, interval_max = (23, 33) if four_week else (20, 40)

    for merchant, group in data.groupby("merchant"):
        group = group.sort_values("date").copy()
        counts = group.groupby("financial_period_start").size()
        # Exactly one payment per period helps avoid mistaking regular shopping
        # at the same merchant for a recurring bill.
        if any(int(counts.get(period_start, 0)) != 1 for period_start in completed_starts):
            continue

        period_rows = []
        for period_start in completed_starts:
            match = group[group["financial_period_start"] == period_start]
            if match.empty:
                period_rows = []
                break
            period_rows.append(match.iloc[0])
        if len(period_rows) != 3:
            continue

        period_rows = sorted(period_rows, key=lambda row: row["date"])
        dates = [pd.Timestamp(row["date"]) for row in period_rows]
        intervals = [(dates[index] - dates[index - 1]).days for index in range(1, len(dates))]
        median_interval = float(pd.Series(intervals).median())
        if not interval_min <= median_interval <= interval_max:
            continue

        amounts = [abs(float(row["amount"])) for row in period_rows]
        mean_amount = float(sum(amounts) / len(amounts))
        if mean_amount <= 0:
            continue

        variation = (max(amounts) - min(amounts)) / mean_amount
        reliability = "Hoog" if variation <= 0.15 else ("Gemiddeld" if variation <= 0.30 else "Laag")
        categories = [str(row.get("category", "Overig") or "Overig") for row in period_rows]
        category = pd.Series(categories).mode().iloc[0] if categories else "Overig"
        last_occurrence = dates[-1]
        next_occurrence = (
            last_occurrence + pd.Timedelta(days=28)
            if four_week
            else last_occurrence + pd.DateOffset(months=1)
        )

        period_amounts = {}
        for period_start, row, amount in zip(completed_starts, reversed(period_rows), reversed(amounts)):
            period_amounts[period_start.strftime("%d-%m-%Y")] = amount

        results.append({
            "merchant": merchant,
            "category": category,
            "frequency": "Elke 4 weken" if four_week else "Maandelijks",
            "expected_amount": mean_amount,
            "last_occurrence": last_occurrence.date().isoformat(),
            "next_occurrence": next_occurrence.date().isoformat(),
            "reliability": reliability,
            "flow": "Uitgave",
            "is_one_time_large": False,
            "period_amounts": period_amounts,
            "period_count": 3,
        })

    return sorted(results, key=lambda item: item.get("expected_amount", 0), reverse=True)


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

    result = df.copy()

    if "is_transfer" in result.columns:
        result = result[~result["is_transfer"].fillna(False)].copy()

    # Savings/internal transfers are not income or expenses. Exclude both
    # the incoming and outgoing leg from all ordinary financial calculations.
    if "category" in result.columns:
        internal_category = result["category"].fillna("").astype(str).str.strip().str.lower().eq("overboeking spaargeld")
        result = result[~internal_category].copy()

    descriptions = result.get("description", pd.Series("", index=result.index)).fillna("").astype(str)
    merchants = result.get("merchant", pd.Series("", index=result.index)).fillna("").astype(str)
    transfer_like = (descriptions + " " + merchants).str.contains(
        r"overboeking|eigen rekening|spaarrekening|spaargeld|transfer from|overgemaakt van|interne overboeking",
        case=False, regex=True, na=False,
    )
    result = result[~transfer_like].copy()

    return result


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

        if str(item.get("category", "")).strip().lower() == "overboeking spaargeld":
            continue

        # Lage betrouwbaarheid niet meenemen
        if item.get("reliability") == "Laag":
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
# YEARLY RECURRING COST
# ============================================================

def calculate_yearly_recurring_cost(
    recurring_transactions
):

    yearly_cost = 0.0

    for item in recurring_transactions:

        if not item.get("active", True):
            continue

        if item.get("flow", "Uitgave") != "Uitgave":
            continue

        if str(item.get("category", "")).strip().lower() == "overboeking spaargeld":
            continue

        if item.get("reliability") == "Laag":
            continue

        if item.get("frequency") != "Jaarlijks":
            continue

        amount = float(
            item.get("expected_amount", 0) or 0
        )

        yearly_cost += amount

    return float(yearly_cost)


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

        if str(item.get("category", "")).strip().lower() == "overboeking spaargeld":
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

        if str(item.get("category", "")).strip().lower() == "overboeking spaargeld":
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

        if str(item.get("category", "")).strip().lower() == "overboeking spaargeld":
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
    """
    Calculate a baseline from completed months only.

    The current month is intentionally excluded: its transactions are
    incomplete and using them in a monthly average can materially
    understate normal spending or income.
    """
    empty_result = {
        "income": 0.0,
        "expenses": 0.0,
    }

    if df is None or df.empty:
        return empty_result

    clean_df = exclude_transfers(df).copy()

    if "date" not in clean_df.columns or "flow" not in clean_df.columns:
        return empty_result

    clean_df["date"] = pd.to_datetime(
        clean_df["date"],
        errors="coerce",
    )
    clean_df["amount"] = pd.to_numeric(
        clean_df["amount"],
        errors="coerce",
    ).fillna(0)
    clean_df = clean_df.dropna(subset=["date"])

    if clean_df.empty:
        return empty_result

    clean_df["month"] = clean_df["date"].dt.to_period("M")
    latest_month = clean_df["month"].max()
    current_month = pd.Timestamp.today().to_period("M")

    # Never use an incomplete current month as the baseline month.
    if latest_month >= current_month:
        latest_month = current_month - 1

    start_month = latest_month - (max(1, int(months)) - 1)
    clean_df = clean_df[
        (clean_df["month"] >= start_month)
        & (clean_df["month"] <= latest_month)
    ]

    if clean_df.empty:
        return empty_result

    monthly_income = (
        clean_df[clean_df["flow"] == "Inkomst"]
        .groupby("month")["amount"]
        .sum()
    )
    monthly_expenses = (
        clean_df[clean_df["flow"] == "Uitgave"]
        .groupby("month")["amount"]
        .apply(lambda values: values.abs().sum())
    )

    return {
        "income": float(monthly_income.mean()) if not monthly_income.empty else 0.0,
        "expenses": float(monthly_expenses.mean()) if not monthly_expenses.empty else 0.0,
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

    # Exclude an incomplete current month from the spending baseline.
    current_month = pd.Timestamp.today().to_period("M")
    if latest_month >= current_month:
        latest_month = current_month - 1

    start_month = latest_month - (max(1, int(months)) - 1)

    clean_df = clean_df[
        (clean_df["month"] >= start_month)
        & (clean_df["month"] <= latest_month)
    ]

    if clean_df.empty:
        return 0.0

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

        if str(item.get("category", "")).strip().lower() == "overboeking spaargeld":
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
# PROJECTED ACCOUNT BALANCE
# ============================================================

def calculate_recurring_transfer_net_in_period(
    recurring_transactions,
    period,
    today=None,
):
    """Estimate future internal transfers for one account, with account-level signs."""
    if not recurring_transactions:
        return 0.0

    if today is None:
        today = pd.Timestamp.today().normalize()

    selected_period = pd.Period(period, freq="M")
    total = 0.0

    for item in recurring_transactions:
        if not item.get("active", True):
            continue

        if str(item.get("category", "")).strip().lower() != "overboeking spaargeld":
            continue

        flow = str(item.get("flow", "")).strip()
        if flow not in ("Inkomst", "Uitgave"):
            continue

        amount = abs(float(item.get("expected_amount", 0) or 0))
        for occurrence in get_recurring_occurrences(item, selected_period):
            if selected_period < today.to_period("M"):
                continue
            if selected_period == today.to_period("M") and occurrence <= today:
                continue

            total += amount if flow == "Inkomst" else -amount

    return float(total)


def calculate_projected_account_balance(
    current_balance,
    balance_as_of,
    df,
    recurring_transactions=None,
    period=None,
    today=None,
):
    """
    Project one account's balance through the end of the selected month.

    The entered balance is reconciled with imported transactions after its
    as-of date. Ordinary income/expenses use the household cashflow forecast;
    scheduled savings transfers are then added separately because they change
    an individual account balance but are not household income or expenses.
    """
    if current_balance is None or balance_as_of in (None, ""):
        return {
            "available": False,
            "reason": "Vul eerst het actuele saldo en de peildatum in via Instellingen.",
        }

    if today is None:
        today = pd.Timestamp.today().normalize()
    else:
        today = pd.Timestamp(today).normalize()

    try:
        selected_period = pd.Period(period, freq="M")
        as_of = pd.Timestamp(balance_as_of).normalize()
    except Exception:
        return {
            "available": False,
            "reason": "Het saldo of de peildatum is niet geldig.",
        }

    if selected_period < today.to_period("M"):
        return {
            "available": False,
            "reason": "Een eindsaldoprognose is alleen beschikbaar voor de huidige of een toekomstige maand.",
        }

    if as_of > today:
        return {
            "available": False,
            "reason": "De peildatum ligt in de toekomst. Vul een actueel saldo met een datum van vandaag of eerder in.",
        }

    if df is None or df.empty or not {"date", "flow", "amount"}.issubset(df.columns):
        return {
            "available": False,
            "reason": "Importeer transacties om het saldo sinds de peildatum en de prognose te kunnen berekenen.",
        }

    transactions = df.copy()
    transactions["date"] = pd.to_datetime(transactions["date"], errors="coerce")
    transactions["amount"] = pd.to_numeric(transactions["amount"], errors="coerce").fillna(0)
    transactions = transactions.dropna(subset=["date"])

    # An account balance includes transfers, unlike household income/expense totals.
    transactions_after_as_of = transactions[
        (transactions["date"].dt.normalize() > as_of)
        & (transactions["date"].dt.normalize() <= today)
    ].copy()

    if not transactions_after_as_of.empty:
        signed_amounts = transactions_after_as_of["amount"].abs()
        signed_amounts = signed_amounts.where(
            transactions_after_as_of["flow"] == "Inkomst",
            -signed_amounts.where(
                transactions_after_as_of["flow"] == "Uitgave",
                0.0,
            ),
        )
        balance_today = float(current_balance) + float(signed_amounts.sum())
    else:
        balance_today = float(current_balance)

    projected_balance = balance_today
    current_month = today.to_period("M")
    recurring_transactions = recurring_transactions or []

    for forecast_period in pd.period_range(
        current_month,
        selected_period,
        freq="M",
    ):
        month_forecast = calculate_month_forecast(
            transactions,
            forecast_period,
            recurring_transactions,
        )

        if forecast_period == current_month:
            actual_net = (
                float(month_forecast.get("actual_income", 0) or 0)
                - float(month_forecast.get("actual_expenses", 0) or 0)
            )
            projected_external_change = (
                float(month_forecast.get("projected_net", 0) or 0)
                - actual_net
            )
        else:
            projected_external_change = float(
                month_forecast.get("projected_net", 0) or 0
            )

        transfer_change = calculate_recurring_transfer_net_in_period(
            recurring_transactions,
            forecast_period,
            today=today,
        )

        projected_balance += projected_external_change + transfer_change

    return {
        "available": True,
        "balance_today_estimate": float(balance_today),
        "projected_balance": float(projected_balance),
        "projected_change": float(projected_balance - balance_today),
        "period": str(selected_period),
        "note": (
            "Schatting op basis van het ingevoerde saldo, geïmporteerde "
            "transacties sinds de peildatum en de cashflowprognose. "
            "Controleer of alle transacties zijn geïmporteerd."
        ),
    }


# ============================================================
# FORECAST QUALITY AND ACTIONABLE INSIGHTS
# ============================================================

def calculate_forecast_data_quality(df, period, months=6):
    """Describe how much completed-month history supports a forecast."""
    try:
        selected_period = pd.Period(period, freq="M")
    except Exception:
        selected_period = pd.Timestamp.today().to_period("M")

    current_month = pd.Timestamp.today().to_period("M")
    reference_month = min(selected_period - 1, current_month - 1)
    start_month = reference_month - (max(1, int(months)) - 1)

    if df is None or df.empty or "date" not in df.columns:
        available_months = 0
    else:
        dates = pd.to_datetime(df["date"], errors="coerce")
        transaction_months = dates.dropna().dt.to_period("M")
        available_months = int(
            transaction_months[
                (transaction_months >= start_month)
                & (transaction_months <= reference_month)
            ].nunique()
        )

    if available_months >= 4:
        confidence = "Redelijk"
        note = (
            f"Gebaseerd op {available_months} volledig afgesloten "
            "maanden met transacties."
        )
    elif available_months >= 2:
        confidence = "Beperkt"
        note = (
            f"Er zijn {available_months} afgesloten historische maanden "
            "beschikbaar. Zie de prognose als een indicatie."
        )
    else:
        confidence = "Laag"
        note = (
            "Er is weinig volledige historische data. De prognose kan "
            "sterk afwijken en leunt relatief meer op terugkerende betalingen."
        )

    return {
        "months_available": available_months,
        "confidence": confidence,
        "note": note,
    }


def generate_financial_insights(
    df,
    period,
    forecast,
    budget_status=None,
):
    """
    Return explainable financial alerts based on the selected period.
    Insights are descriptive signals, not financial advice.
    """
    insights = []
    budget_status = budget_status or []

    projected_net = float(
        (forecast or {}).get("projected_net", 0) or 0
    )
    projected_income = float(
        (forecast or {}).get("projected_income", 0) or 0
    )
    projected_expenses = float(
        (forecast or {}).get("projected_expenses", 0) or 0
    )

    if projected_net < 0:
        insights.append({
            "level": "error",
            "title": "Verwacht maandtekort",
            "message": (
                f"De prognose komt ongeveer €{abs(projected_net):,.2f} "
                "negatief uit: verwachte uitgaven zijn hoger dan inkomsten."
            ).replace(",", "X").replace(".", ",").replace("X", "."),
        })
    elif projected_income > 0 and projected_expenses > projected_income * 0.9:
        insights.append({
            "level": "warning",
            "title": "Kleine financiële marge",
            "message": (
                "De verwachte uitgaven gebruiken meer dan 90% van de "
                "verwachte inkomsten. Houd extra ruimte aan voor onverwachte kosten."
            ),
        })

    for item in budget_status:
        category = str(item.get("category", "Categorie"))
        percentage = float(item.get("percentage", 0) or 0)
        remaining = float(item.get("remaining", 0) or 0)

        if item.get("over_budget", False):
            insights.append({
                "level": "error",
                "title": f"Budget overschreden: {category}",
                "message": (
                    f"Je zit €{abs(remaining):,.2f} boven het ingestelde budget."
                ).replace(",", "X").replace(".", ",").replace("X", "."),
            })
        elif percentage >= 80:
            insights.append({
                "level": "warning",
                "title": f"Budget bijna op: {category}",
                "message": (
                    f"{percentage:.0f}% van het budget is gebruikt; "
                    f"er resteert €{remaining:,.2f}."
                ).replace(",", "X").replace(".", ",").replace("X", "."),
            })

    try:
        selected_period = pd.Period(period, freq="M")
    except Exception:
        selected_period = pd.Timestamp.today().to_period("M")

    current_month = pd.Timestamp.today().to_period("M")
    if (
        df is not None
        and not df.empty
        and selected_period <= current_month
        and {"date", "flow", "amount"}.issubset(df.columns)
    ):
        clean_df = exclude_transfers(df).copy()
        clean_df["date"] = pd.to_datetime(clean_df["date"], errors="coerce")
        clean_df["amount"] = pd.to_numeric(clean_df["amount"], errors="coerce").fillna(0)
        clean_df = clean_df.dropna(subset=["date"])
        clean_df["month"] = clean_df["date"].dt.to_period("M")

        prior_months = [
            selected_period - offset
            for offset in (1, 2, 3)
        ]
        historical_df = clean_df[
            clean_df["month"].isin(prior_months)
            & (clean_df["flow"] == "Uitgave")
        ].copy()
        current_df = clean_df[
            (clean_df["month"] == selected_period)
            & (clean_df["flow"] == "Uitgave")
        ].copy()

        if (
            not historical_df.empty
            and not current_df.empty
            and "category" in clean_df.columns
        ):
            historical_months = int(historical_df["month"].nunique())
            if historical_months >= 2:
                historical_df["_expense"] = historical_df["amount"].abs()
                current_df["_expense"] = current_df["amount"].abs()
                averages = (
                    historical_df.groupby("category")["_expense"].sum()
                    / historical_months
                )
                current_spend = current_df.groupby("category")["_expense"].sum()

                if selected_period == current_month:
                    today = pd.Timestamp.today().normalize()
                    elapsed_days = max(1, today.day)
                    days_in_month = selected_period.days_in_month
                    current_spend = current_spend * days_in_month / elapsed_days

                anomalies = []
                for category, amount in current_spend.items():
                    average = float(averages.get(category, 0) or 0)
                    amount = float(amount or 0)
                    if amount >= 50 and amount > max(average * 1.3, average + 50):
                        anomalies.append((category, amount, average))

                anomalies.sort(key=lambda item: item[1] - item[2], reverse=True)
                for category, amount, average in anomalies[:3]:
                    extra = amount - average
                    insights.append({
                        "level": "info",
                        "title": f"Uitgavenpatroon: {category}",
                        "message": (
                            f"Op basis van de huidige uitgaven ligt het "
                            f"maandtempo ongeveer €{extra:,.0f} boven het "
                            "gemiddelde van de vorige beschikbare maanden. "
                            "Dit is een signaal, geen definitieve overschrijding."
                        ).replace(",", "X").replace(".", ",").replace("X", "."),
                    })

    return insights[:6]


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
