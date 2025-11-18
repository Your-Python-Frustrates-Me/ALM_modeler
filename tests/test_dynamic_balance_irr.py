"""
Integration Tests for Dynamic Balance IRR Calculator
Интеграционные тесты для калькулятора процентного риска на динамическом балансе
"""
import pytest
from datetime import date
from decimal import Decimal

from alm_calculator.models.instruments.deposit import Deposit
from alm_calculator.models.instruments.loan import Loan
from alm_calculator.risks.interest_rate.dynamic_balance_irr_calculator import (
    DynamicBalanceIRRCalculator
)
from alm_calculator.config.elasticity_config_example import (
    create_baseline_elasticity_config
)


@pytest.fixture
def calculation_date():
    """Фикстура с датой расчета"""
    return date(2025, 1, 1)


@pytest.fixture
def repricing_buckets():
    """Фикстура с временными бакетами"""
    return ['0-1m', '1-3m', '3-6m', '6-12m', '1-2y', '2-3y', '3-5y', '5-7y', '7-10y', '10y+']


@pytest.fixture
def sample_instruments():
    """Фикстура с набором инструментов"""
    instruments = []

    # Депозиты ФЛ
    instruments.append(Deposit(
        instrument_id="DEP_001",
        amount=Decimal("10000000"),
        currency="RUB",
        interest_rate=0.08,
        start_date=date(2024, 1, 1),
        maturity_date=date(2026, 1, 1),
        is_demand_deposit=True,
        counterparty_type="retail",
        counterparty_name="Розница"
    ))

    instruments.append(Deposit(
        instrument_id="DEP_002",
        amount=Decimal("5000000"),
        currency="RUB",
        interest_rate=0.10,
        start_date=date(2024, 10, 1),
        maturity_date=date(2025, 4, 1),
        is_demand_deposit=False,
        counterparty_type="retail",
        counterparty_name="Розница"
    ))

    # Депозиты ЮЛ
    instruments.append(Deposit(
        instrument_id="DEP_003",
        amount=Decimal("20000000"),
        currency="RUB",
        interest_rate=0.09,
        start_date=date(2024, 11, 1),
        maturity_date=date(2025, 2, 1),
        is_demand_deposit=False,
        counterparty_type="corporate",
        counterparty_name="ООО Компания"
    ))

    # Кредиты
    instruments.append(Loan(
        instrument_id="LOAN_001",
        amount=Decimal("30000000"),
        currency="RUB",
        interest_rate=0.12,
        start_date=date(2024, 1, 1),
        maturity_date=date(2027, 1, 1),
        counterparty_type="retail",
        loan_type="mortgage"
    ))

    instruments.append(Loan(
        instrument_id="LOAN_002",
        amount=Decimal("15000000"),
        currency="RUB",
        interest_rate=0.11,
        start_date=date(2024, 6, 1),
        maturity_date=date(2026, 6, 1),
        counterparty_type="corporate",
        loan_type="corporate_loan"
    ))

    return instruments


