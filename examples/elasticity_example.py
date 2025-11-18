"""
Example: Deposit Elasticity Model for Interest Rate Risk
Пример использования модели эластичности депозитов для процентного риска

Этот пример демонстрирует:
1. Расчет изменения объемов депозитов при изменении ставок
2. Построение динамического баланса
3. Сравнение процентного риска на статическом и динамическом балансе
4. Анализ влияния эластичности по сегментам клиентов
"""
from datetime import date
from decimal import Decimal
import pandas as pd

from alm_calculator.models.instruments.deposit import Deposit
from alm_calculator.models.instruments.loan import Loan
from alm_calculator.risks.interest_rate.dynamic_balance_irr_calculator import (
    DynamicBalanceIRRCalculator,
    export_dynamic_irr_to_excel
)
from alm_calculator.config.elasticity_config_example import (
    create_baseline_elasticity_config,
    create_conservative_elasticity_config,
    create_optimistic_elasticity_config,
    get_elasticity_config
)


def create_sample_portfolio():
    """
    Создает примерный портфель банка с депозитами и кредитами.
    """
    instruments = []
    calc_date = date(2025, 1, 1)

    # === ДЕПОЗИТЫ ФИЗИЧЕСКИХ ЛИЦ ===

    # До востребования
    for i in range(10):
        instruments.append(Deposit(
            instrument_id=f"DEP_RETAIL_DEMAND_{i}",
            amount=Decimal("5000000") + Decimal(i * 1000000),
            currency="RUB",
            interest_rate=0.06,
            start_date=date(2024, 1, 1),
            maturity_date=date(2026, 1, 1),
            is_demand_deposit=True,
            counterparty_type="retail",
            counterparty_name=f"Клиент ФЛ {i}"
        ))

    # Краткосрочные (до 3 месяцев)
    for i in range(15):
        instruments.append(Deposit(
            instrument_id=f"DEP_RETAIL_SHORT_{i}",
            amount=Decimal("2000000") + Decimal(i * 500000),
            currency="RUB",
            interest_rate=0.10,
            start_date=date(2024, 11, 1),
            maturity_date=date(2025, 2, 1),
            is_demand_deposit=False,
            counterparty_type="retail",
            counterparty_name=f"Клиент ФЛ {i+10}"
        ))

    # Среднесрочные (3-12 месяцев)
    for i in range(10):
        instruments.append(Deposit(
            instrument_id=f"DEP_RETAIL_MEDIUM_{i}",
            amount=Decimal("3000000") + Decimal(i * 700000),
            currency="RUB",
            interest_rate=0.11,
            start_date=date(2024, 7, 1),
            maturity_date=date(2025, 7, 1),
            is_demand_deposit=False,
            counterparty_type="retail",
            counterparty_name=f"Клиент ФЛ {i+25}"
        ))

    # === ДЕПОЗИТЫ ЮРИДИЧЕСКИХ ЛИЦ ===

    # Краткосрочные
    for i in range(8):
        instruments.append(Deposit(
            instrument_id=f"DEP_CORP_SHORT_{i}",
            amount=Decimal("10000000") + Decimal(i * 2000000),
            currency="RUB",
            interest_rate=0.09,
            start_date=date(2024, 11, 1),
            maturity_date=date(2025, 2, 1),
            is_demand_deposit=False,
            counterparty_type="corporate",
            counterparty_name=f"ООО Компания {i}"
        ))

    # До востребования
    for i in range(5):
        instruments.append(Deposit(
            instrument_id=f"DEP_CORP_DEMAND_{i}",
            amount=Decimal("8000000") + Decimal(i * 1500000),
            currency="RUB",
            interest_rate=0.07,
            start_date=date(2024, 1, 1),
            maturity_date=date(2026, 1, 1),
            is_demand_deposit=True,
            counterparty_type="corporate",
            counterparty_name=f"ООО Фирма {i}"
        ))

    # === КРЕДИТЫ ===

    # Ипотека
    for i in range(20):
        instruments.append(Loan(
            instrument_id=f"LOAN_MORTGAGE_{i}",
            amount=Decimal("4000000") + Decimal(i * 500000),
            currency="RUB",
            interest_rate=0.12,
            start_date=date(2023, 1, 1),
            maturity_date=date(2028, 1, 1),
            counterparty_type="retail",
            loan_type="mortgage"
        ))

    # Потребительские кредиты
    for i in range(15):
        instruments.append(Loan(
            instrument_id=f"LOAN_CONSUMER_{i}",
            amount=Decimal("500000") + Decimal(i * 100000),
            currency="RUB",
            interest_rate=0.18,
            start_date=date(2024, 6, 1),
            maturity_date=date(2027, 6, 1),
            counterparty_type="retail",
            loan_type="consumer"
        ))

    # Корпоративные кредиты
    for i in range(10):
        instruments.append(Loan(
            instrument_id=f"LOAN_CORPORATE_{i}",
            amount=Decimal("15000000") + Decimal(i * 3000000),
            currency="RUB",
            interest_rate=0.13,
            start_date=date(2024, 1, 1),
            maturity_date=date(2027, 1, 1),
            counterparty_type="corporate",
            loan_type="corporate_loan"
        ))

    return instruments


