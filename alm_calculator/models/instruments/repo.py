"""
REPO and Reverse REPO instrument implementation
Операции прямого и обратного РЕПО
"""
from typing import Dict, Optional
from datetime import date
from decimal import Decimal
import logging

from alm_calculator.core.base_instrument import BaseInstrument, InstrumentType, RiskContribution
from alm_calculator.utils.date_utils import assign_to_bucket

logger = logging.getLogger(__name__)


class Repo(BaseInstrument):
    """
    Прямое РЕПО (продажа ценных бумаг с обязательством обратного выкупа).

    Особенности:
    - Пассив (привлечение ликвидности под залог ЦБ)
    - Обычно краткосрочный (overnight - несколько недель)
    - Фиксированная ставка РЕПО
    - Есть обеспечение (залоговые ЦБ)
    - Критичен для ликвидности
    """

    instrument_type: InstrumentType = InstrumentType.REPO

    # РЕПО всегда имеет четкую дату погашения
    maturity_date: date

    # Специфичные атрибуты
    repo_rate: Optional[float] = None  # Ставка РЕПО (может отличаться от interest_rate)
    collateral_type: Optional[str] = None  # Тип обеспечения (OFZ, Corporate bonds, etc.)
    collateral_value: Optional[Decimal] = None  # Рыночная стоимость обеспечения
    haircut: Optional[float] = None  # Дисконт обеспечения (обычно 0-20%)
    counterparty_type: str = 'bank'  # Обычно контрагент - банк или ЦБ РФ

    def calculate_risk_contribution(
        self,
        calculation_date: date,
        risk_params: Dict,
        assumptions: Optional[Dict] = None
    ) -> RiskContribution:
        """
        Расчет вклада РЕПО в риски.
        """
        contribution = RiskContribution(
            instrument_id=self.instrument_id,
            instrument_type=self.instrument_type
        )

        # === Interest Rate Risk ===
        # РЕПО - пассив с фиксированной ставкой до погашения
        contribution.repricing_date = self.maturity_date
        contribution.repricing_amount = -self.amount  # Пассив

        # Duration (обычно очень короткий)
        if self.maturity_date and self.repo_rate:
            years_to_maturity = (self.maturity_date - calculation_date).days / 365.25
            contribution.duration = years_to_maturity
            contribution.modified_duration = years_to_maturity / (1 + self.repo_rate)
            # Пассив - отрицательный DV01
            contribution.dv01 = -self.amount * Decimal(contribution.modified_duration) * Decimal(0.0001)

        # === Liquidity Risk ===
        cash_flows = self._generate_cash_flows(calculation_date)

        liquidity_buckets = risk_params.get('liquidity_buckets', [
            'overnight', '2-7d', '8-14d', '15-30d', '30-90d', '90-180d'
        ])

        for cf_date, cf_amount in cash_flows.items():
            bucket = assign_to_bucket(calculation_date, cf_date, liquidity_buckets)
            contribution.cash_flows[bucket] = contribution.cash_flows.get(bucket, Decimal(0)) + cf_amount

        # === FX Risk ===
        # РЕПО - пассив
        contribution.currency_exposure[self.currency] = -self.amount

        logger.debug(
            f"Calculated risk contribution for REPO {self.instrument_id}",
            extra={
                'instrument_id': self.instrument_id,
                'maturity_date': str(self.maturity_date),
                'amount': float(self.amount),
                'collateral_type': self.collateral_type
            }
        )

        return contribution

    def _generate_cash_flows(self, calculation_date: date) -> Dict[date, Decimal]:
        """
        Генерирует денежные потоки РЕПО.

        РЕПО: outflow при обратном выкупе (возврат денег + %%).
        """
        cash_flows = {}

        if self.maturity_date >= calculation_date:
            # Outflow (возврат денег контрагенту)
            cash_flows[self.maturity_date] = -self.amount

        return cash_flows

    def apply_assumptions(self, assumptions: Dict) -> 'Repo':
        """
        Применяет behavioral assumptions к РЕПО.

        Возможные assumptions:
        {
            'rollover_probability': 0.9,  # Вероятность пролонгации
            'haircut_adjustment': 0.05    # Корректировка дисконта в стрессе
        }
        """
        if 'rollover_probability' in assumptions:
            logger.debug(
                f"Rollover probability {assumptions['rollover_probability']} noted for REPO {self.instrument_id}",
                extra={'rollover_probability': assumptions['rollover_probability']}
            )

        return self


