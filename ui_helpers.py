import pandas as pd
import streamlit as st

from categorization import EXPENSE_CATEGORIES


# ============================================================
# FORMATTING
# ============================================================

def euro(value):
    """
    Formats a number as Dutch euro currency.
    """

    try:
        value = float(
            value or 0
        )

    except (
        TypeError,
        ValueError,
    ):
        value = 0.0

    return (
        f"€ {value:,.2f}"
        .replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
    )


# ============================================================
# METRICS
# ============================================================

def metric_columns(
    metrics,
    columns=4,
):
    """
    Renders Streamlit metrics.

    metrics:
        [
            ("Label", "Value"),
            ...
        ]
    """

    cols = st.columns(
        columns
    )

    for col, (
        label,
        value,
    ) in zip(
        cols,
        metrics,
    ):
        col.metric(
            label,
            value,
        )

    return cols


# ============================================================
# MONTH SELECTOR
# ============================================================

def month_selectbox(
    df,
    key="period",
):
    """
    Creates a month selector from transaction dates.
    """

    if (
        df is None
        or df.empty
        or "date" not in df.columns
    ):
        return None

    dates = pd.to_datetime(
        df["date"],
        errors="coerce",
    ).dropna()

    periods = sorted(
        dates.dt.to_period("M").unique(),
        reverse=True,
    )

    if not periods:
        return None

    labels = {
        period: period.strftime(
            "%m-%Y"
        )
        for period in periods
    }

    selected = st.selectbox(
        "Maand",
        periods,
        format_func=lambda period: labels[period],
        key=key,
    )

    return selected


# ============================================================
# CATEGORIES
# ============================================================

def category_options():
    return EXPENSE_CATEGORIES.copy()


# ============================================================
# TRANSFER DETECTION
# ============================================================

def is_transfer_series(df):
    """
    Returns a boolean Series identifying transfers.
    """

    if df is None or df.empty:
        return pd.Series(
            dtype=bool
        )

    if "is_transfer" in df.columns:

        return (
            df["is_transfer"]
            .fillna(False)
            .astype(bool)
        )

    if "transaction_type" in df.columns:

        values = (
            df["transaction_type"]
            .astype(str)
            .str.lower()
        )

        return values.isin(
            [
                "transfer",
                "overboeking",
                "overboekingen",
            ]
        )

    return pd.Series(
        False,
        index=df.index,
    )


def without_transfers(df):
    """
    Returns a copy without internal transfers.
    """

    if df is None:
        return pd.DataFrame()

    if df.empty:
        return df.copy()

    transfer_mask = is_transfer_series(
        df
    )

    return df.loc[
        ~transfer_mask
    ].copy()


# ============================================================
# TRANSACTION METRICS
# ============================================================

def render_transaction_metrics(df):
    """
    Displays transaction overview metrics.
    """

    if df is None or df.empty:

        metric_columns(
            [
                (
                    "Transacties",
                    "0",
                ),
                (
                    "Uitgaven",
                    euro(0),
                ),
                (
                    "Inkomsten",
                    euro(0),
                ),
                (
                    "Overboekingen",
                    "0",
                ),
            ]
        )

        return

    transfer_mask = is_transfer_series(
        df
    )

    normal = df.loc[
        ~transfer_mask
    ]

    expenses = normal.loc[
        normal["flow"] == "Uitgave",
        "amount",
    ].abs().sum()

    income = normal.loc[
        normal["flow"] == "Inkomst",
        "amount",
    ].abs().sum()

    metric_columns(
        [
            (
                "Transacties",
                f"{len(df):,}".replace(
                    ",",
                    ".",
                ),
            ),
            (
                "Uitgaven",
                euro(expenses),
            ),
            (
                "Inkomsten",
                euro(income),
            ),
            (
                "Overboekingen",
                f"{int(transfer_mask.sum()):,}".replace(
                    ",",
                    ".",
                ),
            ),
        ]
    )
