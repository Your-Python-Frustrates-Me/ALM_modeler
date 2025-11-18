"""
Пример использования новой системы расчета горизонта выживания
без персональных предпосылок

Демонстрирует:
1. Загрузку конфигурации behavioral assumptions
2. Применение assumptions к инструментам
3. Расчет горизонта выживания с множественными сценариями (NAME, MARKET, COMBO)
"""
from datetime import date
from decimal import Decimal
import pandas as pd
import json
from pathlib import Path

# Импорты из проекта
from alm_calculator.risks.liquidity.behavioral_assumptions import (
    BehavioralAssumptionsManager,
    CounterpartyAssumption
)
from alm_calculator.risks.liquidity.survival_horizon import (
    SurvivalHorizonCalculator,
    export_to_excel
)


def load_assumptions_config(config_path: str) -> BehavioralAssumptionsManager:
    """Загружает конфигурацию assumptions из JSON файла"""
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    manager = BehavioralAssumptionsManager()
    manager.load_from_config(config)

    return manager


def apply_assumptions_to_flows(
    flows_df: pd.DataFrame,
    assumptions_manager: BehavioralAssumptionsManager
) -> pd.DataFrame:
    """
    Применяет behavioral assumptions к потокам.

    Args:
        flows_df: DataFrame с потоками инструментов
            Колонки: COUNTERPARTY_NAME, COUNTERPARTY_TYPE, INSTRUMENT_CLASS,
                     INSTRUMENT_SUBCLASS, CURRENCY, AMOUNT, MATURITY_DAYS, etc.
        assumptions_manager: Менеджер assumptions

    Returns:
        DataFrame с модифицированными потоками согласно assumptions
    """
    modified_flows = []

    for idx, row in flows_df.iterrows():
        # Собираем данные инструмента для проверки правил
        instrument_data = {
            'counterparty_name': row.get('COUNTERPARTY_NAME'),
            'counterparty_type': row.get('COUNTERPARTY_TYPE'),
            'instrument_class': row.get('INSTRUMENT_CLASS'),
            'instrument_subclass': row.get('INSTRUMENT_SUBCLASS'),
            'currency': row.get('CURRENCY', 'RUB'),
            'amount': row.get('AMOUNT', 0),
            'maturity_days': row.get('MATURITY_DAYS', 0)
        }

        # Получаем применимые assumptions
        assumptions = assumptions_manager.get_assumptions_for_instrument(instrument_data)

        # Применяем assumptions к потоку
        modified_row = row.copy()

        # 1. Переопределение срочности (overnight treatment)
        if 'maturity_override' in assumptions:
            modified_row['MATURITY_DAYS'] = assumptions['maturity_override']
            modified_row['FLOW_DAY'] = assumptions['maturity_override']

        # 2. Переопределение оттока (full outflow)
        if 'runoff_override' in assumptions:
            runoff_rate = assumptions['runoff_override']
            # Применяем ко всем сценариям
            for scenario in ['NAME', 'MARKET', 'COMBO']:
                if scenario in modified_row:
                    modified_row[scenario] = -abs(modified_row['AMOUNT']) * runoff_rate

        # 3. Применение runoff rates по сценариям
        elif 'runoff_rates' in assumptions:
            runoff_rates = assumptions['runoff_rates']

            for scenario, bucket_rates in runoff_rates.items():
                if scenario not in modified_row:
                    continue

                # Определяем бакет для данного инструмента
                days = modified_row.get('MATURITY_DAYS', 0)
                bucket = get_bucket_for_days(days)

                # Применяем runoff rate
                if bucket in bucket_rates:
                    runoff_rate = bucket_rates[bucket]
                    modified_row[scenario] = -abs(modified_row['AMOUNT']) * runoff_rate

        # 4. Ограничение максимального оттока
        if 'maximum_outflow' in assumptions:
            max_outflow = assumptions['maximum_outflow']
            for scenario in ['NAME', 'MARKET', 'COMBO']:
                if scenario in modified_row:
                    # Берем минимум из текущего оттока и максимального
                    current_outflow = abs(modified_row[scenario])
                    modified_row[scenario] = -min(current_outflow, max_outflow)

        modified_flows.append(modified_row)

    return pd.DataFrame(modified_flows)


