"""
Пример использования факторного анализа для декомпозиции изменений в метриках риска

Демонстрирует:
1. Симуляцию двух периодов: t-1 (базовый) и t (текущий)
2. Декомпозицию изменений на эффект старения и эффект новых сделок
3. Анализ индивидуального влияния каждого нового продукта
4. Применение к двум метрикам: горизонт выживания и процентный риск
"""
from datetime import date, timedelta
from decimal import Decimal
import pandas as pd
import logging
from pathlib import Path
from typing import List
from copy import deepcopy

# Импорты из проекта
from alm_calculator.data.loaders.csv_loader import CSVDataLoader
from alm_calculator.core.base_instrument import BaseInstrument
from alm_calculator.risks.factor_analysis import FactorAnalyzer, export_to_excel
from alm_calculator.risks.liquidity.currency_liquidity_gaps import CurrencyLiquidityGapCalculator
from alm_calculator.risks.interest_rate.currency_interest_rate_gaps import CurrencyInterestRateGapCalculator

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def simulate_portfolio_changes(
    base_instruments: List[BaseInstrument],
    base_date: date,
    comparison_date: date,
    new_instruments_pct: float = 0.05
) -> List[BaseInstrument]:
    """
    Симулирует изменения в портфеле между двумя датами.

    Args:
        base_instruments: Базовый портфель на дату t-1
        base_date: Базовая дата (t-1)
        comparison_date: Дата сравнения (t)
        new_instruments_pct: Процент новых инструментов (от размера базового портфеля)

    Returns:
        Список инструментов на дату сравнения
    """
    logger.info(f"Simulating portfolio changes from {base_date} to {comparison_date}")

    # 1. "Состариваем" существующие инструменты
    # Симулируем, что некоторые инструменты погашены
    aged_instruments = []
    matured_count = 0

    for inst in base_instruments:
        # Создаем копию
        aged_inst = deepcopy(inst)

        # Обновляем as_of_date
        aged_inst.as_of_date = comparison_date

        # Проверяем, не погашен ли инструмент
        if inst.maturity_date and inst.maturity_date <= comparison_date:
            matured_count += 1
            continue  # Инструмент погашен, не включаем

        aged_instruments.append(aged_inst)

    logger.info(f"  Existing instruments: {len(base_instruments)} -> {len(aged_instruments)} (matured: {matured_count})")

    # 2. Добавляем "новые" инструменты
    # Для симуляции берем случайные инструменты из базового портфеля и изменяем их ID
    num_new_instruments = int(len(base_instruments) * new_instruments_pct)
    new_instruments = []

    for i in range(num_new_instruments):
        # Берем случайный инструмент из базового портфеля
        source_inst = base_instruments[i % len(base_instruments)]

        # Создаем копию
        new_inst = deepcopy(source_inst)

        # Изменяем атрибуты
        new_inst.instrument_id = f"NEW_{source_inst.instrument_id}_{i}"
        new_inst.start_date = comparison_date - timedelta(days=7)
        new_inst.as_of_date = comparison_date

        # Если есть maturity_date, сдвигаем вперед
        if new_inst.maturity_date:
            days_to_maturity = (source_inst.maturity_date - base_date).days
            new_inst.maturity_date = comparison_date + timedelta(days=max(days_to_maturity, 30))

        new_instruments.append(new_inst)

    logger.info(f"  New instruments added: {len(new_instruments)}")

    # 3. Объединяем
    comparison_instruments = aged_instruments + new_instruments

    logger.info(f"  Total instruments at t: {len(comparison_instruments)}")

    return comparison_instruments


