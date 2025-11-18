"""
Off-Balance Sheet Instruments implementation
Внебалансовые инструменты
"""
from typing import Dict, Optional
from datetime import date, timedelta

import logging

from alm_calculator.core.base_instrument import BaseInstrument, InstrumentType, RiskContribution
from alm_calculator.utils.date_utils import assign_to_bucket

logger = logging.getLogger(__name__)


class OffBalanceInstrument(BaseInstrument):
    """
    Внебалансовый инструмент.

    Включает:
    - Гарантии выданные и полученные
    - Аккредитивы
    - Незадействованные кредитные линии
    - Форвардные контракты
    - Свопы (IRS, XCCY)
    - Опционы
    - Обязательства по будущим выплатам

    Особенности:
    - Не отражаются в балансе на дату расчета
    - Могут стать балансовыми (contingent obligations)
    - Создают потенциальные cash flows
    - Имеют процентный и валютный риск (деривативы)
    - Критичны для расчета ликвидности (draw-down scenarios)
    """

    instrument_type: InstrumentType = InstrumentType.OFF_BALANCE

    # Специфичные атрибуты
    off_balance_type: str  # 'guarantee', 'credit_line', 'forward', 'swap', 'option', 'other'

    # Notional amount (условная сумма)
    notional_amount: float  # Для деривативов - notional

    # Параметры исполнения
    draw_down_probability: Optional[float] = None  # Вероятность использования (для гарантий, кредитных линий)
    expiry_date: Optional[date] = None  # Дата истечения обязательства
    settlement_date: Optional[date] = None  # Дата исполнения/расчетов

    # Для деривативов
    derivative_type: Optional[str] = None  # 'IRS', 'XCCY_SWAP', 'FX_FORWARD', 'FX_OPTION', etc.
    pay_leg_currency: Optional[str] = None  # Валюта платежной ноги
    receive_leg_currency: Optional[str] = None  # Валюта получаемой ноги
    pay_leg_amount: Optional[float] = None
    receive_leg_amount: Optional[float] = None
    is_payer: Optional[bool] = None  # True - платим fixed (IRS), False - получаем fixed

    # Для гарантий и кредитных линий
    utilized_amount: Optional[float] = None  # Уже использованная часть
    available_amount: Optional[float] = None  # Доступная к использованию

    def calculate_risk_contribution(
        self,
        calculation_date: date,
        risk_params: Dict,
        assumptions: Optional[Dict] = None
    ) -> RiskContribution:
        """
        Расчет вклада внебалансового инструмента в риски.
        """
        contribution = RiskContribution(
            instrument_id=self.instrument_id,
            instrument_type=self.instrument_type
        )

        # Логика зависит от типа инструмента
        if self.off_balance_type in ['guarantee', 'credit_line']:
            self._calculate_contingent_contribution(contribution, calculation_date, risk_params, assumptions)

        elif self.off_balance_type in ['forward', 'swap']:
            self._calculate_derivative_contribution(contribution, calculation_date, risk_params, assumptions)

        elif self.off_balance_type == 'option':
            self._calculate_option_contribution(contribution, calculation_date, risk_params, assumptions)

        logger.debug(
            f"Calculated risk contribution for Off-Balance {self.off_balance_type} {self.instrument_id}",
            extra={
                'instrument_id': self.instrument_id,
                'off_balance_type': self.off_balance_type,
                'notional_amount': float(self.notional_amount)
            }
        )

        return contribution

    def _calculate_contingent_contribution(
        self,
        contribution: RiskContribution,
        calculation_date: date,
        risk_params: Dict,
        assumptions: Optional[Dict]
    ) -> None:
        """
        Расчет для contingent obligations (гарантии, кредитные линии).
        """
        # === Interest Rate Risk ===
        # Минимальный IRR для contingent (пока не задействованы)
        contribution.repricing_date = None
        contribution.repricing_amount = 0.0

        # === Liquidity Risk ===
        # Потенциальный outflow при исполнении обязательства
        cash_flows = {}

        # Определяем вероятность и сумму draw-down
        draw_down_prob = self.draw_down_probability if self.draw_down_probability else 0.5  # Default 50%

        if self.available_amount:
            expected_draw_down = self.available_amount * float(draw_down_prob)
        else:
            expected_draw_down = self.notional_amount * float(draw_down_prob)

        # Дата потенциального использования
        if self.settlement_date:
            draw_down_date = self.settlement_date
        elif self.expiry_date:
            # Консервативно: в середине срока до expiry
            days_to_expiry = (self.expiry_date - calculation_date).days
            draw_down_date = calculation_date + timedelta(days=days_to_expiry // 2)
        else:
            # Default: 30 дней
            draw_down_date = calculation_date + timedelta(days=30)

        # Потенциальный outflow
        cash_flows[draw_down_date] = -expected_draw_down

        liquidity_buckets = risk_params.get('liquidity_buckets', [
            '0-30d', '30-90d', '90-180d', '180-365d', '1y+'
        ])

        for cf_date, cf_amount in cash_flows.items():
            bucket = assign_to_bucket(calculation_date, cf_date, liquidity_buckets)
            contribution.cash_flows[bucket] = contribution.cash_flows.get(bucket, 0.0) + cf_amount

        # === FX Risk ===
        # Гарантии в валюте создают потенциальную валютную позицию
        contribution.currency_exposure[self.currency] = -expected_draw_down

    def _calculate_derivative_contribution(
        self,
        contribution: RiskContribution,
        calculation_date: date,
        risk_params: Dict,
        assumptions: Optional[Dict]
    ) -> None:
        """
        Расчет для деривативов (форварды, свопы).
        """
        # === Interest Rate Risk ===
        if self.derivative_type == 'IRS' and self.settlement_date:
            # Interest Rate Swap: учитываем notional по fixed leg
            contribution.repricing_date = self.settlement_date
            if self.is_payer:
                # Платим fixed - пассив
                contribution.repricing_amount = -self.notional_amount
            else:
                # Получаем fixed - актив
                contribution.repricing_amount = self.notional_amount

            # Duration для IRS (упрощенно)
            if self.interest_rate:
                years = (self.settlement_date - calculation_date).days / 365.25
                contribution.duration = years
                contribution.modified_duration = years / (1 + self.interest_rate)
                dv01_sign = -1 if self.is_payer else 1
                contribution.dv01 = self.notional_amount * float(contribution.modified_duration) * float(0.0001) * dv01_sign

        # === Liquidity Risk ===
        cash_flows = {}

        if self.off_balance_type == 'forward' and self.settlement_date:
            # FX Forward: два встречных потока в settlement date
            if self.pay_leg_currency and self.pay_leg_amount:
                cash_flows[self.settlement_date] = -self.pay_leg_amount  # Outflow
            if self.receive_leg_currency and self.receive_leg_amount:
                # Для inflow используем отдельный CF в валюте получения
                # Но для упрощения учтем как одну позицию
                pass

        elif self.derivative_type in ['IRS', 'XCCY_SWAP']:
            # Свопы: периодические платежи (упрощенно - settlement date)
            if self.settlement_date:
                # Net CF свопа (приближенно)
                # В реальности нужно моделировать все купонные платежи
                net_cf = 0.0  # Placeholder
                cash_flows[self.settlement_date] = net_cf

        liquidity_buckets = risk_params.get('liquidity_buckets', [
            '0-30d', '30-90d', '90-180d', '180-365d', '1y+'
        ])

        for cf_date, cf_amount in cash_flows.items():
            bucket = assign_to_bucket(calculation_date, cf_date, liquidity_buckets)
            contribution.cash_flows[bucket] = contribution.cash_flows.get(bucket, 0.0) + cf_amount

        # === FX Risk ===
        if self.off_balance_type == 'forward' or self.derivative_type == 'XCCY_SWAP':
            # FX Forward/XCCY Swap: две валютные позиции
            if self.pay_leg_currency and self.pay_leg_amount:
                contribution.currency_exposure[self.pay_leg_currency] = -self.pay_leg_amount
            if self.receive_leg_currency and self.receive_leg_amount:
                contribution.currency_exposure[self.receive_leg_currency] = self.receive_leg_amount

    def _calculate_option_contribution(
        self,
        contribution: RiskContribution,
        calculation_date: date,
        risk_params: Dict,
        assumptions: Optional[Dict]
    ) -> None:
        """
        Расчет для опционов.

        Опционы требуют более сложного моделирования (Greeks).
        Для ALM обычно учитывают потенциальный cash flow при исполнении.
        """
        # Упрощенный подход: delta-equivalent position
        # В полной модели нужны Delta, Gamma, Vega, etc.

        # Здесь - placeholder для простой модели
        logger.warning(f"Option pricing not fully implemented for {self.instrument_id}")

        # Потенциальный CF при исполнении (delta ~0.5 для ATM)
        if self.expiry_date:
            delta = 0.5  # Simplified assumption
            potential_cf = self.notional_amount * float(delta)

            liquidity_buckets = risk_params.get('liquidity_buckets', ['0-30d', '30-90d', '90-180d', '180-365d', '1y+'])
            bucket = assign_to_bucket(calculation_date, self.expiry_date, liquidity_buckets)
            contribution.cash_flows[bucket] = potential_cf

    def apply_assumptions(self, assumptions: Dict) -> 'OffBalanceInstrument':
        """
        Применяет behavioral assumptions к внебалансовому инструменту.

        Примеры:
        {
            # Для гарантий и кредитных линий:
            'draw_down_probability': 0.30,  # 30% вероятность использования
            'stress_draw_down_probability': 0.80,  # В стрессе - 80%

            # Для опционов:
            'exercise_probability': 0.60,

            # Общие:
            'include_in_liquidity_stress': True
        }
        """
        if 'draw_down_probability' in assumptions:
            self.draw_down_probability = assumptions['draw_down_probability']

        logger.debug(
            f"Applied assumptions to Off-Balance {self.off_balance_type} {self.instrument_id}",
            extra={
                'off_balance_type': self.off_balance_type,
                'draw_down_probability': self.draw_down_probability
            }
        )

        return self
