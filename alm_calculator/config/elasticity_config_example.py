"""
Example Configuration for Deposit Elasticity Parameters
Пример конфигурации параметров эластичности депозитов

Этот файл содержит примеры конфигурации параметров эластичности
для различных типов депозитов и сегментов клиентов.
"""
from alm_calculator.risks.interest_rate.deposit_elasticity import (
    ElasticityParameters,
    CustomerSegment,
    DepositType
)


def create_conservative_elasticity_config():
    """
    Консервативная конфигурация эластичности.

    Используется для стресс-тестирования: предполагает более сильную
    реакцию депозитов на изменение ставок.
    """
    config = {}

    # Физические лица - до востребования
    config[(CustomerSegment.RETAIL, DepositType.DEMAND)] = ElasticityParameters(
        customer_segment=CustomerSegment.RETAIL,
        deposit_type=DepositType.DEMAND,
        base_elasticity=-0.5,  # Более сильная реакция
        asymmetric=True,
        positive_shock_elasticity=-0.3,
        negative_shock_elasticity=-0.6,  # Сильный отток при снижении ставок
        adjustment_speed=0.7,  # Быстрая адаптация
        lag_days=15,  # Меньшая задержка
        max_volume_change=0.25,
        min_remaining_volume=0.50  # Меньше устойчивая часть
    )

    # Физические лица - краткосрочные
    config[(CustomerSegment.RETAIL, DepositType.SHORT_TERM)] = ElasticityParameters(
        customer_segment=CustomerSegment.RETAIL,
        deposit_type=DepositType.SHORT_TERM,
        base_elasticity=-0.7,
        asymmetric=True,
        positive_shock_elasticity=-0.8,
        negative_shock_elasticity=-0.6,
        threshold_rate_change=0.5,  # Низкий порог
        below_threshold_elasticity=-0.5,
        above_threshold_elasticity=-1.0,  # Очень сильная реакция
        adjustment_speed=0.9,
        lag_days=3,
        max_volume_change=0.35,
        min_remaining_volume=0.40
    )

    # Физические лица - среднесрочные
    config[(CustomerSegment.RETAIL, DepositType.MEDIUM_TERM)] = ElasticityParameters(
        customer_segment=CustomerSegment.RETAIL,
        deposit_type=DepositType.MEDIUM_TERM,
        base_elasticity=-0.6,
        adjustment_speed=0.8,
        lag_days=7,
        max_volume_change=0.30,
        min_remaining_volume=0.45
    )

    # Физические лица - долгосрочные
    config[(CustomerSegment.RETAIL, DepositType.LONG_TERM)] = ElasticityParameters(
        customer_segment=CustomerSegment.RETAIL,
        deposit_type=DepositType.LONG_TERM,
        base_elasticity=-0.4,
        adjustment_speed=0.5,
        lag_days=30,
        max_volume_change=0.15,
        min_remaining_volume=0.65
    )

    # Юридические лица - все типы
    for dtype in [DepositType.DEMAND, DepositType.SHORT_TERM,
                  DepositType.MEDIUM_TERM, DepositType.LONG_TERM]:
        config[(CustomerSegment.CORPORATE, dtype)] = ElasticityParameters(
            customer_segment=CustomerSegment.CORPORATE,
            deposit_type=dtype,
            base_elasticity=-1.0,  # Очень сильная реакция
            adjustment_speed=0.95,  # Почти мгновенная
            lag_days=1,
            competitive_factor=1.8,  # Высокая конкуренция
            max_volume_change=0.50,
            min_remaining_volume=0.20
        )

    return config


