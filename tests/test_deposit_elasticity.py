"""
Unit Tests for Deposit Elasticity Model
Тесты для модели эластичности депозитов
"""
import pytest
from datetime import date, timedelta
from decimal import Decimal

from alm_calculator.models.instruments.deposit import Deposit
from alm_calculator.risks.interest_rate.deposit_elasticity import (
    DepositElasticityCalculator,
    ElasticityParameters,
    CustomerSegment,
    DepositType,
    create_default_elasticity_config
)
from alm_calculator.config.elasticity_config_example import (
    create_baseline_elasticity_config,
    create_conservative_elasticity_config,
    create_optimistic_elasticity_config
)


@pytest.fixture
def calculation_date():
    """Фикстура с датой расчета"""
    return date(2025, 1, 1)


@pytest.fixture
def sample_retail_demand_deposit():
    """Фикстура с примером депозита ФЛ до востребования"""
    return Deposit(
        instrument_id="DEP_001",
        amount=Decimal("1000000"),
        currency="RUB",
        interest_rate=0.08,
        start_date=date(2024, 1, 1),
        maturity_date=date(2025, 12, 31),
        is_demand_deposit=True,
        counterparty_type="retail",
        counterparty_name="Иванов И.И."
    )


@pytest.fixture
def sample_retail_term_deposit():
    """Фикстура с примером срочного депозита ФЛ"""
    return Deposit(
        instrument_id="DEP_002",
        amount=Decimal("2000000"),
        currency="RUB",
        interest_rate=0.10,
        start_date=date(2024, 10, 1),
        maturity_date=date(2025, 4, 1),  # 6 месяцев
        is_demand_deposit=False,
        counterparty_type="retail",
        counterparty_name="Петров П.П."
    )


@pytest.fixture
def sample_corporate_deposit():
    """Фикстура с примером депозита ЮЛ"""
    return Deposit(
        instrument_id="DEP_003",
        amount=Decimal("5000000"),
        currency="RUB",
        interest_rate=0.09,
        start_date=date(2024, 11, 1),
        maturity_date=date(2025, 2, 1),  # 3 месяца
        is_demand_deposit=False,
        counterparty_type="corporate",
        counterparty_name="ООО Рога и Копыта"
    )


class TestElasticityParameters:
    """Тесты для ElasticityParameters"""

    def test_create_retail_demand_default(self):
        """Тест создания дефолтных параметров для ФЛ до востребования"""
        params = ElasticityParameters.create_retail_demand_default()

        assert params.customer_segment == CustomerSegment.RETAIL
        assert params.deposit_type == DepositType.DEMAND
        assert params.base_elasticity < 0  # Отрицательная эластичность
        assert params.asymmetric is True
        assert params.adjustment_speed > 0
        assert params.max_volume_change is not None
        assert params.min_remaining_volume is not None

    def test_create_retail_term_default(self):
        """Тест создания дефолтных параметров для срочных депозитов ФЛ"""
        params = ElasticityParameters.create_retail_term_default(DepositType.SHORT_TERM)

        assert params.customer_segment == CustomerSegment.RETAIL
        assert params.deposit_type == DepositType.SHORT_TERM
        assert params.base_elasticity < 0
        assert abs(params.base_elasticity) > abs(
            ElasticityParameters.create_retail_demand_default().base_elasticity
        )  # Срочные более чувствительны

    def test_create_corporate_default(self):
        """Тест создания дефолтных параметров для ЮЛ"""
        params = ElasticityParameters.create_corporate_default(DepositType.SHORT_TERM)

        assert params.customer_segment == CustomerSegment.CORPORATE
        assert abs(params.base_elasticity) > abs(
            ElasticityParameters.create_retail_term_default().base_elasticity
        )  # Корпоративные более чувствительны
        assert params.adjustment_speed > 0.8  # Быстрая адаптация