def calculate_simple_survival_horizon(
    instruments: List[BaseInstrument],
    calc_date: date
) -> int:
    """
    Упрощенный расчет горизонта выживания (для демонстрации).

    Формула:
    - Сумма активов (cash flows) / (ежедневный отток пассивов)
    - Упрощение: считаем все активы как доступные, все пассивы как оттоки

    Args:
        instruments: Список инструментов
        calc_date: Дата расчета

    Returns:
        Горизонт выживания в днях
    """
    total_assets = Decimal(0)
    total_liabilities = Decimal(0)
    daily_liability_outflow = Decimal(0)

    for inst in instruments:
        amount = inst.amount

        if amount > 0:
            # Актив
            total_assets += amount
        else:
            # Пассив
            total_liabilities += abs(amount)

            # Предполагаем, что пассивы оттекают равномерно до maturity
            if inst.maturity_date:
                days_to_maturity = (inst.maturity_date - calc_date).days
                if days_to_maturity > 0:
                    daily_outflow = abs(amount) / days_to_maturity
                    daily_liability_outflow += daily_outflow
            else:
                # Бессрочный пассив - предполагаем 1% в день
                daily_liability_outflow += abs(amount) * Decimal('0.01')

    # Горизонт выживания = активы / дневной отток
    if daily_liability_outflow > 0:
        survival_days = int(total_assets / daily_liability_outflow)
    else:
        survival_days = 999  # Нет оттоков - очень долгий горизонт

    logger.info(
        f"Survival horizon calculation: "
        f"assets={total_assets:,.0f}, "
        f"liabilities={total_liabilities:,.0f}, "
        f"daily_outflow={daily_liability_outflow:,.0f}, "
        f"horizon={survival_days} days"
    )

    return min(survival_days, 365)  # Ограничиваем 365 днями


def calculate_simple_interest_rate_risk(
    instruments: List[BaseInstrument],
    calc_date: date
) -> Decimal:
    """
    Упрощенный расчет процентного риска (для демонстрации).

    Формула: GAP = (Rate-Sensitive Assets - Rate-Sensitive Liabilities)
    Инструменты с переоценкой в течение года считаются rate-sensitive

    Args:
        instruments: Список инструментов
        calc_date: Дата расчета

    Returns:
        Процентный гэп
    """
    rsa = Decimal(0)  # Rate-Sensitive Assets
    rsl = Decimal(0)  # Rate-Sensitive Liabilities

    for inst in instruments:
        # Определяем, является ли инструмент rate-sensitive
        # Считаем rate-sensitive, если переоценка в течение 1 года
        is_rate_sensitive = False

        if inst.maturity_date:
            days_to_maturity = (inst.maturity_date - calc_date).days
            if days_to_maturity <= 365:
                is_rate_sensitive = True
        elif inst.interest_rate and inst.interest_rate > 0:
            # Инструмент с процентной ставкой без maturity - считаем rate-sensitive
            is_rate_sensitive = True

        if is_rate_sensitive:
            if inst.amount > 0:
                rsa += inst.amount
            else:
                rsl += abs(inst.amount)

    gap = rsa - rsl

    logger.info(
        f"Interest rate gap calculation: "
        f"RSA={rsa:,.0f}, RSL={rsl:,.0f}, GAP={gap:,.0f}"
    )

    return gap