def create_optimistic_elasticity_config():
    """
    Оптимистичная конфигурация эластичности.

    Предполагает более слабую реакцию депозитов на изменение ставок.
    Используется для базовых сценариев.
    """
    config = {}

    # Физические лица - до востребования
    config[(CustomerSegment.RETAIL, DepositType.DEMAND)] = ElasticityParameters(
        customer_segment=CustomerSegment.RETAIL,
        deposit_type=DepositType.DEMAND,
        base_elasticity=-0.2,  # Слабая реакция
        asymmetric=True,
        positive_shock_elasticity=-0.1,  # Очень слабая на рост
        negative_shock_elasticity=-0.3,
        adjustment_speed=0.3,  # Медленная адаптация
        lag_days=60,  # Большая задержка
        max_volume_change=0.10,
        min_remaining_volume=0.70  # Большая устойчивая часть
    )

    # Физические лица - срочные
    config[(CustomerSegment.RETAIL, DepositType.SHORT_TERM)] = ElasticityParameters(
        customer_segment=CustomerSegment.RETAIL,
        deposit_type=DepositType.SHORT_TERM,
        base_elasticity=-0.3,
        asymmetric=True,
        positive_shock_elasticity=-0.4,
        negative_shock_elasticity=-0.2,
        threshold_rate_change=2.0,  # Высокий порог
        below_threshold_elasticity=-0.2,
        above_threshold_elasticity=-0.5,
        adjustment_speed=0.5,
        lag_days=14,
        max_volume_change=0.15,
        min_remaining_volume=0.60
    )

    # Физические лица - средне- и долгосрочные
    for dtype in [DepositType.MEDIUM_TERM, DepositType.LONG_TERM]:
        config[(CustomerSegment.RETAIL, dtype)] = ElasticityParameters(
            customer_segment=CustomerSegment.RETAIL,
            deposit_type=dtype,
            base_elasticity=-0.2,
            adjustment_speed=0.4,
            lag_days=45,
            max_volume_change=0.10,
            min_remaining_volume=0.75
        )

    # Юридические лица
    for dtype in [DepositType.DEMAND, DepositType.SHORT_TERM,
                  DepositType.MEDIUM_TERM, DepositType.LONG_TERM]:
        config[(CustomerSegment.CORPORATE, dtype)] = ElasticityParameters(
            customer_segment=CustomerSegment.CORPORATE,
            deposit_type=dtype,
            base_elasticity=-0.6,  # Умеренная реакция
            adjustment_speed=0.7,
            lag_days=3,
            competitive_factor=1.2,
            max_volume_change=0.30,
            min_remaining_volume=0.40
        )

    return config


def create_baseline_elasticity_config():
    """
    Базовая конфигурация эластичности.

    Сбалансированная конфигурация для обычных расчетов.
    """
    config = {}

    # ФЛ - до востребования
    config[(CustomerSegment.RETAIL, DepositType.DEMAND)] = \
        ElasticityParameters.create_retail_demand_default()

    # ФЛ - краткосрочные
    config[(CustomerSegment.RETAIL, DepositType.SHORT_TERM)] = \
        ElasticityParameters.create_retail_term_default(DepositType.SHORT_TERM)

    # ФЛ - среднесрочные
    config[(CustomerSegment.RETAIL, DepositType.MEDIUM_TERM)] = \
        ElasticityParameters.create_retail_term_default(DepositType.MEDIUM_TERM)

    # ФЛ - долгосрочные
    config[(CustomerSegment.RETAIL, DepositType.LONG_TERM)] = ElasticityParameters(
        customer_segment=CustomerSegment.RETAIL,
        deposit_type=DepositType.LONG_TERM,
        base_elasticity=-0.3,
        adjustment_speed=0.5,
        lag_days=60,
        max_volume_change=0.12,
        min_remaining_volume=0.70
    )

    # ЮЛ
    for dtype in [DepositType.DEMAND, DepositType.SHORT_TERM,
                  DepositType.MEDIUM_TERM, DepositType.LONG_TERM]:
        config[(CustomerSegment.CORPORATE, dtype)] = \
            ElasticityParameters.create_corporate_default(dtype)

    # МСБ
    for dtype in [DepositType.DEMAND, DepositType.SHORT_TERM,
                  DepositType.MEDIUM_TERM]:
        config[(CustomerSegment.SME, dtype)] = ElasticityParameters(
            customer_segment=CustomerSegment.SME,
            deposit_type=dtype,
            base_elasticity=-0.6,
            adjustment_speed=0.8,
            lag_days=5,
            competitive_factor=1.3,
            max_volume_change=0.30,
            min_remaining_volume=0.40
        )

    return config