def get_bucket_for_days(days: int) -> str:
    """Определяет бакет по количеству дней"""
    if days <= 1:
        return 'overnight'
    elif days <= 7:
        return '2-7d'
    elif days <= 30:
        return '8-30d'
    elif days <= 90:
        return '30-90d'
    elif days <= 180:
        return '90-180d'
    elif days <= 365:
        return '180-365d'
    else:
        return '1y+'


def example_usage():
    """Пример полного использования системы"""

    # 1. Загружаем конфигурацию assumptions
    print("Loading behavioral assumptions configuration...")
    config_path = Path(__file__).parent / 'behavioral_assumptions_config_example.json'
    assumptions_manager = load_assumptions_config(str(config_path))

    print(f"Loaded {len(assumptions_manager.rules)} rules")
    print(f"Loaded {len(assumptions_manager.counterparty_assumptions)} counterparty assumptions\n")

    # 2. Создаем примерные данные потоков (обычно загружаются из БД)
    print("Creating sample flow data...")

    # Пример данных потоков
    sample_flows = pd.DataFrame([
        {
            'FLOW_DAY': 1,
            'COUNTERPARTY_NAME': 'EXAMPLE_MAJOR_CORPORATION_A',
            'COUNTERPARTY_TYPE': 'corporate',
            'INSTRUMENT_CLASS': 'ДЮЛ',
            'INSTRUMENT_SUBCLASS': 'Досрочка',
            'CURRENCY': 'RUB',
            'AMOUNT': 15_000_000_000,
            'MATURITY_DAYS': 90,
            'NAME': -15_000_000_000,
            'MARKET': -15_000_000_000,
            'COMBO': -15_000_000_000,
            'IN_BUFFER': 0
        },
        {
            'FLOW_DAY': 1,
            'COUNTERPARTY_NAME': 'EXAMPLE_TREASURY',
            'COUNTERPARTY_TYPE': 'government',
            'INSTRUMENT_CLASS': 'ДЮЛ',
            'INSTRUMENT_SUBCLASS': 'Досрочка',
            'CURRENCY': 'RUB',
            'AMOUNT': 25_000_000_000,
            'MATURITY_DAYS': 180,
            'NAME': -25_000_000_000,
            'MARKET': -25_000_000_000,
            'COMBO': -25_000_000_000,
            'IN_BUFFER': 0
        },
        {
            'FLOW_DAY': 30,
            'COUNTERPARTY_NAME': 'Regular Corporate Client',
            'COUNTERPARTY_TYPE': 'corporate',
            'INSTRUMENT_CLASS': 'ДЮЛ',
            'INSTRUMENT_SUBCLASS': 'Standard',
            'CURRENCY': 'RUB',
            'AMOUNT': 5_000_000_000,
            'MATURITY_DAYS': 30,
            'NAME': -5_000_000_000 * 0.15,
            'MARKET': -5_000_000_000 * 0.25,
            'COMBO': -5_000_000_000 * 0.35,
            'IN_BUFFER': 0
        },
        {
            'FLOW_DAY': 90,
            'COUNTERPARTY_NAME': 'Retail Customer Pool',
            'COUNTERPARTY_TYPE': 'retail',
            'INSTRUMENT_CLASS': 'ДФЛ',
            'INSTRUMENT_SUBCLASS': 'Standard',
            'CURRENCY': 'RUB',
            'AMOUNT': 10_000_000_000,
            'MATURITY_DAYS': 90,
            'NAME': -10_000_000_000 * 0.05,
            'MARKET': -10_000_000_000 * 0.10,
            'COMBO': -10_000_000_000 * 0.15,
            'IN_BUFFER': 0
        },
        {
            'FLOW_DAY': 5,
            'COUNTERPARTY_NAME': 'VIP Client 1',
            'COUNTERPARTY_TYPE': 'corporate',
            'INSTRUMENT_CLASS': 'ДЮЛ',
            'INSTRUMENT_SUBCLASS': 'VIP',
            'CURRENCY': 'RUB',
            'AMOUNT': 2_000_000_000,
            'MATURITY_DAYS': 365,
            'NAME': -2_000_000_000 * 0.02,
            'MARKET': -2_000_000_000 * 0.05,
            'COMBO': -2_000_000_000 * 0.10,
            'IN_BUFFER': 0
        }
    ])

    # 3. Применяем assumptions к потокам
    print("Applying behavioral assumptions to flows...")
    modified_flows = apply_assumptions_to_flows(sample_flows, assumptions_manager)

    print(f"Modified {len(modified_flows)} flow records\n")

    # 4. Определяем буфер ликвидности
    buffer = {
        'VALUE': 50_000_000_000.0,  # 50 млрд рублей
        'IMPAIRMENT': 2_000_000_000.0  # 2 млрд обесценения
    }

    print(f"Liquidity Buffer:")
    print(f"  Total Value: {buffer['VALUE']:,.0f} RUB")
    print(f"  Impairment: {buffer['IMPAIRMENT']:,.0f} RUB")
    print(f"  Impaired Value: {buffer['VALUE'] - buffer['IMPAIRMENT']:,.0f} RUB\n")

    # 5. Рассчитываем горизонт выживания
    print("Calculating survival horizon...")
    calculator = SurvivalHorizonCalculator(
        calculation_date=date(2025, 1, 15),
        max_horizon_days=90
    )

    results = calculator.calculate(
        daily_flows=modified_flows,
        buffer=buffer,
        exclude_from_buffer=True  # Исключаем потоки с IN_BUFFER=1
    )

    # 6. Выводим результаты
    print("\n" + "=" * 60)
    print("SURVIVAL HORIZON RESULTS")
    print("=" * 60)
    print(f"Calculation Date: {results['calculation_date']}")
    print(f"Buffer Value: {results['buffer_value']:,.0f} RUB")
    print(f"Buffer (Impaired): {results['buffer_impaired_value']:,.0f} RUB")
    print()

    print("Survival Horizon by Scenario:")
    for scenario, days in results['horizon_days'].items():
        print(f"  {scenario:10s}: {days:3d} days")

    # Находим минимальный горизонт
    min_horizon = min(results['horizon_days'].values())
    print(f"\nMinimum Horizon: {min_horizon} days")

    if min_horizon < 30:
        print("⚠️  WARNING: Survival horizon is less than 30 days!")
    elif min_horizon < 60:
        print("⚡ CAUTION: Survival horizon is less than 60 days")
    else:
        print("✓ Survival horizon is adequate")

    # 7. Экспортируем в Excel
    output_path = Path(__file__).parent / 'survival_horizon_results.xlsx'
    print(f"\nExporting results to {output_path}...")
    export_to_excel(results, str(output_path))

    print("\n✓ Complete!")

    return results