class TestDepositElasticityCalculator:
    """Тесты для DepositElasticityCalculator"""

    def test_init(self, calculation_date):
        """Тест инициализации калькулятора"""
        config = create_default_elasticity_config()
        calculator = DepositElasticityCalculator(
            calculation_date=calculation_date,
            elasticity_params=config
        )

        assert calculator.calculation_date == calculation_date
        assert len(calculator.elasticity_params) > 0

    def test_determine_customer_segment(self, calculation_date, sample_retail_demand_deposit):
        """Тест определения сегмента клиента"""
        config = create_default_elasticity_config()
        calculator = DepositElasticityCalculator(calculation_date, config)

        segment = calculator._determine_customer_segment(sample_retail_demand_deposit, None)
        assert segment == CustomerSegment.RETAIL

    def test_determine_deposit_type_demand(self, calculation_date, sample_retail_demand_deposit):
        """Тест определения типа депозита (до востребования)"""
        config = create_default_elasticity_config()
        calculator = DepositElasticityCalculator(calculation_date, config)

        dtype = calculator._determine_deposit_type(sample_retail_demand_deposit)
        assert dtype == DepositType.DEMAND

    def test_determine_deposit_type_term(self, calculation_date, sample_retail_term_deposit):
        """Тест определения типа депозита (срочный)"""
        config = create_default_elasticity_config()
        calculator = DepositElasticityCalculator(calculation_date, config)

        dtype = calculator._determine_deposit_type(sample_retail_term_deposit)
        assert dtype == DepositType.MEDIUM_TERM  # 6 месяцев

    def test_calculate_volume_changes_positive_shock(
        self,
        calculation_date,
        sample_retail_demand_deposit
    ):
        """Тест расчета изменения объема при росте ставки"""
        config = create_default_elasticity_config()
        calculator = DepositElasticityCalculator(calculation_date, config)

        # Шок +200 б.п. по рублю
        rate_shocks = {'RUB': 200.0}

        volume_changes = calculator.calculate_volume_changes(
            [sample_retail_demand_deposit],
            rate_shocks
        )

        assert len(volume_changes) == 1
        vc = volume_changes[0]

        # При положительном шоке и отрицательной эластичности объем должен снизиться
        # (клиенты уходят к конкурентам с более высокими ставками)
        assert vc.volume_change < 0
        assert vc.new_amount < vc.original_amount
        assert vc.elasticity_used < 0

    def test_calculate_volume_changes_negative_shock(
        self,
        calculation_date,
        sample_retail_demand_deposit
    ):
        """Тест расчета изменения объема при снижении ставки"""
        config = create_default_elasticity_config()
        calculator = DepositElasticityCalculator(calculation_date, config)

        # Шок -100 б.п. по рублю
        rate_shocks = {'RUB': -100.0}

        volume_changes = calculator.calculate_volume_changes(
            [sample_retail_demand_deposit],
            rate_shocks
        )

        assert len(volume_changes) == 1
        vc = volume_changes[0]

        # При отрицательном шоке и отрицательной эластичности объем должен вырасти
        # (клиенты приходят от конкурентов)
        assert vc.volume_change > 0
        assert vc.new_amount > vc.original_amount

    def test_calculate_volume_changes_multiple_deposits(
        self,
        calculation_date,
        sample_retail_demand_deposit,
        sample_retail_term_deposit,
        sample_corporate_deposit
    ):
        """Тест расчета изменений для нескольких депозитов"""
        config = create_default_elasticity_config()
        calculator = DepositElasticityCalculator(calculation_date, config)

        deposits = [
            sample_retail_demand_deposit,
            sample_retail_term_deposit,
            sample_corporate_deposit
        ]

        rate_shocks = {'RUB': 150.0}

        volume_changes = calculator.calculate_volume_changes(deposits, rate_shocks)

        assert len(volume_changes) == 3

        # Корпоративный депозит должен реагировать сильнее
        corporate_change = next(vc for vc in volume_changes if vc.instrument_id == "DEP_003")
        retail_demand_change = next(vc for vc in volume_changes if vc.instrument_id == "DEP_001")

        assert abs(corporate_change.volume_change_pct) > abs(retail_demand_change.volume_change_pct)

    def test_min_remaining_volume_constraint(self, calculation_date):
        """Тест ограничения минимального остатка"""
        # Создаем параметры с минимальным остатком 70%
        config = {
            (CustomerSegment.RETAIL, DepositType.DEMAND): ElasticityParameters(
                customer_segment=CustomerSegment.RETAIL,
                deposit_type=DepositType.DEMAND,
                base_elasticity=-2.0,  # Очень сильная эластичность
                adjustment_speed=1.0,
                min_remaining_volume=0.70  # Минимум 70%
            )
        }

        calculator = DepositElasticityCalculator(calculation_date, config)

        deposit = Deposit(
            instrument_id="DEP_TEST",
            amount=Decimal("1000000"),
            currency="RUB",
            interest_rate=0.08,
            start_date=date(2024, 1, 1),
            maturity_date=date(2025, 12, 31),
            is_demand_deposit=True,
            counterparty_type="retail"
        )

        # Огромный шок +500 б.п.
        rate_shocks = {'RUB': 500.0}

        volume_changes = calculator.calculate_volume_changes([deposit], rate_shocks)

        assert len(volume_changes) == 1
        vc = volume_changes[0]

        # Проверяем, что остаток не меньше 70%
        assert vc.new_amount >= vc.original_amount * Decimal("0.70")

    def test_max_volume_change_constraint(self, calculation_date):
        """Тест ограничения максимального изменения"""
        config = {
            (CustomerSegment.RETAIL, DepositType.DEMAND): ElasticityParameters(
                customer_segment=CustomerSegment.RETAIL,
                deposit_type=DepositType.DEMAND,
                base_elasticity=-2.0,
                adjustment_speed=1.0,
                max_volume_change=0.15  # Максимум 15%
            )
        }

        calculator = DepositElasticityCalculator(calculation_date, config)

        deposit = Deposit(
            instrument_id="DEP_TEST",
            amount=Decimal("1000000"),
            currency="RUB",
            interest_rate=0.08,
            start_date=date(2024, 1, 1),
            maturity_date=date(2025, 12, 31),
            is_demand_deposit=True,
            counterparty_type="retail"
        )

        rate_shocks = {'RUB': 500.0}

        volume_changes = calculator.calculate_volume_changes([deposit], rate_shocks)

        vc = volume_changes[0]

        # Проверяем, что изменение не больше 15%
        assert abs(vc.volume_change_pct) <= 0.15

    def test_create_dynamic_balance_sheet(
        self,
        calculation_date,
        sample_retail_demand_deposit,
        sample_retail_term_deposit
    ):
        """Тест создания динамического баланса"""
        config = create_default_elasticity_config()
        calculator = DepositElasticityCalculator(calculation_date, config)

        deposits = [sample_retail_demand_deposit, sample_retail_term_deposit]
        rate_shocks = {'RUB': 200.0}

        new_deposits, changes_df = calculator.create_dynamic_balance_sheet(deposits, rate_shocks)

        assert len(new_deposits) == len(deposits)
        assert not changes_df.empty
        assert 'volume_change' in changes_df.columns
        assert 'elasticity' in changes_df.columns

        # Проверяем, что новые депозиты имеют обновленные объемы
        for new_dep in new_deposits:
            original_dep = next(d for d in deposits if d.instrument_id == new_dep.instrument_id)
            if new_dep.instrument_id in changes_df['instrument_id'].values:
                # Объем должен измениться
                assert new_dep.amount != original_dep.amount

    def test_analyze_elasticity_impact(
        self,
        calculation_date,
        sample_retail_demand_deposit,
        sample_corporate_deposit
    ):
        """Тест анализа влияния эластичности"""
        config = create_default_elasticity_config()
        calculator = DepositElasticityCalculator(calculation_date, config)

        deposits = [sample_retail_demand_deposit, sample_corporate_deposit]
        rate_shocks = {'RUB': 150.0}

        volume_changes = calculator.calculate_volume_changes(deposits, rate_shocks)
        summary = calculator.analyze_elasticity_impact(volume_changes)

        assert not summary.empty
        assert 'customer_segment' in summary.columns
        assert 'deposit_type' in summary.columns
        assert 'volume_change' in summary.columns
        assert 'agg_volume_change_pct' in summary.columns