def analyze_baseline_scenario():
    """
    Анализ базового сценария: рост ставок на 200 б.п.
    """
    print("=" * 80)
    print("БАЗОВЫЙ СЦЕНАРИЙ: Рост ставок на 200 б.п.")
    print("=" * 80)

    # Создаем портфель
    instruments = create_sample_portfolio()
    calc_date = date(2025, 1, 1)

    # Подсчитываем общие объемы
    total_deposits = sum(
        inst.amount for inst in instruments if isinstance(inst, Deposit)
    )
    total_loans = sum(
        inst.amount for inst in instruments if isinstance(inst, Loan)
    )

    print(f"\nПортфель на {calc_date}:")
    print(f"  Депозиты: {float(total_deposits):,.0f} RUB")
    print(f"  Кредиты:  {float(total_loans):,.0f} RUB")
    print(f"  Gap:      {float(total_loans - total_deposits):,.0f} RUB")

    # Создаем калькулятор
    repricing_buckets = ['0-1m', '1-3m', '3-6m', '6-12m', '1-2y', '2-3y', '3-5y', '5-7y', '7-10y', '10y+']

    calculator = DynamicBalanceIRRCalculator(
        calculation_date=calc_date,
        repricing_buckets=repricing_buckets,
        elasticity_params=create_baseline_elasticity_config()
    )

    # Шок ставок
    rate_shocks = {'RUB': 200.0}  # +200 б.п.

    risk_params = {
        'liquidity_buckets': ['0-30d', '30-90d', '90-180d', '180-365d', '1-2y', '2y+']
    }

    # Расчет
    print("\nВыполняется расчет динамического процентного риска...")
    result = calculator.calculate_dynamic_irr(
        instruments,
        rate_shocks,
        risk_params
    )

    # Результаты
    print("\n" + "=" * 80)
    print("РЕЗУЛЬТАТЫ: Изменение объемов депозитов")
    print("=" * 80)

    elasticity_summary = result['dynamic']['elasticity_summary']
    print("\nИзменения по сегментам:")
    print(elasticity_summary.to_string(index=False))

    # Сравнение NII Impact
    print("\n" + "=" * 80)
    print("РЕЗУЛЬТАТЫ: Влияние на Net Interest Income (NII)")
    print("=" * 80)

    static_nii = result['static']['sensitivity']['RUB']['nii_impact_1y']
    dynamic_nii = result['dynamic']['sensitivity']['RUB']['nii_impact_1y']
    nii_diff = result['comparison']['nii_impact_difference']['RUB']

    print(f"\nСтатический баланс (без эластичности):")
    print(f"  NII Impact (1 год): {float(static_nii):,.0f} RUB")

    print(f"\nДинамический баланс (с эластичностью):")
    print(f"  NII Impact (1 год): {float(dynamic_nii):,.0f} RUB")

    print(f"\nРазница:")
    print(f"  {float(nii_diff):,.0f} RUB ({float(nii_diff/static_nii*100):.1f}%)")

    # Общее изменение объема депозитов
    total_volume_change = sum(
        vc.volume_change for vc in result['dynamic']['volume_changes']
    )
    volume_change_pct = float(total_volume_change / total_deposits * 100)

    print(f"\nОбщее изменение объема депозитов:")
    print(f"  {float(total_volume_change):,.0f} RUB ({volume_change_pct:.2f}%)")

    # Экспорт в Excel
    output_path = "output/elasticity_baseline_scenario.xlsx"
    export_dynamic_irr_to_excel(result, output_path, "Baseline: +200bp")
    print(f"\nРезультаты экспортированы в: {output_path}")

    return result


