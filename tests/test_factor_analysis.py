"""
Tests for Factor Analysis module
"""
import unittest
from datetime import date, timedelta
from decimal import Decimal
from typing import List

from alm_calculator.core.base_instrument import BaseInstrument, InstrumentType
from alm_calculator.risks.factor_analysis import FactorAnalyzer


class MockInstrument(BaseInstrument):
    """Mock instrument for testing"""

    def calculate_risk_contribution(self, calculation_date, risk_params, assumptions=None):
        """Mock implementation"""
        pass

    def apply_assumptions(self, assumptions):
        """Mock implementation"""
        return self


class TestFactorAnalyzer(unittest.TestCase):
    """Tests for FactorAnalyzer class"""

    def setUp(self):
        """Set up test fixtures"""
        self.base_date = date(2024, 12, 31)
        self.comparison_date = date(2025, 1, 7)

        # Create base portfolio (3 instruments)
        self.base_instruments = [
            MockInstrument(
                instrument_id="LOAN_001",
                instrument_type=InstrumentType.LOAN,
                balance_account="40101",
                amount=Decimal("1000000"),
                currency="RUB",
                start_date=date(2024, 1, 1),
                as_of_date=self.base_date,
                maturity_date=date(2025, 12, 31),
                interest_rate=0.15
            ),
            MockInstrument(
                instrument_id="LOAN_002",
                instrument_type=InstrumentType.LOAN,
                balance_account="40101",
                amount=Decimal("500000"),
                currency="RUB",
                start_date=date(2024, 1, 1),
                as_of_date=self.base_date,
                maturity_date=date(2025, 6, 30),
                interest_rate=0.12
            ),
            MockInstrument(
                instrument_id="DEPO_001",
                instrument_type=InstrumentType.DEPOSIT,
                balance_account="42301",
                amount=Decimal("-800000"),
                currency="RUB",
                start_date=date(2024, 1, 1),
                as_of_date=self.base_date,
                maturity_date=date(2025, 3, 31),
                interest_rate=0.10
            )
        ]

        # Create comparison portfolio (existing + new)
        self.comparison_instruments = []

        # Add aged existing instruments
        for inst in self.base_instruments:
            aged = MockInstrument(
                instrument_id=inst.instrument_id,
                instrument_type=inst.instrument_type,
                balance_account=inst.balance_account,
                amount=inst.amount,
                currency=inst.currency,
                start_date=inst.start_date,
                as_of_date=self.comparison_date,  # Updated
                maturity_date=inst.maturity_date,
                interest_rate=inst.interest_rate
            )
            self.comparison_instruments.append(aged)

        # Add new instrument
        new_instrument = MockInstrument(
            instrument_id="LOAN_003",
            instrument_type=InstrumentType.LOAN,
            balance_account="40101",
            amount=Decimal("300000"),
            currency="RUB",
            start_date=date(2025, 1, 1),
            as_of_date=self.comparison_date,
            maturity_date=date(2026, 1, 1),
            interest_rate=0.14
        )
        self.comparison_instruments.append(new_instrument)

    def test_initialization(self):
        """Test FactorAnalyzer initialization"""
        analyzer = FactorAnalyzer(self.base_date, self.comparison_date)

        self.assertEqual(analyzer.base_date, self.base_date)
        self.assertEqual(analyzer.comparison_date, self.comparison_date)
        self.assertEqual(analyzer.days_elapsed, 7)

    def test_initialization_invalid_dates(self):
        """Test that initialization fails with invalid dates"""
        with self.assertRaises(ValueError):
            FactorAnalyzer(self.comparison_date, self.base_date)

    def test_simple_metric_calculation(self):
        """Test factor analysis with simple metric (sum of amounts)"""

        def calculate_sum_of_amounts(instruments: List[BaseInstrument], calc_date: date) -> Decimal:
            """Simple metric: sum of all amounts"""
            return sum(inst.amount for inst in instruments)

        analyzer = FactorAnalyzer(self.base_date, self.comparison_date)

        result = analyzer.analyze(
            self.base_instruments,
            self.comparison_instruments,
            calculate_sum_of_amounts,
            metric_name="Sum of Amounts"
        )

        # Check structure
        self.assertIn('metric_base', result)
        self.assertIn('metric_aged', result)
        self.assertIn('metric_full', result)
        self.assertIn('total_change', result)
        self.assertIn('aging_effect', result)
        self.assertIn('new_deals_effect', result)

        # Check values
        # Base: 1000000 + 500000 - 800000 = 700000
        self.assertEqual(result['metric_base'], Decimal("700000"))

        # Aged (same instruments): 700000
        self.assertEqual(result['metric_aged'], Decimal("700000"))

        # Full (aged + new 300000): 1000000
        self.assertEqual(result['metric_full'], Decimal("1000000"))

        # Changes
        self.assertEqual(result['total_change'], Decimal("300000"))
        self.assertEqual(result['aging_effect'], Decimal("0"))
        self.assertEqual(result['new_deals_effect'], Decimal("300000"))

        # Products
        self.assertEqual(result['existing_products_count'], 3)
        self.assertEqual(result['new_products_count'], 1)
        self.assertIn('LOAN_003', result['new_products'])

    def test_individual_impact_analysis(self):
        """Test individual impact analysis"""

        def calculate_asset_count(instruments: List[BaseInstrument], calc_date: date) -> int:
            """Count assets"""
            return sum(1 for inst in instruments if inst.amount > 0)

        analyzer = FactorAnalyzer(self.base_date, self.comparison_date)

        result = analyzer.analyze_individual_impact(
            self.base_instruments,
            self.comparison_instruments,
            calculate_asset_count,
            metric_name="Asset Count",
            top_n=10
        )

        # Check breakdown exists
        self.assertIn('new_products_breakdown', result)
        self.assertIsNotNone(result['new_products_breakdown'])

        # Check breakdown structure
        breakdown = result['new_products_breakdown']
        self.assertEqual(len(breakdown), 1)  # Only 1 new product

        product = breakdown[0]
        self.assertEqual(product['product_id'], 'LOAN_003')
        self.assertEqual(product['product_type'], 'loan')
        self.assertEqual(product['amount'], 300000.0)
        self.assertEqual(product['impact'], 1)  # Added 1 asset

    def test_aging_instruments(self):
        """Test that instruments are properly aged"""
        analyzer = FactorAnalyzer(self.base_date, self.comparison_date)

        existing_ids = {'LOAN_001', 'LOAN_002', 'DEPO_001'}
        aged_instruments = analyzer._age_instruments(
            self.base_instruments,
            existing_ids,
            analyzer.days_elapsed
        )

        # Check count
        self.assertEqual(len(aged_instruments), 3)

        # Check as_of_date updated
        for inst in aged_instruments:
            self.assertEqual(inst.as_of_date, self.comparison_date)

        # Check maturity_date unchanged
        original_maturities = {inst.instrument_id: inst.maturity_date for inst in self.base_instruments}
        for inst in aged_instruments:
            self.assertEqual(inst.maturity_date, original_maturities[inst.instrument_id])

    def test_calculate_delta_numeric(self):
        """Test delta calculation for numeric values"""
        analyzer = FactorAnalyzer(self.base_date, self.comparison_date)

        # Test integers
        delta = analyzer._calculate_delta(100, 70)
        self.assertEqual(delta, 30)

        # Test Decimals
        delta = analyzer._calculate_delta(Decimal("100.5"), Decimal("50.3"))
        self.assertEqual(delta, Decimal("50.2"))

    def test_calculate_delta_dict(self):
        """Test delta calculation for dictionaries"""
        analyzer = FactorAnalyzer(self.base_date, self.comparison_date)

        old = {'RUB': 100, 'USD': 50}
        new = {'RUB': 150, 'USD': 45, 'EUR': 20}

        delta = analyzer._calculate_delta(new, old)

        self.assertEqual(delta['RUB'], 50)
        self.assertEqual(delta['USD'], -5)
        self.assertEqual(delta['EUR'], 20)

    def test_format_metric(self):
        """Test metric formatting"""
        analyzer = FactorAnalyzer(self.base_date, self.comparison_date)

        # Test numeric
        formatted = analyzer._format_metric(1234567.89)
        self.assertIn('1,234,567.89', formatted)

        # Test dict
        formatted = analyzer._format_metric({'RUB': 100, 'USD': 50})
        self.assertIn('RUB', formatted)
        self.assertIn('100', formatted)

        # Test None
        formatted = analyzer._format_metric(None)
        self.assertEqual(formatted, 'N/A')

    def test_get_impact_magnitude(self):
        """Test impact magnitude extraction"""
        analyzer = FactorAnalyzer(self.base_date, self.comparison_date)

        # Test numeric
        mag = analyzer._get_impact_magnitude(100)
        self.assertEqual(mag, 100.0)

        mag = analyzer._get_impact_magnitude(-50)
        self.assertEqual(mag, 50.0)

        # Test dict
        mag = analyzer._get_impact_magnitude({'RUB': 100, 'USD': -50})
        self.assertEqual(mag, 150.0)


if __name__ == '__main__':
    unittest.main()
