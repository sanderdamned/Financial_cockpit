from typing import Optional

import pandas as pd


class Database:
    """
    Central Supabase data-access layer.

    Streamlit pages should use this class instead of
    directly constructing Supabase queries.
    """

    def __init__(self, client):
        self.client = client

    # ========================================================
    # GENERIC DATABASE METHODS
    # ========================================================

    def select(
        self,
        table,
        filters=None,
        order_by=None,
        descending=False,
    ):
        query = (
            self.client
            .table(table)
            .select("*")
        )

        for column, value in (
            filters or {}
        ).items():

            query = query.eq(
                column,
                value,
            )

        if order_by:

            query = query.order(
                order_by,
                desc=descending,
            )

        return (
            query.execute().data
            or []
        )

    def insert(
        self,
        table,
        records,
    ):

        if not records:
            return []

        return (
            self.client
            .table(table)
            .insert(records)
            .execute()
            .data
            or []
        )

    def upsert(
        self,
        table,
        records,
        on_conflict,
    ):

        if not records:
            return []

        return (
            self.client
            .table(table)
            .upsert(
                records,
                on_conflict=on_conflict,
            )
            .execute()
            .data
            or []
        )

    def update(
        self,
        table,
        values,
        filters,
    ):

        query = (
            self.client
            .table(table)
            .update(values)
        )

        for column, value in filters.items():

            query = query.eq(
                column,
                value,
            )

        return (
            query.execute().data
            or []
        )

    def delete(
        self,
        table,
        filters,
    ):

        query = (
            self.client
            .table(table)
            .delete()
        )

        for column, value in filters.items():

            query = query.eq(
                column,
                value,
            )

        return (
            query.execute().data
            or []
        )

    # ========================================================
    # ACCOUNTS
    # ========================================================

    def load_accounts(
        self,
        user_id,
    ):

        return self.select(
            "accounts",
            {
                "user_id": user_id,
            },
            "name",
        )

    def create_account(
        self,
        user_id,
        name,
        bank,
        account_type,
    ):

        return self.insert(
            "accounts",
            [
                {
                    "user_id": user_id,
                    "name": name,
                    "bank": bank,
                    "account_type": account_type,
                }
            ],
        )

    # ========================================================
    # TRANSACTIONS
    # ========================================================

    def load_transactions(
        self,
        user_id,
        account_id,
    ):

        return self.select(
            "transactions",
            {
                "user_id": user_id,
                "account_id": account_id,
            },
            "date",
            descending=True,
        )

    def load_all_transactions(
        self,
        user_id,
    ):

        return self.select(
            "transactions",
            {
                "user_id": user_id,
            },
            "date",
            descending=True,
        )

    def save_transactions(
        self,
        records,
    ):

        return self.upsert(
            "transactions",
            records,
            "user_id,transaction_hash",
        )

    def update_transactions_for_merchant(
        self,
        user_id,
        merchant,
        category,
    ):

        return self.update(
            "transactions",
            {
                "category": category,
            },
            {
                "user_id": user_id,
                "merchant": merchant,
            },
        )

    # ========================================================
    # BUDGETS
    # ========================================================

    def load_budgets(
        self,
        user_id,
    ):

        return self.select(
            "budgets",
            {
                "user_id": user_id,
            },
            "category",
        )

    def save_budget(
        self,
        user_id,
        category,
        monthly_limit,
    ):

        return self.upsert(
            "budgets",
            [
                {
                    "user_id": user_id,
                    "category": category,
                    "monthly_limit": float(
                        monthly_limit
                    ),
                }
            ],
            "user_id,category",
        )

    # ========================================================
    # MERCHANT CATEGORY RULES
    # ========================================================

    def load_merchant_category_rules(
        self,
        user_id,
    ):

        rows = self.select(
            "merchant_category_rules",
            {
                "user_id": user_id,
            },
            "merchant",
        )

        return {
            row["merchant"]: row["category"]
            for row in rows
        }

    def save_merchant_category_rule(
        self,
        user_id,
        merchant,
        category,
    ):

        return self.upsert(
            "merchant_category_rules",
            [
                {
                    "user_id": user_id,
                    "merchant": merchant,
                    "category": category,
                    "updated_at": pd.Timestamp.utcnow().isoformat(),
                }
            ],
            "user_id,merchant",
        )

    def delete_merchant_category_rule(
        self,
        user_id,
        merchant,
    ):

        return self.delete(
            "merchant_category_rules",
            {
                "user_id": user_id,
                "merchant": merchant,
            },
        )

    # ========================================================
    # RECURRING TRANSACTIONS
    # ========================================================

    def load_recurring_transactions(
        self,
        user_id,
        account_id=None,
    ):

        filters = {
            "user_id": user_id,
        }

        if account_id is not None:
            filters["account_id"] = account_id

        return self.select(
            "recurring_transactions",
            filters,
            "next_occurrence",
        )

    def save_recurring_transactions(
        self,
        records,
    ):

        return self.upsert(
            "recurring_transactions",
            records,
            "user_id,account_id,merchant",
        )

    def update_recurring_active(
        self,
        recurring_id,
        active,
    ):

        return self.update(
            "recurring_transactions",
            {
                "active": bool(active),
            },
            {
                "id": recurring_id,
            },
        )

    def delete_recurring_transaction(
        self,
        recurring_id,
    ):

        return self.delete(
            "recurring_transactions",
            {
                "id": recurring_id,
            },
        )
