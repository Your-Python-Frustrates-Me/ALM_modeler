"""
Interbank loan instrument implementation
Межбанковские кредиты (МБК)
"""
from typing import Dict, Optional
from datetime import date
from decimal import Decimal
import logging

from alm_calculator.core.base_instrument import BaseInstrument, InstrumentType, RiskContribution
from alm_calculator.utils.date_utils import assign_to_bucket

logger = logging.getLogger(__name__)


class InterbankLoan(BaseInstrument):
    """
    Межбанковский кредит (МБК).

    Особенности:
    - Может быть активом (размещение, amount > 0) или пассивом (привлечение, amount < 0)
    - Обычно краткосрочный (overnight - 1 год)
    - Фиксированная ставка и четкая дата погашения
    - Контрагент - банк
    - Низкий процентный риск (короткие сроки)
    - Важен для ликвидности
    """

    instrument_type: InstrumentType = InstrumentType.INTERBANK_LOAN

    # МБК всегда имеет четкую дату погашения
    maturity_date: date

    # Специфичные атрибуты
    is_placement: Optional[bool] = None  # True - размещение (актив), False - привлечение (пассив)
    counterparty_bank: Optional[str] = None  # Наименование банка-контрагента
    credit_rating: Optional[str] = None  # Кредитный рейтинг контрагента

    def __init__(self, **data):
        super().__init__(**data)
        # Автоматически определяем направление по знаку amount
        if self.is_placement is None:
            self.is_placement = self.amount > 0
        # МБК всегда межбанковский
        if not self.counterparty_type:
            self.counterparty_type = 'bank'

    def calculate_risk_contribution(
        self,
        calculation_date: date,
        risk_params: Dict,
        assumptions: Optional[Dict] = None
    ) -> RiskContribution:
        """
        Расчет вклада МБК в риски.
        """
        contribution = RiskContribution(
            instrument_id=self.instrument_id,
            instrument_type=self.instrument_type
        )

        # === Interest Rate Risk ===
        # МБК обычно не пересматривается до погашения
        contribution.repricing_date = self.maturity_date
        contribution.repricing_amount = self.amount

        # Duration для МБК (обычно краткосрочный)
        if self.maturity_date and self.interest_rate:
            years_to_maturity = (self.maturity_date - calculation_date).days / 365.25
            contribution.duration = years_to_maturity
            contribution.modified_duration = years_to_maturity / (1 + self.interest_rate)

            # DV01
            dv01_sign = 1 if self.is_placement else -1
            contribution.dv01 = self.amount * Decimal(contribution.modified_duration) * Decimal(0.0001) * dv01_sign

        # === Liquidity Risk ===
        # МБК - простой инструмент с единой датой погашения
        cash_flows = self._generate_cash_flows(calculation_date)

        liquidity_buckets = risk_params.get('liquidity_buckets', [
            '0-7d', '7-14d', '14-30d', '30-90d', '90-180d', '180-365d', '1-2y'
        ])

        for cf_date, cf_amount in cash_flows.items():
            bucket = assign_to_bucket(calculation_date, cf_date, liquidity_buckets)
            contribution.cash_flows[bucket] = contribution.cash_flows.get(bucket, Decimal(0)) + cf_amount

        # === FX Risk ===
        # Размещение - актив, привлечение - пассив
        fx_sign = 1 if self.is_placement else -1
        contribution.currency_exposure[self.currency] = self.amount * fx_sign

        logger.debug(
            f"Calculated risk contribution for {'placement' if self.is_placement else 'borrowing'} MBK {self.instrument_id}",
            extra={
                'instrument_id': self.instrument_id,
                'is_placement': self.is_placement,
                'maturity_date': str(self.maturity_date),
                'amount': float(self.amount)
            }
        )

        return contribution

    def _generate_cash_flows(self, calculation_date: date) -> Dict[date, Decimal]:
        """
        Генерирует денежные потоки МБК.

        МБК - простой bullet инструмент с единой датой погашения.
        """
        cash_flows = {}

        if self.maturity_date >= calculation_date:
            # Размещение - это inflow (+), привлечение - это outflow (-)
            cf_sign = 1 if self.is_placement else -1
            cash_flows[self.maturity_date] = self.amount * cf_sign

        return cash_flows

    def apply_assumptions(self, assumptions: Dict) -> 'InterbankLoan':
        """
        Применяет behavioral assumptions к МБК.

        Для МБК обычно не требуется сложных assumptions,
        т.к. это четко определенный инструмент.

        Возможные assumptions:
        {
            'rollover_probability': 0.8,  # Вероятность пролонгации
            'maturity_adjustment_days': 0  # Корректировка даты погашения
        }
        """
        # МБК обычно не модифицируется assumptions
        # Но можем учесть вероятность пролонгации для крупных позиций
        if 'rollover_probability' in assumptions:
            logger.debug(
                f"Rollover probability {assumptions['rollover_probability']} noted for MBK {self.instrument_id}",
                extra={'rollover_probability': assumptions['rollover_probability']}
            )
            # В будущем можно разбить на две части: с пролонгацией и без

        return self