class TestDynamicBalanceIRRCalculator:
    """Тесты для DynamicBalanceIRRCalculator"""

    def test_init(self, calculation_date, repricing_buckets):
        """Тест инициализации калькулятора"""
        calculator = DynamicBalanceIRRCalculator(
            calculation_date=calculation_date,
            repricing_buckets=repricing_buckets
        )

        assert calculator.calculation_date == calculation_date
        assert calculator.repricing_buckets == repricing_buckets
        assert calculator.elasticity_calculator is not None
        assert calculator.gap_calculator is not None

    def test_calculate_dynamic_irr_basic(
        self,
        calculation_date,
        repricing_buckets,
        sample_instruments
    ):
        """Базовый тест расчета динамического процентного риска"""
        calculator = DynamicBalanceIRRCalculator(
            calculation_date=calculation_date,
            repricing_buckets=repricing_buckets
        )

        rate_shocks = {'RUB': 200.0}  # +200 б.п.
        risk_params = {'liquidity_buckets': ['0-30d', '30-90d', '90-180d', '180-365d', '1-2y', '2y+']}

        result = calculator.calculate_dynamic_irr(
            sample_instruments,
            rate_shocks,
            risk_params
        )

        # Проверяем структуру результата
        assert 'static' in result
        assert 'dynamic' in result
        assert 'comparison' in result

        # Статический баланс
        assert 'gaps' in result['static']
        assert 'sensitivity' in result['static']
        assert 'RUB' in result['static']['gaps']

        # Динамический баланс
        assert 'gaps' in result['dynamic']
        assert 'sensitivity' in result['dynamic']
        assert 'volume_changes' in result['dynamic']
        assert 'elasticity_summary' in result['dynamic']

        # Должны быть изменения объемов депозитов
        assert len(result['dynamic']['volume_changes']) > 0

        # Сравнение
        assert 'gap_differences' in result['comparison']
        assert 'nii_impact_difference' in result['comparison']

    def test_static_vs_dynamic_gaps_different(
        self,
        calculation_date,
        repricing_buckets,
        sample_instruments
    ):
        """Тест: гэпы статического и динамического баланса должны различаться"""
        calculator = DynamicBalanceIRRCalculator(
            calculation_date=calculation_date,
            repricing_buckets=repricing_buckets
        )

        rate_shocks = {'RUB': 200.0}
        risk_params = {'liquidity_buckets': ['0-30d', '30-90d', '90-180d', '180-365d', '1-2y', '2y+']}

        result = calculator.calculate_dynamic_irr(
            sample_instruments,
            rate_shocks,
            risk_params
        )

        # Получаем гэпы для RUB
        static_gaps = result['static']['gaps']['RUB']
        dynamic_gaps = result['dynamic']['gaps']['RUB']

        # Гэпы должны различаться (из-за изменения объемов депозитов)
        # Проверяем хотя бы один бакет
        gap_differences = (static_gaps['gap'] - dynamic_gaps['gap']).abs()
        assert gap_differences.sum() > 0  # Есть различия

    def test_nii_impact_changes_with_elasticity(
        self,
        calculation_date,
        repricing_buckets,
        sample_instruments
    ):
        """Тест: NII impact должен меняться с учетом эластичности"""
        calculator = DynamicBalanceIRRCalculator(
            calculation_date=calculation_date,
            repricing_buckets=repricing_buckets
        )

        rate_shocks = {'RUB': 200.0}
        risk_params = {'liquidity_buckets': ['0-30d', '30-90d', '90-180d', '180-365d', '1-2y', '2y+']}

        result = calculator.calculate_dynamic_irr(
            sample_instruments,
            rate_shocks,
            risk_params
        )

        static_nii = result['static']['sensitivity']['RUB']['nii_impact_1y']
        dynamic_nii = result['dynamic']['sensitivity']['RUB']['nii_impact_1y']

        # NII impact должен измениться
        assert static_nii != dynamic_nii

        # Должна быть разница
        nii_diff = result['comparison']['nii_impact_difference']['RUB']
        assert nii_diff != Decimal(0)

    def test_multiple_scenarios(
        self,
        calculation_date,
        repricing_buckets,
        sample_instruments
    ):
        """Тест расчета для нескольких сценариев"""
        calculator = DynamicBalanceIRRCalculator(
            calculation_date=calculation_date,
            repricing_buckets=repricing_buckets
        )

        scenarios = {
            'mild_shock': {'RUB': 100.0},
            'moderate_shock': {'RUB': 200.0},
            'severe_shock': {'RUB': 300.0}
        }

        risk_params = {'liquidity_buckets': ['0-30d', '30-90d', '90-180d', '180-365d', '1-2y', '2y+']}

        results = calculator.calculate_multiple_scenarios(
            sample_instruments,
            scenarios,
            risk_params
        )

        assert len(results) == 3
        assert 'mild_shock' in results
        assert 'moderate_shock' in results
        assert 'severe_shock' in results

        # Проверяем, что изменения объемов растут с размером шока
        mild_changes = sum(
            abs(vc.volume_change)
            for vc in results['mild_shock']['dynamic']['volume_changes']
        )
        severe_changes = sum(
            abs(vc.volume_change)
            for vc in results['severe_shock']['dynamic']['volume_changes']
        )

        # При большем шоке должно быть больше изменений
        # (с учетом ограничений max_volume_change)
        assert severe_changes >= mild_changes

    def test_volume_changes_by_segment(
        self,
        calculation_date,
        repricing_buckets,
        sample_instruments
    ):
        """Тест: корпоративные депозиты должны реагировать сильнее"""
        calculator = DynamicBalanceIRRCalculator(
            calculation_date=calculation_date,
            repricing_buckets=repricing_buckets
        )

        rate_shocks = {'RUB': 150.0}
        risk_params = {'liquidity_buckets': ['0-30d', '30-90d', '90-180d', '180-365d', '1-2y', '2y+']}

        result = calculator.calculate_dynamic_irr(
            sample_instruments,
            rate_shocks,
            risk_params
        )

        volume_changes = result['dynamic']['volume_changes']

        # Находим изменения по сегментам
        from alm_calculator.risks.interest_rate.deposit_elasticity import CustomerSegment

        retail_changes = [
            vc for vc in volume_changes
            if vc.customer_segment == CustomerSegment.RETAIL
        ]

        corporate_changes = [
            vc for vc in volume_changes
            if vc.customer_segment == CustomerSegment.CORPORATE
        ]

        if retail_changes and corporate_changes:
            # Средний процент изменения
            retail_avg_pct = sum(abs(vc.volume_change_pct) for vc in retail_changes) / len(retail_changes)
            corporate_avg_pct = sum(abs(vc.volume_change_pct) for vc in corporate_changes) / len(corporate_changes)

            # Корпоративные должны реагировать сильнее
            assert corporate_avg_pct >= retail_avg_pct

    def test_elasticity_summary_not_empty(
        self,
        calculation_date,
        repricing_buckets,
        sample_instruments
    ):
        """Тест: сводка по эластичности должна содержать данные"""
        calculator = DynamicBalanceIRRCalculator(
            calculation_date=calculation_date,
            repricing_buckets=repricing_buckets
        )

        rate_shocks = {'RUB': 200.0}
        risk_params = {'liquidity_buckets': ['0-30d', '30-90d', '90-180d', '180-365d', '1-2y', '2y+']}

        result = calculator.calculate_dynamic_irr(
            sample_instruments,
            rate_shocks,
            risk_params
        )

        elasticity_summary = result['dynamic']['elasticity_summary']

        assert not elasticity_summary.empty
        assert 'customer_segment' in elasticity_summary.columns
        assert 'deposit_type' in elasticity_summary.columns
        assert 'volume_change' in elasticity_summary.columns

    def test_no_rate_shock_no_changes(
        self,
        calculation_date,
        repricing_buckets,
        sample_instruments
    ):
        """Тест: без шока ставок не должно быть изменений"""
        calculator = DynamicBalanceIRRCalculator(
            calculation_date=calculation_date,
            repricing_buckets=repricing_buckets
        )

        rate_shocks = {'RUB': 0.0}  # Нет шока
        risk_params = {'liquidity_buckets': ['0-30d', '30-90d', '90-180d', '180-365d', '1-2y', '2y+']}

        result = calculator.calculate_dynamic_irr(
            sample_instruments,
            rate_shocks,
            risk_params
        )

        # Не должно быть изменений объемов
        assert len(result['dynamic']['volume_changes']) == 0

        # Статический и динамический баланс должны совпадать
        static_gaps = result['static']['gaps']['RUB']
        dynamic_gaps = result['dynamic']['gaps']['RUB']

        # Проверяем, что гэпы одинаковые
        assert (static_gaps['gap'] == dynamic_gaps['gap']).all()

    def test_different_currencies(self, calculation_date, repricing_buckets):
        """Тест расчета для разных валют"""
        # Создаем инструменты в разных валютах
        instruments = [
            Deposit(
                instrument_id="DEP_RUB",
                amount=Decimal("10000000"),
                currency="RUB",
                interest_rate=0.08,
                start_date=date(2024, 1, 1),
                maturity_date=date(2026, 1, 1),
                is_demand_deposit=True,
                counterparty_type="retail"
            ),
            Deposit(
                instrument_id="DEP_USD",
                amount=Decimal("100000"),
                currency="USD",
                interest_rate=0.03,
                start_date=date(2024, 1, 1),
                maturity_date=date(2026, 1, 1),
                is_demand_deposit=True,
                counterparty_type="retail"
            ),
            Loan(
                instrument_id="LOAN_RUB",
                amount=Decimal("20000000"),
                currency="RUB",
                interest_rate=0.12,
                start_date=date(2024, 1, 1),
                maturity_date=date(2027, 1, 1),
                counterparty_type="retail",
                loan_type="mortgage"
            )
        ]

        calculator = DynamicBalanceIRRCalculator(
            calculation_date=calculation_date,
            repricing_buckets=repricing_buckets,
            target_currencies=['RUB', 'USD']
        )

        rate_shocks = {
            'RUB': 200.0,
            'USD': 100.0
        }
        risk_params = {'liquidity_buckets': ['0-30d', '30-90d', '90-180d', '180-365d', '1-2y', '2y+']}

        result = calculator.calculate_dynamic_irr(
            instruments,
            rate_shocks,
            risk_params
        )

        # Должны быть результаты для обеих валют
        assert 'RUB' in result['static']['gaps']
        assert 'USD' in result['static']['gaps']

        # Должны быть изменения для обеих валют
        volume_changes = result['dynamic']['volume_changes']
        rub_changes = [vc for vc in volume_changes if vc.rate_change_bps == 200.0]
        usd_changes = [vc for vc in volume_changes if vc.rate_change_bps == 100.0]

        assert len(rub_changes) > 0
        assert len(usd_changes) > 0