class TestElasticityConfigs:
    """Тесты для различных конфигураций эластичности"""

    def test_baseline_config(self):
        """Тест базовой конфигурации"""
        config = create_baseline_elasticity_config()

        assert len(config) > 0
        assert (CustomerSegment.RETAIL, DepositType.DEMAND) in config
        assert (CustomerSegment.CORPORATE, DepositType.SHORT_TERM) in config

    def test_conservative_config(self):
        """Тест консервативной конфигурации"""
        conservative = create_conservative_elasticity_config()
        baseline = create_baseline_elasticity_config()

        # Консервативная должна иметь более сильную эластичность
        retail_demand_key = (CustomerSegment.RETAIL, DepositType.DEMAND)

        cons_elasticity = abs(conservative[retail_demand_key].base_elasticity)
        base_elasticity = abs(baseline[retail_demand_key].base_elasticity)

        assert cons_elasticity >= base_elasticity

    def test_optimistic_config(self):
        """Тест оптимистичной конфигурации"""
        optimistic = create_optimistic_elasticity_config()
        baseline = create_baseline_elasticity_config()

        # Оптимистичная должна иметь более слабую эластичность
        retail_demand_key = (CustomerSegment.RETAIL, DepositType.DEMAND)

        opt_elasticity = abs(optimistic[retail_demand_key].base_elasticity)
        base_elasticity = abs(baseline[retail_demand_key].base_elasticity)

        assert opt_elasticity <= base_elasticity


