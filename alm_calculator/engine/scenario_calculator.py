"""
Scenario Calculator for ALM Risk Analysis

Applies stress scenarios to balance sheet positions and calculates risk metrics.
"""

import pandas as pd
import numpy as np
import logging
from typing import List, Dict, Optional
from datetime import date, timedelta
from decimal import Decimal
from dataclasses import dataclass, field

from alm_calculator.core.base_instrument import BaseInstrument, RiskContribution

logger = logging.getLogger(__name__)


@dataclass
class ScenarioParameters:
    """
    Параметры стресс-сценария.

    Примеры сценариев:
    - Baseline: текущая ситуация без стресса
    - Interest Rate Shock: +200 б.п. к ставкам
    - FX Shock: девальвация рубля на 30%
    - Deposit Run: отток депозитов 20%
    - Combined Stress: комбинация шоков
    """

    scenario_name: str
    calculation_date: date

    # Interest Rate Shocks (в базисных пунктах, 1 б.п. = 0.01%)
    interest_rate_shock_bps: Dict[str, float] = field(default_factory=dict)
    # Ключ - валюта, значение - шок в б.п. (например, {'RUB': 200, 'USD': 100})

    # FX Rate Shocks (изменение курса в %)
    fx_rate_shock_pct: Dict[str, float] = field(default_factory=dict)
    # Ключ - валюта, значение - % изменения (например, {'USD': 30, 'EUR': 25})

    # Deposit Runoff (отток депозитов в %)
    deposit_runoff_pct: float = 0.0
    # Процент моментального оттока депозитов

    # Liquidity Stress Parameters
    haircut_increase: Dict[str, float] = field(default_factory=dict)
    # Увеличение haircut для различных активов

    market_liquidity_stress: bool = False
    # Стресс рыночной ликвидности (сложнее продать активы)

    # Credit Stress
    default_rate_increase: float = 0.0
    # Увеличение дефолтов по кредитам (для будущего)

    # Off-Balance Stress
    credit_line_drawdown_pct: float = 0.0
    # Процент использования незадействованных кредитных линий

    def __repr__(self):
        return f"Scenario('{self.scenario_name}')"


@dataclass
class ScenarioResult:
    """
    Результаты расчета сценария.
    """

    scenario_name: str
    calculation_date: date

    # Liquidity metrics
    liquidity_gaps: Optional[pd.DataFrame] = None
    cumulative_gaps: Optional[pd.DataFrame] = None
    survival_horizon_days: Optional[Dict[str, int]] = None

    # Interest rate risk metrics
    interest_rate_gaps: Optional[pd.DataFrame] = None
    repricing_gap_total: Optional[Decimal] = None
    duration_gap: Optional[float] = None
    dv01_total: Optional[Decimal] = None

    # FX risk metrics
    fx_positions: Optional[Dict[str, Decimal]] = None
    fx_exposure_total: Optional[Decimal] = None

    # Summary metrics
    total_assets: Optional[Decimal] = None
    total_liabilities: Optional[Decimal] = None
    net_position: Optional[Decimal] = None

    # Detailed contributions
    risk_contributions: Optional[List[RiskContribution]] = None

    def to_dict(self) -> Dict:
        """Сериализация результатов"""
        return {
            'scenario_name': self.scenario_name,
            'calculation_date': str(self.calculation_date),
            'survival_horizon_days': self.survival_horizon_days,
            'repricing_gap_total': float(self.repricing_gap_total) if self.repricing_gap_total else None,
            'duration_gap': self.duration_gap,
            'dv01_total': float(self.dv01_total) if self.dv01_total else None,
            'fx_positions': {k: float(v) for k, v in self.fx_positions.items()} if self.fx_positions else None,
            'total_assets': float(self.total_assets) if self.total_assets else None,
            'total_liabilities': float(self.total_liabilities) if self.total_liabilities else None,
            'net_position': float(self.net_position) if self.net_position else None,
        }


