import unittest
from datetime import date

import pandas as pd

from financial_engine import (
    calculate_forecast_data_quality,
    calculate_historical_monthly_average,
    calculate_variable_expense_average,
    calculate_monthly_recurring_cost,
    calculate_recurring_remaining,
    calculate_recurring_income_remaining,
    generate_financial_insights,
)


def sample_monthly_transactions():
    current_month = pd.Timestamp.today().to_period("M")
    rows = []
    for offset, expense in [(3, 100.0), (2, 200.0), (1, 300.0)]:
        month = current_month - offset
        rows.append({
            "date": month.start_time + pd.Timedelta(days=9),
            "flow": "Inkomst",
            "amount": 1000.0,
            "category": "Salaris",
            "description": "Salaris",
            "merchant": "Werkgever",
        })
        rows.append({
            "date": month.start_time + pd.Timedelta(days=9),
            "flow": "Uitgave",
            "amount": -expense,
            "category": "Boodschappen",
            "description": "Boodschappen",
            "merchant": "Supermarkt",
        })

    # Deliberately large partial-month values: they must not contaminate
    # a baseline built from fully completed months.
    rows.extend([
        {
            "date": pd.Timestamp.today().normalize(),
            "flow": "Inkomst",
            "amount": 99999.0,
            "category": "Salaris",
            "description": "Test current month",
            "merchant": "Test",
        },
        {
            "date": pd.Timestamp.today().normalize(),
            "flow": "Uitgave",
            "amount": -99999.0,
            "category": "Boodschappen",
            "description": "Test current month",
            "merchant": "Test",
        },
    ])
    return pd.DataFrame(rows)


class ForecastBaselineTests(unittest.TestCase):
    def test_historical_average_excludes_incomplete_current_month(self):
        df = sample_monthly_transactions()
        result = calculate_historical_monthly_average(df, months=3)
        self.assertAlmostEqual(result["income"], 1000.0)
        self.assertAlmostEqual(result["expenses"], 200.0)

    def test_variable_expense_average_excludes_incomplete_current_month(self):
        df = sample_monthly_transactions()
        result = calculate_variable_expense_average(df, [], months=3)
        self.assertAlmostEqual(result, 200.0)

    def test_forecast_quality_counts_completed_months(self):
        df = sample_monthly_transactions()
        result = calculate_forecast_data_quality(
            df, pd.Timestamp.today().to_period("M")
        )
        self.assertEqual(result["months_available"], 3)
        self.assertEqual(result["confidence"], "Beperkt" if result["months_available"] < 4 else "Redelijk")

    def test_savings_transfers_are_not_recurring_income_or_expenses(self):
        next_month = (pd.Timestamp.today().to_period("M") + 1)
        occurrence = (next_month.start_time + pd.Timedelta(days=4)).date().isoformat()
        recurring = [
            {
                "active": True,
                "flow": "Uitgave",
                "category": "Overboeking spaargeld",
                "expected_amount": 250.0,
                "frequency": "Maandelijks",
                "next_occurrence": occurrence,
                "reliability": "Hoog",
            },
            {
                "active": True,
                "flow": "Uitgave",
                "category": "Wonen",
                "expected_amount": 900.0,
                "frequency": "Maandelijks",
                "next_occurrence": occurrence,
                "reliability": "Hoog",
            },
            {
                "active": True,
                "flow": "Inkomst",
                "category": "Overboeking spaargeld",
                "expected_amount": 250.0,
                "frequency": "Maandelijks",
                "next_occurrence": occurrence,
                "reliability": "Hoog",
            },
        ]

        self.assertAlmostEqual(calculate_monthly_recurring_cost(recurring), 900.0)
        self.assertAlmostEqual(
            calculate_recurring_remaining(recurring, next_month),
            900.0,
        )
        self.assertAlmostEqual(
            calculate_recurring_income_remaining(recurring, next_month),
            0.0,
        )

    def test_insights_flag_negative_forecast_and_budget_overrun(self):
        insights = generate_financial_insights(
            pd.DataFrame(),
            pd.Timestamp.today().to_period("M"),
            {
                "projected_income": 1000,
                "projected_expenses": 1200,
                "projected_net": -200,
            },
            [{
                "category": "Boodschappen",
                "percentage": 120,
                "remaining": -40,
                "over_budget": True,
            }],
        )
        titles = [item["title"] for item in insights]
        self.assertIn("Verwacht maandtekort", titles)
        self.assertIn("Budget overschreden: Boodschappen", titles)


if __name__ == "__main__":
    unittest.main()
