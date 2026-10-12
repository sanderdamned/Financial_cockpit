import unittest

from categorization import categorize_transaction


class SmallExpenseCategorizationTests(unittest.TestCase):
    def test_unrecognized_expense_below_15_is_small_expense(self):
        self.assertEqual(
            categorize_transaction(
                description="UNKNOWN LOCAL PURCHASE",
                merchant="UNKNOWN LOCAL PURCHASE",
                flow="Uitgave",
                amount=-14.99,
            ),
            "Kleine uitgaven",
        )

    def test_expense_of_exactly_15_is_not_small_expense(self):
        self.assertEqual(
            categorize_transaction(
                description="UNKNOWN LOCAL PURCHASE",
                merchant="UNKNOWN LOCAL PURCHASE",
                flow="Uitgave",
                amount=-15.00,
            ),
            "Overig",
        )

    def test_known_category_has_priority_even_below_15(self):
        self.assertEqual(
            categorize_transaction(
                description="Albert Heijn",
                merchant="Albert Heijn",
                flow="Uitgave",
                amount=-4.50,
            ),
            "Boodschappen",
        )

    def test_saved_merchant_rule_has_priority_even_below_15(self):
        self.assertEqual(
            categorize_transaction(
                description="My regular merchant",
                merchant="My regular merchant",
                merchant_rules={"My regular merchant": "Horeca"},
                flow="Uitgave",
                amount=-6.00,
            ),
            "Horeca",
        )

    def test_income_is_never_categorized_as_small_expense(self):
        self.assertNotEqual(
            categorize_transaction(
                description="Unknown incoming payment",
                merchant="Unknown incoming payment",
                flow="Inkomst",
                amount=5.00,
            ),
            "Kleine uitgaven",
        )


if __name__ == "__main__":
    unittest.main()