def example_adding_custom_assumptions():
    """Пример добавления пользовательских assumptions программно"""

    manager = BehavioralAssumptionsManager()

    # Добавляем правило для крупных корпоративных депозитов
    from alm_calculator.risks.liquidity.behavioral_assumptions import (
        AssumptionRule,
        AssumptionRuleType
    )

    rule = AssumptionRule(
        rule_id='custom_large_corporate',
        rule_type=AssumptionRuleType.COMBINED,
        priority=100,
        conditions={
            'counterparty_type': 'corporate',
            'amount': {'>=': 1_000_000_000}
        },
        assumptions={
            'stable_portion': 0.7,
            'avg_life_days': 120,
            'runoff_rates': {
                'NAME': {'overnight': 0.05, '2-7d': 0.10},
                'MARKET': {'overnight': 0.10, '2-7d': 0.15},
                'COMBO': {'overnight': 0.20, '2-7d': 0.30}
            }
        },
        description='Custom rule for large corporate deposits'
    )

    manager.add_rule(rule)

    # Добавляем assumptions для конкретного контрагента
    cp_assumption = CounterpartyAssumption(
        counterparty_name='MY_SPECIAL_CLIENT',
        stable_portion=0.95,
        avg_life_days=365,
        overnight_treatment=False,
        full_outflow=False
    )

    manager.add_counterparty_assumption('MY_SPECIAL_CLIENT', cp_assumption)

    print(f"Added custom assumptions:")
    print(f"  Rules: {len(manager.rules)}")
    print(f"  Counterparty assumptions: {len(manager.counterparty_assumptions)}")

    return manager


if __name__ == '__main__':
    # Запускаем основной пример
    results = example_usage()

    # Можно также добавить пользовательские assumptions
    # custom_manager = example_adding_custom_assumptions()
