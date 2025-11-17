"""
Loan instrument implementation
"""
from typing import Dict, Optional
from datetime import date, timedelta
from decimal import Decimal
import logging

from alm_calculator.core.base_instrument import BaseInstrument, InstrumentType, RiskContribution

logger = logging.getLogger(__name__)


class Loan(BaseInstrument):
    """
    Кредитный инструмент.
    
    Особенности:
    - Актив (amount > 0)
    - Может иметь график погашения
    - Возможен prepayment
    """
    
    instrument_type: InstrumentType = InstrumentType.LOAN
    
    # Специфичные для кредита атрибуты
    repricing_date: Optional[date] = None  # Дата переоценки процентной ставки
    repayment_schedule: Optional[Dict[date, Decimal]] = None  # График погашений
    prepayment_rate: Optional[float] = None  # Годовая ставка досрочного погашения

    # Дополнительные поля для классификации и учета
    instrument_class: Optional[str] = None  # Класс инструмента
    instrument_subclass: Optional[str] = None  # Подкласс инструмента
    counterparty_name: Optional[str] = None  # Имя контрагента

    # Параметры процентных платежей
    is_interest: bool = False  # False - платеж тела, True - процентный платеж

    # Параметры ставки
    is_fix: bool = True  # True - фиксированная ставка, False - плавающая
    fix_rate: Optional[float] = None  # Фиксированная ставка (если is_fix=True)
    float_indicator: Optional[str] = None  # Индикатор плавающей ставки (RUONIA, KeyRate и т.д.)
    float_margin: Optional[float] = None  # Маржа плавающей ставки

    # Дополнительные даты
    trade_date: Optional[date] = None  # Дата заключения сделки

    # Портфельная принадлежность
    trading_portfolio: Optional[str] = None  # Торговый портфель

    # Параметры резервирования и качества
    reserve_rate: Optional[float] = None  # Ставка резерва (в долях от суммы кредита)
    credit_quality_category: Optional[str] = None  # Категория качества кредита (I, II, III, IV, V)
    is_overdue: bool = False  # Флаг просрочки
    
    def calculate_risk_contribution(
        self, 
        calculation_date: date,
        risk_params: Dict,
        assumptions: Optional[Dict] = None
    ) -> RiskContribution:
        """
        Расчет вклада кредита в риски.
        """
        contribution = RiskContribution(
            instrument_id=self.instrument_id,
            instrument_type=self.instrument_type
        )
        
        # === Interest Rate Risk ===
        # Дата переоценки (для gap analysis)
        effective_repricing = self.repricing_date or self.maturity_date
        if effective_repricing:
            contribution.repricing_date = effective_repricing
            contribution.repricing_amount = self.amount
        
        # Duration расчет (упрощенная модель для примера)
        if self.maturity_date and self.interest_rate:
            years_to_maturity = (self.maturity_date - calculation_date).days / 365.25
            # Simplified Macaulay Duration для bullet loan
            contribution.duration = years_to_maturity
            contribution.modified_duration = years_to_maturity / (1 + self.interest_rate)
            
            # DV01: изменение стоимости при параллельном сдвиге на 1 б.п.
            contribution.dv01 = self.amount * Decimal(contribution.modified_duration) * Decimal(0.0001)
        
        # === Liquidity Risk ===
        # Генерируем cash flows с учетом графика погашения или единой датой
        cash_flows = self._generate_cash_flows(calculation_date, assumptions)
        
        # Распределяем CF по временным корзинам
        liquidity_buckets = risk_params.get('liquidity_buckets', [
            '0-30d', '30-90d', '90-180d', '180-365d', '1-2y', '2y+'
        ])
        
        from alm_calculator.utils.date_utils import assign_to_bucket
        
        for cf_date, cf_amount in cash_flows.items():
            bucket = assign_to_bucket(calculation_date, cf_date, liquidity_buckets)
            contribution.cash_flows[bucket] = contribution.cash_flows.get(bucket, Decimal(0)) + cf_amount
        
        # === FX Risk ===
        contribution.currency_exposure[self.currency] = self.amount
        
        logger.debug(
            f"Calculated risk contribution for loan {self.instrument_id}",
            extra={
                'instrument_id': self.instrument_id,
                'repricing_date': str(contribution.repricing_date),
                'duration': contribution.duration
            }
        )
        
        return contribution
    
    def _generate_cash_flows(
        self, 
        calculation_date: date,
        assumptions: Optional[Dict] = None
    ) -> Dict[date, Decimal]:
        """
        Генерирует денежные потоки с учетом:
        - Графика погашения
        - Prepayment assumptions
        - Процентных платежей
        """
        cash_flows = {}
        
        # Если есть график - используем его
        if self.repayment_schedule:
            for cf_date, cf_amount in self.repayment_schedule.items():
                if cf_date >= calculation_date:
                    cash_flows[cf_date] = cf_amount
        
        # Если нет графика - единая дата погашения
        elif self.maturity_date and self.maturity_date >= calculation_date:
            cash_flows[self.maturity_date] = self.amount
        
        # Применяем prepayment если задан
        if assumptions and 'prepayment_rate' in assumptions:
            cash_flows = self._apply_prepayment(cash_flows, assumptions['prepayment_rate'])
        
        return cash_flows
    
    def _apply_prepayment(
        self, 
        cash_flows: Dict[date, Decimal], 
        annual_prepayment_rate: float
    ) -> Dict[date, Decimal]:
        """
        Применяет CPR (Constant Prepayment Rate) к денежным потокам.
        
        Упрощенная модель: распределяем prepayment равномерно до maturity.
        """
        # TODO: Реализовать полноценную CPR/SMM модель
        logger.warning("Prepayment model not fully implemented, using simplified version")
        return cash_flows
    
    def apply_assumptions(self, assumptions: Dict) -> 'Loan':
        """
        Применяет behavioral assumptions к кредиту.
        
        Пример assumptions:
        {
            'prepayment_rate': 0.15,  # 15% годовых
            'repricing_adjustment': 30  # Сдвиг repricing на 30 дней
        }
        """
        if 'prepayment_rate' in assumptions:
            self.prepayment_rate = assumptions['prepayment_rate']
            logger.debug(
                f"Applied prepayment assumption to loan {self.instrument_id}",
                extra={'prepayment_rate': assumptions['prepayment_rate']}
            )
        
        if 'repricing_adjustment' in assumptions and self.repricing_date:
            self.repricing_date = self.repricing_date + timedelta(days=assumptions['repricing_adjustment'])
            logger.debug(
                f"Adjusted repricing date for loan {self.instrument_id}",
                extra={'adjustment_days': assumptions['repricing_adjustment']}
            )
        
        return self