# Пример кастомной конфигурации для конкретного банка
def create_custom_bank_elasticity_config():
    """
    Кастомная конфигурация для конкретного банка.

    Может быть основана на исторических данных, анализе поведения клиентов,
    конкурентной позиции банка и т.д.
    """
    config = {}

    # Пример: Банк с очень лояльной базой розничных клиентов
    config[(CustomerSegment.RETAIL, DepositType.DEMAND)] = ElasticityParameters(
        customer_segment=CustomerSegment.RETAIL,
        deposit_type=DepositType.DEMAND,
        base_elasticity=-0.15,  # Низкая эластичность из-за лояльности
        asymmetric=True,
        positive_shock_elasticity=-0.05,  # Очень слабая реакция на рост
        negative_shock_elasticity=-0.25,  # Умеренная на падение
        adjustment_speed=0.4,
        lag_days=45,
        max_volume_change=0.08,
        min_remaining_volume=0.80,  # 80% остается в любом случае
        competitive_factor=0.8  # Низкая конкуренция (нишевой банк)
    )

    # Пример: Высококонкурентный рынок срочных депозитов ФЛ
    config[(CustomerSegment.RETAIL, DepositType.SHORT_TERM)] = ElasticityParameters(
        customer_segment=CustomerSegment.RETAIL,
        deposit_type=DepositType.SHORT_TERM,
        base_elasticity=-0.8,
        asymmetric=True,
        positive_shock_elasticity=-0.9,  # Сильная на рост (переток к конкурентам)
        negative_shock_elasticity=-0.7,
        threshold_rate_change=0.25,  # Порог 25 б.п.
        below_threshold_elasticity=-0.4,
        above_threshold_elasticity=-1.2,
        adjustment_speed=0.85,
        lag_days=7,
        max_volume_change=0.40,
        min_remaining_volume=0.35,
        competitive_factor=1.6  # Высокая конкуренция
    )

    # Для остальных сегментов используем базовые параметры
    config[(CustomerSegment.RETAIL, DepositType.MEDIUM_TERM)] = \
        ElasticityParameters.create_retail_term_default(DepositType.MEDIUM_TERM)

    config[(CustomerSegment.RETAIL, DepositType.LONG_TERM)] = ElasticityParameters(
        customer_segment=CustomerSegment.RETAIL,
        deposit_type=DepositType.LONG_TERM,
        base_elasticity=-0.25,
        adjustment_speed=0.45,
        lag_days=60,
        max_volume_change=0.10,
        min_remaining_volume=0.75
    )

    # ЮЛ - используем дефолтные корпоративные параметры
    for dtype in [DepositType.DEMAND, DepositType.SHORT_TERM,
                  DepositType.MEDIUM_TERM, DepositType.LONG_TERM]:
        config[(CustomerSegment.CORPORATE, dtype)] = \
            ElasticityParameters.create_corporate_default(dtype)

    return config


# Словарь всех доступных конфигураций
ELASTICITY_CONFIGS = {
    'baseline': create_baseline_elasticity_config,
    'conservative': create_conservative_elasticity_config,
    'optimistic': create_optimistic_elasticity_config,
    'custom': create_custom_bank_elasticity_config
}


def get_elasticity_config(config_name: str = 'baseline'):
    """
    Получает конфигурацию эластичности по имени.

    Args:
        config_name: Имя конфигурации ('baseline', 'conservative', 'optimistic', 'custom')

    Returns:
        Dict[Tuple[CustomerSegment, DepositType], ElasticityParameters]
    """
    if config_name not in ELASTICITY_CONFIGS:
        raise ValueError(f"Unknown elasticity config: {config_name}. "
                        f"Available: {list(ELASTICITY_CONFIGS.keys())}")

    return ELASTICITY_CONFIGS[config_name]()
