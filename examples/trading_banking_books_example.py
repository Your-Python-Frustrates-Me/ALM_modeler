"""
Пример использования разделения на торговую и банковскую книги

Этот скрипт демонстрирует:
1. Как определяется книга инструмента по торговому портфелю
2. Как рассчитать метрики процентного риска отдельно для торговой и банковской книг
3. Как сравнить результаты между книгами
"""

import logging
from pathlib import Path
from datetime import date
from decimal import Decimal

from alm_calculator.data.loaders.csv_loader import load_mock_data
from alm_calculator.risks.interest_rate.currency_interest_rate_gaps import CurrencyInterestRateGapCalculator
from alm_calculator.core.base_instrument import BookType

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def main():
    """Основная функция примера"""

    logger.info("="*80)
    logger.info("Trading and Banking Books Analysis Example")
    logger.info("="*80)

    # 1. Загрузка данных
    logger.info("\n1. Loading mock data...")
    data_dir = Path(__file__).parent.parent / 'data' / 'mock_data'

    if not data_dir.exists():
        logger.error(f"Data directory not found: {data_dir}")
        logger.info("Please run the mock data generator first:")
        logger.info("  python -m alm_calculator.data_generation.mock_data_generator")
        return

    instruments = load_mock_data(data_dir)
    logger.info(f"Loaded {len(instruments)} instruments")

    # 2. Анализ распределения по книгам
    logger.info("\n2. Analyzing book distribution...")
    trading_count = 0
    banking_count = 0

    for inst in instruments:
        book = inst.get_book()
        if book == BookType.TRADING:
            trading_count += 1
        else:
            banking_count += 1

    logger.info(f"Trading book instruments: {trading_count} ({trading_count/len(instruments)*100:.1f}%)")
    logger.info(f"Banking book instruments: {banking_count} ({banking_count/len(instruments)*100:.1f}%)")

    # 3. Примеры инструментов из каждой книги
    logger.info("\n3. Sample instruments from each book:")

    # Торговая книга
    trading_instruments = [inst for inst in instruments if inst.get_book() == BookType.TRADING][:3]
    logger.info("\nTrading book samples:")
    for inst in trading_instruments:
        logger.info(f"  - {inst.instrument_id}: {inst.instrument_type.value}, "
                   f"portfolio={inst.trading_portfolio}, amount={inst.amount}")

    # Банковская книга
    banking_instruments = [inst for inst in instruments if inst.get_book() == BookType.BANKING][:3]
    logger.info("\nBanking book samples:")
    for inst in banking_instruments:
        logger.info(f"  - {inst.instrument_id}: {inst.instrument_type.value}, "
                   f"portfolio={inst.trading_portfolio}, amount={inst.amount}")

    # 4. Расчет процентных гэпов отдельно по книгам
    logger.info("\n4. Calculating interest rate gaps by books...")

    calculation_date = date(2024, 12, 31)
    repricing_buckets = ['0-1m', '1-3m', '3-6m', '6-12m', '1-2y', '2-3y', '3-5y', '5-7y', '7-10y', '10y+']

    calculator = CurrencyInterestRateGapCalculator(
        calculation_date=calculation_date,
        repricing_buckets=repricing_buckets,
        target_currencies=['RUB', 'USD']
    )

    # Параметры расчета
    risk_params = {
        'liquidity_buckets': ['0-30d', '30-90d', '90-180d', '180-365d', '1-2y', '2y+'],
        'calculation_date': calculation_date
    }

    # Расчет для всех книг вместе
    logger.info("\nCalculating gaps for ALL books combined...")
    all_books_gaps = calculator.calculate(instruments, risk_params, book_filter=None)

    # Расчет отдельно для торговой книги
    logger.info("\nCalculating gaps for TRADING book...")
    trading_gaps = calculator.calculate(instruments, risk_params, book_filter=BookType.TRADING)

    # Расчет отдельно для банковской книги
    logger.info("\nCalculating gaps for BANKING book...")
    banking_gaps = calculator.calculate(instruments, risk_params, book_filter=BookType.BANKING)

    # 5. Сравнение результатов
    logger.info("\n5. Comparing results across books:")
    logger.info("="*80)

    for currency in ['RUB', 'USD']:
        if currency not in all_books_gaps:
            continue

        logger.info(f"\nCurrency: {currency}")
        logger.info("-" * 80)

        # Все книги
        all_total_gap = all_books_gaps[currency]['gap'].sum()
        logger.info(f"  All books - Total gap: {all_total_gap:,.0f}")

        # Торговая книга
        if currency in trading_gaps:
            trading_total_gap = trading_gaps[currency]['gap'].sum()
            logger.info(f"  Trading book - Total gap: {trading_total_gap:,.0f}")
        else:
            logger.info(f"  Trading book - No instruments in this currency")

        # Банковская книга
        if currency in banking_gaps:
            banking_total_gap = banking_gaps[currency]['gap'].sum()
            logger.info(f"  Banking book - Total gap: {banking_total_gap:,.0f}")
        else:
            logger.info(f"  Banking book - No instruments in this currency")

    # 6. Детальный анализ по временным бакетам для RUB
    if 'RUB' in all_books_gaps:
        logger.info("\n6. Detailed gap analysis for RUB by time buckets:")
        logger.info("="*80)
        logger.info(f"{'Bucket':<12} {'All Books':>15} {'Trading':>15} {'Banking':>15}")
        logger.info("-" * 80)

        all_df = all_books_gaps['RUB']
        trading_df = trading_gaps.get('RUB')
        banking_df = banking_gaps.get('RUB')

        for bucket in repricing_buckets:
            all_gap = all_df[all_df['bucket'] == bucket]['gap'].values[0] if len(all_df[all_df['bucket'] == bucket]) > 0 else 0
            trading_gap = trading_df[trading_df['bucket'] == bucket]['gap'].values[0] if trading_df is not None and len(trading_df[trading_df['bucket'] == bucket]) > 0 else 0
            banking_gap = banking_df[banking_df['bucket'] == bucket]['gap'].values[0] if banking_df is not None and len(banking_df[banking_df['bucket'] == bucket]) > 0 else 0

            logger.info(f"{bucket:<12} {all_gap:>15,.0f} {trading_gap:>15,.0f} {banking_gap:>15,.0f}")

    # 7. Расчет чувствительности
    logger.info("\n7. Calculating sensitivity to rate shocks...")
    logger.info("="*80)

    # Для всех книг
    all_sensitivity = calculator.calculate_sensitivity(all_books_gaps, rate_shock_bps=100)

    # Для торговой книги
    trading_sensitivity = calculator.calculate_sensitivity(trading_gaps, rate_shock_bps=100)

    # Для банковской книги
    banking_sensitivity = calculator.calculate_sensitivity(banking_gaps, rate_shock_bps=100)

    for currency in ['RUB', 'USD']:
        if currency not in all_sensitivity:
            continue

        logger.info(f"\n{currency} - Impact of +100 bps parallel shift:")
        logger.info("-" * 80)

        # Все книги
        logger.info(f"  All books:")
        logger.info(f"    NII impact (1Y): {all_sensitivity[currency]['nii_impact_1y']:,.0f}")
        logger.info(f"    EVE impact: {all_sensitivity[currency]['eve_impact']:,.0f}")

        # Торговая книга
        if currency in trading_sensitivity:
            logger.info(f"  Trading book:")
            logger.info(f"    NII impact (1Y): {trading_sensitivity[currency]['nii_impact_1y']:,.0f}")
            logger.info(f"    EVE impact: {trading_sensitivity[currency]['eve_impact']:,.0f}")

        # Банковская книга
        if currency in banking_sensitivity:
            logger.info(f"  Banking book:")
            logger.info(f"    NII impact (1Y): {banking_sensitivity[currency]['nii_impact_1y']:,.0f}")
            logger.info(f"    EVE impact: {banking_sensitivity[currency]['eve_impact']:,.0f}")

    logger.info("\n" + "="*80)
    logger.info("Analysis completed successfully!")
    logger.info("="*80)


if __name__ == '__main__':
    main()
