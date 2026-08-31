import pandas as pd


# ============================================================
# TRANSACTION PREPARATION
# ============================================================

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
            errors="coerce",
        )

    if "amount" in df.columns:
        df["amount"] = pd.to_numeric(
            df["amount"],
            errors="coerce",
        )

    df = df[
        df["date"].notna()
        & df["amount"].notna()
    ].copy()

    return df


# ============================================================
# MONTHLY METRICS
# ============================================================

def calculate_monthly_metrics(
    df,
    period=None,
):
    """
    Bereken inkomsten, uitgaven en netto resultaat
    voor een bepaalde maand.
    """

    if df.empty:
        return {
            "income": 0.0,
            "expenses": 0.0,
            "net": 0.0,
        }

    period_df = df.copy()

    if period is not None:
        period_df = period_df[
            period_df["date"].dt.to_period("M") == period
        ]

    income = period_df.loc[
        period_df["flow"] == "Inkomst",
        "amount",
    ].sum()

    expenses = period_df.loc[
        period_df["flow"] == "Uitgave",
        "amount",
    ].abs().sum()

    return {
        "income": float(income),
        "expenses": float(expenses),
        "net": float(income - expenses),
    }


# ============================================================
# CATEGORY SPENDING
# ============================================================

def calculate_category_spending(
    df,
    period=None,
):
    """
    Geeft totale uitgaven per categorie terug.
    """

    if df.empty:
        return {}

    period_df = df.copy()

    if period is not None:
        period_df = period_df[
            period_df["date"].dt.to_period("M") == period
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


# ============================================================
# BUDGET STATUS
# ============================================================

def calculate_budget_status(
    df,
    budgets,
    period,
):
    """
    Vergelijk werkelijke uitgaven met budgetten.
    """

    spending = calculate_category_spending(
        df,
        period,
    )

    results = []

    for budget in budgets:

        category = budget.get(
            "category",
            "Overig",
        )

        limit = float(
            budget.get(
                "monthly_limit",
                0,
            ) or 0
        )

        spent = float(
            spending.get(
                category,
                0,
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
                "over_budget": spent > limit,
            }
        )

    return results


# ============================================================
# RECURRING COSTS
# ============================================================

def calculate_monthly_recurring_cost(
    recurring_transactions,
):
    """
    Zet actieve recurring payments om naar
    een geschatte maandelijkse kostenpost.
    """

    monthly_cost = 0.0

    for item in recurring_transactions:

        if not item.get(
            "active",
            True,
        ):
            continue

        amount = float(
            item.get(
                "expected_amount",
                0,
            ) or 0
        )

        frequency = item.get(
            "frequency",
            "",
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
# RECURRING PAYMENTS REMAINING
# ============================================================

def calculate_recurring_remaining(
    recurring_transactions,
    period,
):
    """
    Bereken hoeveel actieve recurring payments
    nog verwacht worden binnen de geselecteerde maand.
    """

    if not recurring_transactions:
        return 0.0

    month_start = period.start_time
    month_end = period.end_time

    total = 0.0

    for item in recurring_transactions:

        if not item.get(
            "active",
            True,
        ):
            continue

        next_occurrence = item.get(
            "next_occurrence"
        )

        if not next_occurrence:
            continue

        next_date = pd.to_datetime(
            next_occurrence,
            errors="coerce",
        )

        if pd.isna(next_date):
            continue

        frequency = item.get(
            "frequency",
            "",
        )

        amount = float(
            item.get(
                "expected_amount",
                0,
            ) or 0
        )

        # Start bij de eerstvolgende betaling
        occurrence = next_date

        # We willen alleen betalingen binnen
        # de geselecteerde maand tellen.
        while occurrence < month_start:

            if frequency == "Wekelijks":
                occurrence += pd.Timedelta(days=7)

            elif frequency == "Maandelijks":
                occurrence += pd.DateOffset(months=1)

            elif frequency == "Per kwartaal":
                occurrence += pd.DateOffset(months=3)

            elif frequency == "Jaarlijks":
                occurrence += pd.DateOffset(years=1)

            else:
                break

        if (
            month_start
            <= occurrence
            <= month_end
        ):
            total += amount

    return float(total)


# ============================================================
# MONTH FORECAST
# ============================================================

def calculate_month_forecast(
    df,
    period,
    recurring_transactions=None,
    budgets=None,
):
    """
    Voorspel het financiële resultaat van de maand.

    De forecast gebruikt:

    1. Werkelijke inkomsten tot nu toe
    2. Werkelijke uitgaven tot nu toe
    3. Verwachte resterende recurring payments
    4. Verwachte inkomsten op basis van historische data
    5. Budgetten als bovengrens voor overige uitgaven
    """

    if df.empty:
        return {
            "projected_income": 0.0,
            "projected_expenses": 0.0,
            "projected_net": 0.0,
            "actual_income": 0.0,
            "actual_expenses": 0.0,
            "remaining_days": 0,
            "recurring_remaining": 0.0,
        }

    period_df = df[
        df["date"].dt.to_period("M") == period
    ].copy()

    actual_income = period_df.loc[
        period_df["flow"] == "Inkomst",
        "amount",
    ].sum()

    actual_expenses = period_df.loc[
        period_df["flow"] == "Uitgave",
        "amount",
    ].abs().sum()

    today = pd.Timestamp.today().normalize()

    month_start = period.start_time.normalize()
    month_end = period.end_time.normalize()

    # Als we naar een historische maand kijken,
    # is er geen extrapolatie nodig.
    if period < today.to_period("M"):

        projected_income = float(actual_income)
        projected_expenses = float(actual_expenses)

        recurring_remaining = 0.0

    else:

        effective_today = min(
            max(today, month_start),
            month_end,
        )

        remaining_days = (
            month_end - effective_today
        ).days

        days_elapsed = (
            effective_today - month_start
        ).days + 1

        days_in_month = (
            month_end - month_start
        ).days + 1

        # ----------------------------------------------------
        # INCOME FORECAST
        # ----------------------------------------------------

        projected_income = float(
            actual_income
        )

        # Als er al inkomsten zijn geregistreerd,
        # extrapoleren we voorzichtig.
        if actual_income > 0:

            income_rate = (
                actual_income
                / days_elapsed
            )

            projected_income += (
                income_rate
                * remaining_days
            )

        # ----------------------------------------------------
        # EXPENSE FORECAST
        # ----------------------------------------------------

        projected_expenses = float(
            actual_expenses
        )

        if actual_expenses > 0:

            expense_rate = (
                actual_expenses
                / days_elapsed
            )

            projected_expenses += (
                expense_rate
                * remaining_days
            )

        # ----------------------------------------------------
        # RECURRING PAYMENTS
        # ----------------------------------------------------

        recurring_remaining = (
            calculate_recurring_remaining(
                recurring_transactions or [],
                period,
            )
        )

        # Voeg recurring payments toe die
        # nog niet in de transacties zitten.
        projected_expenses += (
            recurring_remaining
        )

        # Voorkom dat recurring payments dubbel
        # worden meegenomen als ze al onderdeel
        # zijn van de historische run-rate.
        projected_expenses = max(
            projected_expenses,
            actual_expenses + recurring_remaining,
        )

    projected_net = (
        projected_income
        - projected_expenses
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
        "remaining_days": (
            max(
                0,
                (
                    month_end
                    - today
                ).days,
            )
            if period == today.to_period("M")
            else 0
        ),
        "recurring_remaining": float(
            recurring_remaining
        ),
    }


# ============================================================
# FINANCIAL HEALTH
# ============================================================

def calculate_financial_health(
    forecast,
    budget_status,
):
    """
    Geeft een eenvoudige Financial Health score van 0-100.
    """

    score = 100
    warnings = []

    projected_net = forecast.get(
        "projected_net",
        0,
    )

    projected_income = forecast.get(
        "projected_income",
        0,
    )

    projected_expenses = forecast.get(
        "projected_expenses",
        0,
    )

    # --------------------------------------------------------
    # NEGATIVE CASHFLOW
    # --------------------------------------------------------

    if projected_net < 0:

        score -= 40

        warnings.append(
            "🔴 Je verwachte uitgaven liggen "
            "hoger dan je verwachte inkomsten."
        )

    elif projected_income > 0:

        savings_rate = (
            projected_net
            / projected_income
            * 100
        )

        if savings_rate < 10:

            score -= 20

            warnings.append(
                "🟠 Je verwachte spaarpercentage "
                "is lager dan 10%."
            )

        elif savings_rate < 20:

            score -= 10

    # --------------------------------------------------------
    # BUDGETS
    # --------------------------------------------------------

    over_budget_count = 0

    for budget in budget_status:

        percentage = budget.get(
            "percentage",
            0,
        )

        if budget.get(
            "over_budget",
            False,
        ):

            over_budget_count += 1

            warnings.append(
                f"🔴 {budget['category']} "
                f"zit {abs(budget['remaining']):.2f} "
                "boven het budget."
            )

        elif percentage >= 80:

            warnings.append(
                f"🟠 {budget['category']} "
                f"heeft al {percentage:.0f}% "
                "van het budget gebruikt."
            )

    score -= min(
        over_budget_count * 10,
        30,
    )

    score = max(
        0,
        min(
            100,
            round(score),
        ),
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
# SAFE TO SPEND
# ============================================================

def calculate_safe_to_spend(
    forecast,
    buffer=0,
):
    """
    Bereken hoeveel extra geld uitgegeven kan worden
    zonder dat de geprojecteerde maandcashflow negatief wordt.
    """

    projected_net = float(
        forecast.get(
            "projected_net",
            0,
        ) or 0
    )

    buffer = float(
        buffer or 0
    )

    safe_amount = (
        projected_net
        - buffer
    )

    return max(
        0.0,
        safe_amount,
    )
