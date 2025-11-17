"""
Complete ALM Risk Calculator Workflow Example

Demonstrates:
1. Loading mock balance sheet data from CSV
2. Calculating baseline risks
3. Running stress scenarios
4. Comparing results
"""

import logging
from datetime import date
from pathlib import Path
import pandas as pd

# ALM Calculator imports
from alm_calculator.data.loaders.csv_loader import load_mock_data, CSVDataLoader
from alm_calculator.engine.scenario_calculator import (
    ScenarioCalculator,
    create_baseline_scenario,
    create_interest_rate_shock_scenario,
    create_deposit_run_scenario,
    create_combined_stress_scenario
)


def setup_logging():
    """Setup logging configuration"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


def main():
    """
    Main workflow demonstration
    """
    setup_logging()
    logger = logging.getLogger(__name__)

    logger.info("="*80)
    logger.info("ALM RISK CALCULATOR - FULL WORKFLOW EXAMPLE")
    logger.info("="*80)

    # ====================================================================
    # STEP 1: Load Balance Sheet Data
    # ====================================================================
    logger.info("\n" + "="*80)
    logger.info("STEP 1: Loading Balance Sheet Data")
    logger.info("="*80)

    # Option 1: Use default path
    instruments = load_mock_data()

    # Option 2: Specify custom path
    # data_dir = Path(__file__).parent.parent / 'data' / 'mock_data'
    # instruments = load_mock_data(data_dir)

    logger.info(f"✓ Loaded {len(instruments)} instruments from CSV files")

    # Get portfolio summary
    loader = CSVDataLoader(Path(__file__).parent.parent / 'data' / 'mock_data')
    portfolio_summary = loader.get_portfolio_summary(instruments)

    logger.info("\nPortfolio Summary:")
    logger.info("\n" + portfolio_summary.to_string(index=False))

    # ====================================================================
    # STEP 2: Initialize Scenario Calculator
    # ====================================================================
    logger.info("\n" + "="*80)
    logger.info("STEP 2: Initializing Scenario Calculator")
    logger.info("="*80)

    calculator = ScenarioCalculator(instruments)

    logger.info(f"✓ Calculator initialized with {len(instruments)} instruments")

    # ====================================================================
    # STEP 3: Define Scenarios
    # ====================================================================
    logger.info("\n" + "="*80)
    logger.info("STEP 3: Defining Stress Scenarios")
    logger.info("="*80)

    calculation_date = date(2024, 12, 31)

    scenarios = [
        create_baseline_scenario(calculation_date),
        create_interest_rate_shock_scenario(calculation_date, shock_bps=200),
        create_deposit_run_scenario(calculation_date, runoff_pct=20),
        create_combined_stress_scenario(calculation_date),
    ]

    logger.info(f"✓ Defined {len(scenarios)} scenarios:")
    for scenario in scenarios:
        logger.info(f"  - {scenario.scenario_name}")

    # ====================================================================
    # STEP 4: Calculate Baseline Scenario
    # ====================================================================
    logger.info("\n" + "="*80)
    logger.info("STEP 4: Calculating Baseline Scenario")
    logger.info("="*80)

    baseline_scenario = scenarios[0]
    baseline_result = calculator.calculate_scenario(baseline_scenario)

    logger.info(f"\n✓ Baseline Results:")
    logger.info(f"  Total Assets:      {float(baseline_result.total_assets):>20,.0f}")
    logger.info(f"  Total Liabilities: {float(baseline_result.total_liabilities):>20,.0f}")
    logger.info(f"  Net Position:      {float(baseline_result.net_position):>20,.0f}")

    if baseline_result.repricing_gap_total:
        logger.info(f"  Repricing Gap:     {float(baseline_result.repricing_gap_total):>20,.0f}")

    if baseline_result.dv01_total:
        logger.info(f"  DV01 (1bp shock):  {float(baseline_result.dv01_total):>20,.0f}")

    if baseline_result.survival_horizon_days:
        logger.info(f"\n  Survival Horizons by Currency:")
        for currency, days in baseline_result.survival_horizon_days.items():
            logger.info(f"    {currency}: {days} days")

    # Liquidity Gaps
    if baseline_result.liquidity_gaps is not None:
        logger.info(f"\n  Liquidity Gaps (RUB, first 5 buckets):")
        rub_gaps = baseline_result.liquidity_gaps[
            baseline_result.liquidity_gaps['currency'] == 'RUB'
        ].head(5)
        for _, row in rub_gaps.iterrows():
            logger.info(f"    {row['bucket']:>12}: {row['gap']:>18,.0f}")

    # Interest Rate Gaps
    if baseline_result.interest_rate_gaps is not None:
        logger.info(f"\n  Interest Rate Gaps (RUB, first 5 buckets):")
        rub_irr_gaps = baseline_result.interest_rate_gaps[
            baseline_result.interest_rate_gaps['currency'] == 'RUB'
        ].head(5)
        for _, row in rub_irr_gaps.iterrows():
            logger.info(f"    {row['bucket']:>12}: {row['repricing_gap']:>18,.0f}")

    # FX Positions
    if baseline_result.fx_positions:
        logger.info(f"\n  FX Positions:")
        for currency, position in baseline_result.fx_positions.items():
            logger.info(f"    {currency}: {float(position):>20,.0f}")

    # ====================================================================
    # STEP 5: Calculate Stress Scenarios
    # ====================================================================
    logger.info("\n" + "="*80)
    logger.info("STEP 5: Calculating Stress Scenarios")
    logger.info("="*80)

    stress_results = {}

    for scenario in scenarios[1:]:  # Skip baseline
        logger.info(f"\nCalculating: {scenario.scenario_name}")
        result = calculator.calculate_scenario(scenario)
        stress_results[scenario.scenario_name] = result

        logger.info(f"  ✓ {scenario.scenario_name} completed")
        logger.info(f"    Net Position: {float(result.net_position):>18,.0f}")

        if result.survival_horizon_days:
            for currency, days in result.survival_horizon_days.items():
                if currency == 'RUB':
                    logger.info(f"    Survival Horizon (RUB): {days} days")

    # ====================================================================
    # STEP 6: Compare Scenarios
    # ====================================================================
    logger.info("\n" + "="*80)
    logger.info("STEP 6: Scenario Comparison")
    logger.info("="*80)

    comparison = calculator.compare_scenarios(scenarios)

    logger.info("\nScenario Comparison Table:")
    logger.info("\n" + comparison[
        ['scenario_name', 'total_assets', 'total_liabilities', 'net_position']
    ].to_string(index=False))

    # Detailed comparison for specific metrics
    if 'dv01_total' in comparison.columns:
        logger.info("\nDV01 (Interest Rate Sensitivity) Comparison:")
        dv01_comparison = comparison[['scenario_name', 'dv01_total']].copy()
        dv01_comparison = dv01_comparison.dropna()
        if not dv01_comparison.empty:
            logger.info("\n" + dv01_comparison.to_string(index=False))

    # ====================================================================
    # STEP 7: Export Results (Optional)
    # ====================================================================
    logger.info("\n" + "="*80)
    logger.info("STEP 7: Exporting Results")
    logger.info("="*80)

    output_dir = Path(__file__).parent.parent / 'output'
    output_dir.mkdir(exist_ok=True)

    # Export scenario comparison
    comparison_path = output_dir / 'scenario_comparison.csv'
    comparison.to_csv(comparison_path, index=False)
    logger.info(f"✓ Exported scenario comparison to: {comparison_path}")

    # Export baseline liquidity gaps
    if baseline_result.liquidity_gaps is not None:
        liq_gaps_path = output_dir / 'baseline_liquidity_gaps.csv'
        baseline_result.liquidity_gaps.to_csv(liq_gaps_path, index=False)
        logger.info(f"✓ Exported baseline liquidity gaps to: {liq_gaps_path}")

    # Export baseline IRR gaps
    if baseline_result.interest_rate_gaps is not None:
        irr_gaps_path = output_dir / 'baseline_interest_rate_gaps.csv'
        baseline_result.interest_rate_gaps.to_csv(irr_gaps_path, index=False)
        logger.info(f"✓ Exported baseline interest rate gaps to: {irr_gaps_path}")

    # ====================================================================
    # SUMMARY
    # ====================================================================
    logger.info("\n" + "="*80)
    logger.info("WORKFLOW COMPLETED SUCCESSFULLY!")
    logger.info("="*80)

    logger.info("\nKey Findings:")
    logger.info(f"  • Portfolio size: {len(instruments):,} positions")
    logger.info(f"  • Total assets: {float(baseline_result.total_assets):,.0f}")
    logger.info(f"  • Total liabilities: {float(baseline_result.total_liabilities):,.0f}")
    logger.info(f"  • Net position: {float(baseline_result.net_position):,.0f}")
    logger.info(f"  • Scenarios analyzed: {len(scenarios)}")

    if baseline_result.survival_horizon_days:
        rub_survival = baseline_result.survival_horizon_days.get('RUB', 0)
        logger.info(f"  • Survival horizon (RUB): {rub_survival} days (baseline)")

    logger.info("\nNext Steps:")
    logger.info("  1. Review exported CSV files in ./output/ directory")
    logger.info("  2. Adjust scenario parameters for custom stress tests")
    logger.info("  3. Add behavioral assumptions for instrument modeling")
    logger.info("  4. Integrate with your data warehouse for real-time analysis")

    logger.info("\n" + "="*80)


if __name__ == '__main__':
    main()