class ReverseRepo(BaseInstrument):
    """
    Обратное РЕПО (покупка ценных бумаг с обязательством обратной продажи).

    Особенности:
    - Актив (размещение ликвидности под залог ЦБ)
    - Обычно краткосрочный (overnight - несколько недель)
    - Фиксированная ставка РЕПО
    - Есть полученное обеспечение
    - Критичен для ликвидности
    """

    instrument_type: InstrumentType = InstrumentType.REVERSE_REPO

    # Обратное РЕПО всегда имеет четкую дату погашения
    maturity_date: date

    # Специфичные атрибуты
    repo_rate: Optional[float] = None  # Ставка РЕПО
    collateral_type: Optional[str] = None  # Тип полученного обеспечения
    collateral_value: Optional[Decimal] = None  # Рыночная стоимость обеспечения
    haircut: Optional[float] = None  # Дисконт обеспечения
    counterparty_type: str = 'bank'  # Обычно контрагент - банк

    def calculate_risk_contribution(
        self,
        calculation_date: date,
        risk_params: Dict,
        assumptions: Optional[Dict] = None
    ) -> RiskContribution:
        """
        Расчет вклада обратного РЕПО в риски.
        """
        contribution = RiskContribution(
            instrument_id=self.instrument_id,
            instrument_type=self.instrument_type
        )

        # === Interest Rate Risk ===
        # Обратное РЕПО - актив с фиксированной ставкой до погашения
        contribution.repricing_date = self.maturity_date
        contribution.repricing_amount = self.amount  # Актив

        # Duration (обычно очень короткий)
        if self.maturity_date and self.repo_rate:
            years_to_maturity = (self.maturity_date - calculation_date).days / 365.25
            contribution.duration = years_to_maturity
            contribution.modified_duration = years_to_maturity / (1 + self.repo_rate)
            # Актив - положительный DV01
            contribution.dv01 = self.amount * Decimal(contribution.modified_duration) * Decimal(0.0001)

        # === Liquidity Risk ===
        cash_flows = self._generate_cash_flows(calculation_date)

        liquidity_buckets = risk_params.get('liquidity_buckets', [
            'overnight', '2-7d', '8-14d', '15-30d', '30-90d', '90-180d'
        ])

        for cf_date, cf_amount in cash_flows.items():
            bucket = assign_to_bucket(calculation_date, cf_date, liquidity_buckets)
            contribution.cash_flows[bucket] = contribution.cash_flows.get(bucket, Decimal(0)) + cf_amount

        # === FX Risk ===
        # Обратное РЕПО - актив
        contribution.currency_exposure[self.currency] = self.amount

        logger.debug(
            f"Calculated risk contribution for Reverse REPO {self.instrument_id}",
            extra={
                'instrument_id': self.instrument_id,
                'maturity_date': str(self.maturity_date),
                'amount': float(self.amount),
                'collateral_type': self.collateral_type
            }
        )

        return contribution

    def _generate_cash_flows(self, calculation_date: date) -> Dict[date, Decimal]:
        """
        Генерирует денежные потоки обратного РЕПО.

        Обратное РЕПО: inflow при обратной продаже (получение денег + %%).
        """
        cash_flows = {}

        if self.maturity_date >= calculation_date:
            # Inflow (получение денег от контрагента)
            cash_flows[self.maturity_date] = self.amount

        return cash_flows

    def apply_assumptions(self, assumptions: Dict) -> 'ReverseRepo':
        """
        Применяет behavioral assumptions к обратному РЕПО.

        Возможные assumptions:
        {
            'rollover_probability': 0.7,  # Вероятность пролонгации
            'recovery_rate': 0.95         # Recovery в случае дефолта контрагента (с учетом залога)
        }
        """
        if 'rollover_probability' in assumptions:
            logger.debug(
                f"Rollover probability {assumptions['rollover_probability']} noted for Reverse REPO {self.instrument_id}",
                extra={'rollover_probability': assumptions['rollover_probability']}
            )

        return self