def compare_elasticity_configurations():
    """
    Сравнение различных конфигураций эластичности.
    """
    print("\n" + "=" * 80)
    print("СРАВНЕНИЕ КОНФИГУРАЦИЙ ЭЛАСТИЧНОСТИ")
    print("=" * 80)

    instruments = create_sample_portfolio()
    calc_date = date(2025, 1, 1)
    repricing_buckets = ['0-1m', '1-3m', '3-6m', '6-12m', '1-2y', '2-3y', '3-5y', '5-7y', '7-10y', '10y+']
    rate_shocks = {'RUB': 200.0}
    risk_params = {'liquidity_buckets': ['0-30d', '30-90d', '90-180d', '180-365d', '1-2y', '2y+']}

    configs = {
        'Оптимистичная': create_optimistic_elasticity_config(),
        'Базовая': create_baseline_elasticity_config(),
        'Консервативная': create_conservative_elasticity_config()
    }

    results_summary = []

    for config_name, elasticity_config in configs.items():
        print(f"\nРасчет для конфигурации: {config_name}")

        calculator = DynamicBalanceIRRCalculator(
            calculation_date=calc_date,
            repricing_buckets=repricing_buckets,
            elasticity_params=elasticity_config
        )

        result = calculator.calculate_dynamic_irr(
            instruments,
            rate_shocks,
            risk_params
        )

        # Собираем результаты
        total_volume_change = sum(
            vc.volume_change for vc in result['dynamic']['volume_changes']
        )

        nii_diff = result['comparison']['nii_impact_difference']['RUB']

        results_summary.append({
            'Конфигурация': config_name,
            'Изменение объема депозитов (RUB)': float(total_volume_change),
            'Изменение NII Impact (RUB)': float(nii_diff),
            'Количество изменений': len(result['dynamic']['volume_changes'])
        })

    # Выводим сводку
    print("\n" + "=" * 80)
    print("СВОДКА ПО КОНФИГУРАЦИЯМ")
    print("=" * 80)

    summary_df = pd.DataFrame(results_summary)
    print("\n" + summary_df.to_string(index=False))

    print("\nИнтерпретация:")
    print("- Оптимистичная: предполагает слабую реакцию клиентов (базовый сценарий)")
    print("- Базовая: сбалансированная реакция (рекомендуется)")
    print("- Консервативная: сильная реакция клиентов (стресс-тест)")


def analyze_multiple_rate_shocks():
    """
    Анализ различных шоков ставок.
    """
    print("\n" + "=" * 80)
    print("АНАЛИЗ РАЗЛИЧНЫХ ШОКОВ СТАВОК")
    print("=" * 80)

    instruments = create_sample_portfolio()
    calc_date = date(2025, 1, 1)
    repricing_buckets = ['0-1m', '1-3m', '3-6m', '6-12m', '1-2y', '2-3y', '3-5y', '5-7y', '7-10y', '10y+']

    calculator = DynamicBalanceIRRCalculator(
        calculation_date=calc_date,
        repricing_buckets=repricing_buckets,
        elasticity_params=create_baseline_elasticity_config()
    )

    scenarios = {
        'Малый рост (+50 б.п.)': {'RUB': 50.0},
        'Умеренный рост (+100 б.п.)': {'RUB': 100.0},
        'Сильный рост (+200 б.п.)': {'RUB': 200.0},
        'Экстремальный рост (+300 б.п.)': {'RUB': 300.0},
        'Снижение (-100 б.п.)': {'RUB': -100.0}
    }

    risk_params = {'liquidity_buckets': ['0-30d', '30-90d', '90-180d', '180-365d', '1-2y', '2y+']}

    print("\nВыполняется расчет для нескольких сценариев...")
    results = calculator.calculate_multiple_scenarios(
        instruments,
        scenarios,
        risk_params
    )

    # Сводка
    scenario_summary = []

    for scenario_name, result in results.items():
        total_volume_change = sum(
            vc.volume_change for vc in result['dynamic']['volume_changes']
        ) if result['dynamic']['volume_changes'] else Decimal(0)

        nii_diff = result['comparison']['nii_impact_difference'].get('RUB', Decimal(0))

        scenario_summary.append({
            'Сценарий': scenario_name,
            'Изменение объема (млн RUB)': float(total_volume_change) / 1_000_000,
            'Изменение NII (млн RUB)': float(nii_diff) / 1_000_000
        })

    print("\n" + "=" * 80)
    print("СВОДКА ПО СЦЕНАРИЯМ")
    print("=" * 80)

    summary_df = pd.DataFrame(scenario_summary)
    print("\n" + summary_df.to_string(index=False))


def main():
    """
    Главная функция - запускает все примеры.
    """
    print("\n" + "=" * 80)
    print("МОДЕЛЬ ЭЛАСТИЧНОСТИ ДЕПОЗИТОВ ДЛЯ ПРОЦЕНТНОГО РИСКА")
    print("Пример расчета динамического баланса")
    print("=" * 80)

    # 1. Базовый сценарий
    analyze_baseline_scenario()

    # 2. Сравнение конфигураций
    compare_elasticity_configurations()

    # 3. Различные шоки ставок
    analyze_multiple_rate_shocks()

    print("\n" + "=" * 80)
    print("АНАЛИЗ ЗАВЕРШЕН")
    print("=" * 80)
    print("\nВсе результаты сохранены в директории 'output/'")


if __name__ == "__main__":
    main()