class ScenarioCalculator:
    """
    Калькулятор сценариев ALM рисков.

    Workflow:
    1. Загрузить инструменты
    2. Применить stress к инструментам (если требуется)
    3. Рассчитать risk contributions для каждого инструмента
    4. Агрегировать риски на портфельном уровне
    5. Вернуть результаты
    """

    def __init__(
        self,
        instruments: List[BaseInstrument],
        risk_params: Optional[Dict] = None
    ):
        """
        Args:
            instruments: Список всех инструментов портфеля
            risk_params: Параметры для расчета рисков (buckets, curves, etc.)
        """
        self.instruments = instruments
        self.risk_params = risk_params or self._default_risk_params()

        logger.info(f"Initialized ScenarioCalculator with {len(instruments)} instruments")

    def _default_risk_params(self) -> Dict:
        """Параметры по умолчанию для расчета рисков"""
        return {
            'liquidity_buckets': [
                'overnight', '2-7d', '8-14d', '15-30d',
                '30-90d', '90-180d', '180-365d', '1-2y', '2y+'
            ],
            'irr_buckets': [
                '0-1m', '1-3m', '3-6m', '6-12m',
                '1-2y', '2-3y', '3-5y', '5-7y', '7-10y', '10y+'
            ],
            'currencies': ['RUB', 'USD', 'EUR', 'CNY'],
        }

    def calculate_scenario(
        self,
        scenario: ScenarioParameters,
        assumptions: Optional[Dict] = None
    ) -> ScenarioResult:
        """
        Рассчитывает все риски для заданного сценария.

        Args:
            scenario: Параметры сценария
            assumptions: Behavioral assumptions для инструментов

        Returns:
            ScenarioResult с результатами расчета
        """
        logger.info(f"Calculating scenario: {scenario.scenario_name}")

        # 1. Apply scenario stress to instruments (if needed)
        stressed_instruments = self._apply_scenario_stress(self.instruments, scenario)

        # 2. Calculate risk contributions for all instruments
        risk_contributions = self._calculate_risk_contributions(
            stressed_instruments,
            scenario.calculation_date,
            assumptions
        )

        # 3. Aggregate risks
        result = self._aggregate_risks(
            risk_contributions,
            scenario
        )

        logger.info(f"Scenario '{scenario.scenario_name}' calculation completed")

        return result

    def _apply_scenario_stress(
        self,
        instruments: List[BaseInstrument],
        scenario: ScenarioParameters
    ) -> List[BaseInstrument]:
        """
        Применяет стресс-сценарий к инструментам.

        В зависимости от сценария:
        - Меняет процентные ставки
        - Меняет курсы валют (для оценки exposure)
        - Применяет runoff к депозитам
        - И т.д.

        Важно: возвращает копии инструментов, не модифицируя оригиналы.
        """
        logger.debug(f"Applying stress scenario: {scenario.scenario_name}")

        stressed_instruments = []

        for instrument in instruments:
            # Copy instrument (shallow copy достаточно для большинства случаев)
            stressed_inst = instrument.model_copy(deep=True)

            # Apply interest rate shock
            if scenario.interest_rate_shock_bps:
                currency = stressed_inst.currency
                if currency in scenario.interest_rate_shock_bps:
                    shock_bps = scenario.interest_rate_shock_bps[currency]
                    if stressed_inst.interest_rate is not None:
                        stressed_inst.interest_rate += shock_bps / 10000  # Convert bps to decimal

            # Deposit runoff (уменьшаем amount)
            if scenario.deposit_runoff_pct > 0:
                if stressed_inst.instrument_type.value == 'deposit':
                    runoff_multiplier = 1 - (scenario.deposit_runoff_pct / 100)
                    stressed_inst.amount = stressed_inst.amount * Decimal(runoff_multiplier)

            # Credit line drawdown (увеличиваем utilized для off-balance)
            if scenario.credit_line_drawdown_pct > 0:
                if stressed_inst.instrument_type.value == 'off_balance':
                    if hasattr(stressed_inst, 'available_amount') and stressed_inst.available_amount:
                        drawdown = stressed_inst.available_amount * Decimal(scenario.credit_line_drawdown_pct / 100)
                        if hasattr(stressed_inst, 'utilized_amount'):
                            if stressed_inst.utilized_amount:
                                stressed_inst.utilized_amount += drawdown
                            else:
                                stressed_inst.utilized_amount = drawdown
                        stressed_inst.available_amount -= drawdown

            stressed_instruments.append(stressed_inst)

        logger.debug(f"Applied stress to {len(stressed_instruments)} instruments")

        return stressed_instruments

    def _calculate_risk_contributions(
        self,
        instruments: List[BaseInstrument],
        calculation_date: date,
        assumptions: Optional[Dict]
    ) -> List[RiskContribution]:
        """
        Рассчитывает risk contribution для каждого инструмента.
        """
        logger.debug(f"Calculating risk contributions for {len(instruments)} instruments")

        risk_contributions = []

        for i, instrument in enumerate(instruments):
            try:
                # Get instrument-specific assumptions if provided
                inst_assumptions = assumptions.get(instrument.instrument_type.value, {}) if assumptions else {}

                # Calculate contribution
                contribution = instrument.calculate_risk_contribution(
                    calculation_date=calculation_date,
                    risk_params=self.risk_params,
                    assumptions=inst_assumptions
                )

                risk_contributions.append(contribution)

            except Exception as e:
                logger.error(
                    f"Failed to calculate risk contribution for instrument {instrument.instrument_id}: {e}",
                    exc_info=True
                )
                # Continue with other instruments
                continue

            # Progress logging for large portfolios
            if (i + 1) % 50000 == 0:
                logger.info(f"Processed {i + 1}/{len(instruments)} instruments")

        logger.debug(f"Successfully calculated {len(risk_contributions)} risk contributions")

        return risk_contributions

    def _aggregate_risks(
        self,
        risk_contributions: List[RiskContribution],
        scenario: ScenarioParameters
    ) -> ScenarioResult:
        """
        Агрегирует risk contributions на портфельном уровне.
        """
        logger.debug("Aggregating risk contributions")

        result = ScenarioResult(
            scenario_name=scenario.scenario_name,
            calculation_date=scenario.calculation_date,
            risk_contributions=risk_contributions
        )

        # === Liquidity Risk Aggregation ===
        liquidity_gaps_by_currency = {}
        for contrib in risk_contributions:
            for bucket, amount in contrib.cash_flows.items():
                currency = list(contrib.currency_exposure.keys())[0] if contrib.currency_exposure else 'RUB'

                if currency not in liquidity_gaps_by_currency:
                    liquidity_gaps_by_currency[currency] = {}

                if bucket not in liquidity_gaps_by_currency[currency]:
                    liquidity_gaps_by_currency[currency][bucket] = Decimal(0)

                liquidity_gaps_by_currency[currency][bucket] += amount

        # Convert to DataFrame
        if liquidity_gaps_by_currency:
            liq_gaps_data = []
            for currency, buckets in liquidity_gaps_by_currency.items():
                for bucket, amount in buckets.items():
                    liq_gaps_data.append({
                        'currency': currency,
                        'bucket': bucket,
                        'gap': float(amount)
                    })

            result.liquidity_gaps = pd.DataFrame(liq_gaps_data)

            # Calculate cumulative gaps
            result.cumulative_gaps = self._calculate_cumulative_gaps(result.liquidity_gaps)

            # Calculate survival horizon (simplified)
            result.survival_horizon_days = self._calculate_survival_horizon(result.cumulative_gaps)

        # === Interest Rate Risk Aggregation ===
        irr_gaps_by_currency = {}
        duration_contributions = []
        dv01_contributions = []

        for contrib in risk_contributions:
            # Repricing gaps
            if contrib.repricing_date and contrib.repricing_amount:
                currency = list(contrib.currency_exposure.keys())[0] if contrib.currency_exposure else 'RUB'

                if currency not in irr_gaps_by_currency:
                    irr_gaps_by_currency[currency] = {}

                # Assign to IRR bucket
                bucket = self._assign_to_irr_bucket(scenario.calculation_date, contrib.repricing_date)

                if bucket not in irr_gaps_by_currency[currency]:
                    irr_gaps_by_currency[currency][bucket] = Decimal(0)

                irr_gaps_by_currency[currency][bucket] += contrib.repricing_amount

            # Duration & DV01
            if contrib.duration is not None:
                duration_contributions.append(contrib.duration)

            if contrib.dv01 is not None:
                dv01_contributions.append(contrib.dv01)

        # Convert to DataFrame
        if irr_gaps_by_currency:
            irr_gaps_data = []
            for currency, buckets in irr_gaps_by_currency.items():
                for bucket, amount in buckets.items():
                    irr_gaps_data.append({
                        'currency': currency,
                        'bucket': bucket,
                        'repricing_gap': float(amount)
                    })

            result.interest_rate_gaps = pd.DataFrame(irr_gaps_data)
            result.repricing_gap_total = sum([Decimal(row['repricing_gap']) for row in irr_gaps_data])

        # Aggregate duration (weighted by amount - simplified)
        if duration_contributions:
            result.duration_gap = sum(duration_contributions) / len(duration_contributions)

        # Aggregate DV01
        if dv01_contributions:
            result.dv01_total = sum(dv01_contributions)

        # === FX Risk Aggregation ===
        fx_positions = {}
        for contrib in risk_contributions:
            for currency, exposure in contrib.currency_exposure.items():
                if currency not in fx_positions:
                    fx_positions[currency] = Decimal(0)
                fx_positions[currency] += exposure

        result.fx_positions = fx_positions

        # Calculate total FX exposure (in RUB equivalent, simplified)
        # В реальности нужны FX rates
        result.fx_exposure_total = sum([abs(exp) for exp in fx_positions.values()])

        # === Summary Metrics ===
        total_assets = Decimal(0)
        total_liabilities = Decimal(0)

        for contrib in risk_contributions:
            for currency, exposure in contrib.currency_exposure.items():
                if exposure > 0:
                    total_assets += exposure
                else:
                    total_liabilities += abs(exposure)

        result.total_assets = total_assets
        result.total_liabilities = total_liabilities
        result.net_position = total_assets - total_liabilities

        logger.info(
            f"Aggregated risks - Assets: {float(total_assets):,.0f}, "
            f"Liabilities: {float(total_liabilities):,.0f}, "
            f"Net: {float(result.net_position):,.0f}"
        )

        return result

    def _calculate_cumulative_gaps(self, liquidity_gaps: pd.DataFrame) -> pd.DataFrame:
        """Рассчитывает кумулятивные гэпы ликвидности"""
        if liquidity_gaps.empty:
            return pd.DataFrame()

        # Sort buckets
        bucket_order = ['overnight', '2-7d', '8-14d', '15-30d', '30-90d',
                        '90-180d', '180-365d', '1-2y', '2y+']

        cumulative_data = []

        for currency in liquidity_gaps['currency'].unique():
            currency_gaps = liquidity_gaps[liquidity_gaps['currency'] == currency].copy()

            cumulative_gap = 0.0
            for bucket in bucket_order:
                bucket_gaps = currency_gaps[currency_gaps['bucket'] == bucket]

                if not bucket_gaps.empty:
                    gap = bucket_gaps['gap'].sum()
                else:
                    gap = 0.0

                cumulative_gap += gap

                cumulative_data.append({
                    'currency': currency,
                    'bucket': bucket,
                    'gap': gap,
                    'cumulative_gap': cumulative_gap
                })

        return pd.DataFrame(cumulative_data)

    def _calculate_survival_horizon(self, cumulative_gaps: pd.DataFrame) -> Dict[str, int]:
        """
        Рассчитывает горизонт выживания (survival horizon).

        Горизонт выживания = первый временной бакет, где кумулятивный гэп становится отрицательным.
        """
        if cumulative_gaps.empty:
            return {}

        bucket_days_mapping = {
            'overnight': 1,
            '2-7d': 7,
            '8-14d': 14,
            '15-30d': 30,
            '30-90d': 90,
            '90-180d': 180,
            '180-365d': 365,
            '1-2y': 730,
            '2y+': 1095
        }

        survival_horizons = {}

        for currency in cumulative_gaps['currency'].unique():
            currency_data = cumulative_gaps[cumulative_gaps['currency'] == currency]

            # Find first negative cumulative gap
            negative_gaps = currency_data[currency_data['cumulative_gap'] < 0]

            if not negative_gaps.empty:
                first_negative_bucket = negative_gaps.iloc[0]['bucket']
                survival_horizons[currency] = bucket_days_mapping.get(first_negative_bucket, 0)
            else:
                # No negative gaps = survived all horizons
                survival_horizons[currency] = 1095  # 3 years

        return survival_horizons

    def _assign_to_irr_bucket(self, calculation_date: date, repricing_date: date) -> str:
        """Assigns repricing date to IRR bucket"""
        days_to_repricing = (repricing_date - calculation_date).days

        if days_to_repricing <= 30:
            return '0-1m'
        elif days_to_repricing <= 90:
            return '1-3m'
        elif days_to_repricing <= 180:
            return '3-6m'
        elif days_to_repricing <= 365:
            return '6-12m'
        elif days_to_repricing <= 730:
            return '1-2y'
        elif days_to_repricing <= 1095:
            return '2-3y'
        elif days_to_repricing <= 1825:
            return '3-5y'
        elif days_to_repricing <= 2555:
            return '5-7y'
        elif days_to_repricing <= 3650:
            return '7-10y'
        else:
            return '10y+'

    def compare_scenarios(
        self,
        scenarios: List[ScenarioParameters],
        assumptions: Optional[Dict] = None
    ) -> pd.DataFrame:
        """
        Сравнивает несколько сценариев.

        Args:
            scenarios: Список сценариев для расчета
            assumptions: Behavioral assumptions

        Returns:
            DataFrame со сравнением результатов
        """
        logger.info(f"Comparing {len(scenarios)} scenarios")

        results = []

        for scenario in scenarios:
            result = self.calculate_scenario(scenario, assumptions)
            results.append(result.to_dict())

        comparison_df = pd.DataFrame(results)

        return comparison_df