class TestAsymmetricElasticity:
    """Тесты для асимметричной эластичности"""

    def test_asymmetric_positive_vs_negative_shock(self, calculation_date):
        """Тест различной реакции на положительный и отрицательный шоки"""
        config = {
            (CustomerSegment.RETAIL, DepositType.DEMAND): ElasticityParameters(
                customer_segment=CustomerSegment.RETAIL,
                deposit_type=DepositType.DEMAND,
                base_elasticity=-0.5,
                asymmetric=True,
                positive_shock_elasticity=-0.2,  # Слабая реакция на рост
                negative_shock_elasticity=-0.8,  # Сильная на падение
                adjustment_speed=1.0
            )
        }

        calculator = DepositElasticityCalculator(calculation_date, config)

        deposit = Deposit(
            instrument_id="DEP_TEST",
            amount=Decimal("1000000"),
            currency="RUB",
            interest_rate=0.08,
            start_date=date(2024, 1, 1),
            maturity_date=date(2025, 12, 31),
            is_demand_deposit=True,
            counterparty_type="retail"
        )

        # Положительный шок
        pos_changes = calculator.calculate_volume_changes([deposit], {'RUB': 100.0})
        pos_change_pct = abs(pos_changes[0].volume_change_pct)

        # Отрицательный шок
        neg_changes = calculator.calculate_volume_changes([deposit], {'RUB': -100.0})
        neg_change_pct = abs(neg_changes[0].volume_change_pct)

        # Реакция на отрицательный шок должна быть сильнее
        assert neg_change_pct > pos_change_pct


class TestThresholdElasticity:
    """Тесты для пороговой эластичности"""

    def test_below_above_threshold(self, calculation_date):
        """Тест различной эластичности ниже и выше порога"""
        config = {
            (CustomerSegment.RETAIL, DepositType.SHORT_TERM): ElasticityParameters(
                customer_segment=CustomerSegment.RETAIL,
                deposit_type=DepositType.SHORT_TERM,
                base_elasticity=-0.5,
                threshold_rate_change=1.0,  # Порог 1 п.п.
                below_threshold_elasticity=-0.3,  # Слабая ниже порога
                above_threshold_elasticity=-0.9,  # Сильная выше порога
                adjustment_speed=1.0
            )
        }

        calculator = DepositElasticityCalculator(calculation_date, config)

        deposit = Deposit(
            instrument_id="DEP_TEST",
            amount=Decimal("1000000"),
            currency="RUB",
            interest_rate=0.10,
            start_date=date(2024, 10, 1),
            maturity_date=date(2025, 4, 1),
            is_demand_deposit=False,
            counterparty_type="retail"
        )

        # Шок ниже порога (50 б.п. = 0.5 п.п.)
        below_changes = calculator.calculate_volume_changes([deposit], {'RUB': 50.0})
        below_elasticity = abs(below_changes[0].elasticity_used)

        # Шок выше порога (150 б.п. = 1.5 п.п.)
        above_changes = calculator.calculate_volume_changes([deposit], {'RUB': 150.0})
        above_elasticity = abs(above_changes[0].elasticity_used)

        # Эластичность выше порога должна быть сильнее
        assert above_elasticity > below_elasticity