def main():
    """Основная функция примера"""

    # 1. Загружаем базовые данные
    logger.info("=" * 80)
    logger.info("FACTOR ANALYSIS EXAMPLE")
    logger.info("=" * 80)

    data_dir = Path(__file__).parent.parent / 'data' / 'mock_data'
    loader = CSVDataLoader(data_dir)

    logger.info("\n1. Loading base portfolio data...")
    base_instruments = loader.load_all_instruments()

    # Ограничим размер для быстрого примера
    base_instruments = base_instruments[:10000]

    logger.info(f"   Loaded {len(base_instruments)} instruments for base portfolio")

    # 2. Определяем даты
    base_date = date(2024, 12, 31)
    comparison_date = date(2025, 1, 7)  # Неделя спустя

    logger.info(f"\n2. Simulation dates:")
    logger.info(f"   Base date (t-1): {base_date}")
    logger.info(f"   Comparison date (t): {comparison_date}")
    logger.info(f"   Days elapsed: {(comparison_date - base_date).days}")

    # 3. Симулируем изменения в портфеле
    logger.info("\n3. Simulating portfolio changes...")
    comparison_instruments = simulate_portfolio_changes(
        base_instruments,
        base_date,
        comparison_date,
        new_instruments_pct=0.05  # 5% новых инструментов
    )

    # 4. Факторный анализ для горизонта выживания
    logger.info("\n" + "=" * 80)
    logger.info("FACTOR ANALYSIS #1: SURVIVAL HORIZON")
    logger.info("=" * 80)

    analyzer_sh = FactorAnalyzer(base_date, comparison_date)

    sh_results = analyzer_sh.analyze_individual_impact(
        base_instruments,
        comparison_instruments,
        calculate_simple_survival_horizon,
        metric_name="Survival Horizon (days)",
        top_n=10  # Топ-10 продуктов по влиянию
    )

    # Выводим результаты
    logger.info(f"\nResults:")
    logger.info(f"  Base horizon (t-1): {sh_results['metric_base']} days")
    logger.info(f"  Aged positions horizon (t): {sh_results['metric_aged']} days")
    logger.info(f"  Full portfolio horizon (t): {sh_results['metric_full']} days")
    logger.info(f"\nDecomposition:")
    logger.info(f"  Total change: {sh_results['total_change']} days")
    logger.info(f"    - Aging effect: {sh_results['aging_effect']} days")
    logger.info(f"    - New deals effect: {sh_results['new_deals_effect']} days")
    logger.info(f"\nProducts:")
    logger.info(f"  Existing: {sh_results['existing_products_count']}")
    logger.info(f"  New: {sh_results['new_products_count']}")

    # Топ продуктов
    if sh_results['new_products_breakdown']:
        logger.info(f"\nTop 10 new products by impact on survival horizon:")
        for i, product in enumerate(sh_results['new_products_breakdown'][:10], 1):
            logger.info(
                f"  {i}. {product['product_id']}: "
                f"{product['impact']:+.0f} days "
                f"(type: {product['product_type']}, "
                f"amount: {product['amount']:,.0f} {product['currency']})"
            )

    # 5. Факторный анализ для процентного риска
    logger.info("\n" + "=" * 80)
    logger.info("FACTOR ANALYSIS #2: INTEREST RATE RISK (GAP)")
    logger.info("=" * 80)

    analyzer_irr = FactorAnalyzer(base_date, comparison_date)

    irr_results = analyzer_irr.analyze_individual_impact(
        base_instruments,
        comparison_instruments,
        calculate_simple_interest_rate_risk,
        metric_name="Interest Rate Gap",
        top_n=10
    )

    # Выводим результаты
    logger.info(f"\nResults:")
    logger.info(f"  Base gap (t-1): {irr_results['metric_base']:,.0f}")
    logger.info(f"  Aged positions gap (t): {irr_results['metric_aged']:,.0f}")
    logger.info(f"  Full portfolio gap (t): {irr_results['metric_full']:,.0f}")
    logger.info(f"\nDecomposition:")
    logger.info(f"  Total change: {irr_results['total_change']:,.0f}")
    logger.info(f"    - Aging effect: {irr_results['aging_effect']:,.0f}")
    logger.info(f"    - New deals effect: {irr_results['new_deals_effect']:,.0f}")

    # Топ продуктов
    if irr_results['new_products_breakdown']:
        logger.info(f"\nTop 10 new products by impact on interest rate gap:")
        for i, product in enumerate(irr_results['new_products_breakdown'][:10], 1):
            logger.info(
                f"  {i}. {product['product_id']}: "
                f"{product['impact']:+,.0f} "
                f"(type: {product['product_type']}, "
                f"amount: {product['amount']:,.0f} {product['currency']})"
            )

    # 6. Экспорт результатов
    logger.info("\n" + "=" * 80)
    logger.info("EXPORTING RESULTS")
    logger.info("=" * 80)

    output_dir = Path(__file__).parent.parent / 'output'
    output_dir.mkdir(exist_ok=True)

    # Экспорт горизонта выживания
    sh_output_path = output_dir / 'factor_analysis_survival_horizon.xlsx'
    export_to_excel(sh_results, str(sh_output_path))
    logger.info(f"  Survival horizon analysis exported to: {sh_output_path}")

    # Экспорт процентного риска
    irr_output_path = output_dir / 'factor_analysis_interest_rate_gap.xlsx'
    export_to_excel(irr_results, str(irr_output_path))
    logger.info(f"  Interest rate gap analysis exported to: {irr_output_path}")

    logger.info("\n" + "=" * 80)
    logger.info("EXAMPLE COMPLETED SUCCESSFULLY")
    logger.info("=" * 80)


if __name__ == '__main__':
    main()