def create_baseline_scenario(calculation_date: date) -> ScenarioParameters:
    """Создает baseline сценарий (без стресса)"""
    return ScenarioParameters(
        scenario_name='Baseline',
        calculation_date=calculation_date
    )


def create_interest_rate_shock_scenario(
    calculation_date: date,
    shock_bps: float = 200
) -> ScenarioParameters:
    """Создает сценарий процентного шока"""
    return ScenarioParameters(
        scenario_name=f'IR Shock +{shock_bps}bp',
        calculation_date=calculation_date,
        interest_rate_shock_bps={
            'RUB': shock_bps,
            'USD': shock_bps * 0.5,  # Меньший шок для USD
            'EUR': shock_bps * 0.5,
        }
    )


def create_deposit_run_scenario(
    calculation_date: date,
    runoff_pct: float = 20
) -> ScenarioParameters:
    """Создает сценарий оттока депозитов"""
    return ScenarioParameters(
        scenario_name=f'Deposit Run {runoff_pct}%',
        calculation_date=calculation_date,
        deposit_runoff_pct=runoff_pct
    )


def create_combined_stress_scenario(calculation_date: date) -> ScenarioParameters:
    """Создает комбинированный стресс-сценарий"""
    return ScenarioParameters(
        scenario_name='Combined Stress',
        calculation_date=calculation_date,
        interest_rate_shock_bps={'RUB': 300, 'USD': 150, 'EUR': 150},
        fx_rate_shock_pct={'USD': 30, 'EUR': 25, 'CNY': 35},
        deposit_runoff_pct=30,
        credit_line_drawdown_pct=50,
        market_liquidity_stress=True
    )
