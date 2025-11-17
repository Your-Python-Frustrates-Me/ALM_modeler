"""
Bond instrument implementation
Облигации
"""
from typing import Dict, Optional
from datetime import date
from decimal import Decimal
import logging

from alm_calculator.core.base_instrument import BaseInstrument, InstrumentType, RiskContribution
from alm_calculator.utils.date_utils import assign_to_bucket

logger = logging.getLogger(__name__)


class Bond(BaseInstrument):
    """
    Облигация.

    Особенности:
    - Актив (инвестиция в облигации)
    - Имеет номинал, купонные выплаты
    - Может иметь фиксированную или плавающую купонную ставку
    - Критична дюрация для процентного риска
    """

    instrument_type: InstrumentType = InstrumentType.BOND

    # Специфичные атрибуты облигаций
    isin: Optional[str] = None  # ISIN облигации
    nominal_value: Optional[Decimal] = None  # Номинал одной облигации
    quantity: Optional[Decimal] = None  # Количество облигаций
    coupon_rate: Optional[float] = None  # Купонная ставка
    coupon_frequency: Optional[int] = None  # Частота купонных выплат в днях

    # Дополнительные поля для классификации и учета
    instrument_class: Optional[str] = None  # Класс инструмента
    instrument_subclass: Optional[str] = None  # Подкласс инструмента
    bond_name: Optional[str] = None  # Название облигации

    # Параметры процентных платежей
    is_interest: bool = False  # False - платеж тела, True - процентный платеж (купон)

    # Параметры ставки
    is_fix: bool = True  # True - фиксированная купонная ставка, False - плавающая
    fix_rate: Optional[float] = None  # Фиксированная ставка (если is_fix=True)
    float_indicator: Optional[str] = None  # Индикатор плавающей ставки (RUONIA, KeyRate и т.д.)
    float_margin: Optional[float] = None  # Маржа плавающей ставки

    # Дополнительные даты
    date_open: Optional[date] = None  # Дата начала владения облигацией
    date_close: Optional[date] = None  # Дата погашения облигации

    # Рыночная информация
    market_price: Optional[Decimal] = None  # Рыночная цена облигации (в % от номинала)
    accrued_interest: Optional[Decimal] = None  # Накопленный купонный доход

    def calculate_risk_contribution(
        self,
        calculation_date: date,
        risk_params: Dict,
        assumptions: Optional[Dict] = None
    ) -> RiskContribution:
        """
        Расчет вклада облигации в риски.
        """
        contribution = RiskContribution(
            instrument_id=self.instrument_id,
            instrument_type=self.instrument_type
        )

        # === Interest Rate Risk ===
        # Облигация - актив с фиксированными купонами до погашения
        if self.date_close:
            contribution.repricing_date = self.date_close
        elif self.maturity_date:
            contribution.repricing_date = self.maturity_date

        contribution.repricing_amount = self.amount  # Актив

        # Duration (критична для облигаций)
        if contribution.repricing_date and self.coupon_rate:
            years_to_maturity = (contribution.repricing_date - calculation_date).days / 365.25
            # Упрощенная Macaulay Duration для облигации с купонами
            contribution.duration = self._calculate_duration(
                years_to_maturity,
                self.coupon_rate,
                self.coupon_frequency
            )
            contribution.modified_duration = contribution.duration / (1 + self.coupon_rate)
            # Актив - положительный DV01
            contribution.dv01 = self.amount * Decimal(contribution.modified_duration) * Decimal(0.0001)

        # === Liquidity Risk ===
        cash_flows = self._generate_cash_flows(calculation_date)

        liquidity_buckets = risk_params.get('liquidity_buckets', [
            '0-30d', '30-90d', '90-180d', '180-365d', '1-2y', '2-5y', '5-10y', '10y+'
        ])

        for cf_date, cf_amount in cash_flows.items():
            bucket = assign_to_bucket(calculation_date, cf_date, liquidity_buckets)
            contribution.cash_flows[bucket] = contribution.cash_flows.get(bucket, Decimal(0)) + cf_amount

        # === FX Risk ===
        # Облигация - актив
        contribution.currency_exposure[self.currency] = self.amount

        logger.debug(
            f"Calculated risk contribution for Bond {self.instrument_id}",
            extra={
                'instrument_id': self.instrument_id,
                'isin': self.isin,
                'maturity_date': str(contribution.repricing_date),
                'amount': float(self.amount),
                'duration': contribution.duration
            }
        )

        return contribution

    def _calculate_duration(
        self,
        years_to_maturity: float,
        coupon_rate: float,
        coupon_frequency: Optional[int]
    ) -> float:
        """
        Рассчитывает приблизительную Macaulay Duration для облигации.

        Упрощенная формула для облигации с регулярными купонами.
        """
        if not coupon_frequency or coupon_frequency == 0:
            # Zero-coupon bond
            return years_to_maturity

        # Количество купонных выплат в год
        payments_per_year = 365 / coupon_frequency
        n_periods = years_to_maturity * payments_per_year

        # Упрощенная формула Macaulay Duration
        if coupon_rate > 0:
            # Формула для купонной облигации
            duration = (1 + 1/payments_per_year) / coupon_rate
            duration -= (1 + 1/payments_per_year + (n_periods - 1) * coupon_rate) / (coupon_rate * ((1 + coupon_rate)**n_periods - 1))
            return duration
        else:
            # Без купонов - duration равна сроку
            return years_to_maturity

    def _generate_cash_flows(self, calculation_date: date) -> Dict[date, Decimal]:
        """
        Генерирует денежные потоки облигации.

        Облигация: купонные выплаты + погашение номинала.
        """
        cash_flows = {}

        maturity = self.date_close or self.maturity_date
        if not maturity or maturity < calculation_date:
            return cash_flows

        # Генерация купонных выплат
        if self.coupon_frequency and self.coupon_rate and self.nominal_value and self.quantity:
            coupon_payment = self.nominal_value * Decimal(self.coupon_rate) * self.quantity * Decimal(self.coupon_frequency / 365.0)

            # Генерируем даты купонных выплат
            current_date = calculation_date
            while current_date < maturity:
                from datetime import timedelta
                current_date = current_date + timedelta(days=self.coupon_frequency)
                if current_date <= maturity:
                    cash_flows[current_date] = cash_flows.get(current_date, Decimal(0)) + coupon_payment

        # Погашение номинала в дату погашения
        if maturity >= calculation_date:
            redemption_amount = self.amount  # Используем балансовую стоимость
            if self.nominal_value and self.quantity:
                redemption_amount = self.nominal_value * self.quantity
            cash_flows[maturity] = cash_flows.get(maturity, Decimal(0)) + redemption_amount

        return cash_flows

    def apply_assumptions(self, assumptions: Dict) -> 'Bond':
        """
        Применяет behavioral assumptions к облигации.

        Возможные assumptions:
        {
            'early_redemption_probability': 0.1,  # Вероятность досрочного погашения
            'default_probability': 0.02,           # Вероятность дефолта
            'recovery_rate': 0.40                  # Recovery rate при дефолте
        }
        """
        if 'early_redemption_probability' in assumptions:
            logger.debug(
                f"Early redemption probability {assumptions['early_redemption_probability']} noted for Bond {self.instrument_id}",
                extra={'early_redemption_probability': assumptions['early_redemption_probability']}
            )

        if 'default_probability' in assumptions:
            logger.debug(
                f"Default probability {assumptions['default_probability']} noted for Bond {self.instrument_id}",
                extra={'default_probability': assumptions['default_probability']}
            )

        return self
