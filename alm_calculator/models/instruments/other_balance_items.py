"""
Other Assets and Other Liabilities instrument implementation
Прочие активы и прочие пассивы
"""
from typing import Dict, Optional
from datetime import date, timedelta
from decimal import Decimal
import logging

from alm_calculator.core.base_instrument import BaseInstrument, InstrumentType, RiskContribution
from alm_calculator.utils.date_utils import assign_to_bucket

logger = logging.getLogger(__name__)


class OtherAsset(BaseInstrument):
    """
    Прочие активы.

    Включает:
    - Основные средства (здания, оборудование)
    - Нематериальные активы (ПО, лицензии)
    - Дебиторская задолженность
    - Расчеты с бюджетом
    - Прочие финансовые активы

    Особенности:
    - Обычно не генерируют процентных доходов
    - Могут иметь или не иметь дату погашения
    - Низкая ликвидность (особенно ОС)
    - Минимальный процентный риск
    """

    instrument_type: InstrumentType = InstrumentType.OTHER_ASSET

    # Специфичные атрибуты
    asset_category: Optional[str] = None  # 'fixed_assets', 'intangible', 'receivables', 'other'
    is_monetary: bool = True  # Является ли денежным активом (влияет на FX risk)
    liquidation_value: Optional[Decimal] = None  # Ликвидационная стоимость
    liquidity_haircut: Optional[float] = None  # Дисконт при срочной продаже (0-1)

    def calculate_risk_contribution(
        self,
        calculation_date: date,
        risk_params: Dict,
        assumptions: Optional[Dict] = None
    ) -> RiskContribution:
        """
        Расчет вклада прочего актива в риски.
        """
        contribution = RiskContribution(
            instrument_id=self.instrument_id,
            instrument_type=self.instrument_type
        )

        # === Interest Rate Risk ===
        # Прочие активы обычно не имеют процентного риска
        # Но если есть maturity_date и interest_rate - учитываем
        if self.maturity_date and self.interest_rate:
            contribution.repricing_date = self.maturity_date
            contribution.repricing_amount = self.amount

            years_to_maturity = (self.maturity_date - calculation_date).days / 365.25
            contribution.duration = years_to_maturity
            contribution.modified_duration = years_to_maturity / (1 + self.interest_rate)
            contribution.dv01 = self.amount * Decimal(contribution.modified_duration) * Decimal(0.0001)
        else:
            # Не чувствителен к ставкам (например, здания)
            contribution.repricing_date = None
            contribution.repricing_amount = Decimal(0)

        # === Liquidity Risk ===
        cash_flows = self._generate_cash_flows(calculation_date, assumptions)

        liquidity_buckets = risk_params.get('liquidity_buckets', [
            '0-30d', '30-90d', '90-180d', '180-365d', '1-2y', '2y+'
        ])

        for cf_date, cf_amount in cash_flows.items():
            bucket = assign_to_bucket(calculation_date, cf_date, liquidity_buckets)
            contribution.cash_flows[bucket] = contribution.cash_flows.get(bucket, Decimal(0)) + cf_amount

        # === FX Risk ===
        # Только денежные активы имеют валютный риск
        if self.is_monetary:
            contribution.currency_exposure[self.currency] = self.amount

        logger.debug(
            f"Calculated risk contribution for Other Asset {self.instrument_id}",
            extra={
                'instrument_id': self.instrument_id,
                'asset_category': self.asset_category,
                'amount': float(self.amount)
            }
        )

        return contribution

    def _generate_cash_flows(
        self,
        calculation_date: date,
        assumptions: Optional[Dict] = None
    ) -> Dict[date, Decimal]:
        """
        Генерирует денежные потоки прочего актива.

        Логика зависит от типа актива:
        - Дебиторская задолженность: дата погашения
        - Основные средства: амортизация или продажа
        - Нематериальные активы: обычно не генерируют CF
        """
        cash_flows = {}

        if self.maturity_date and self.maturity_date >= calculation_date:
            # Есть четкая дата погашения (например, дебиторка)
            cash_flows[self.maturity_date] = self.amount

        elif self.asset_category == 'fixed_assets':
            # Основные средства: можно продать при необходимости
            # Используем liquidation value с дисконтом
            if assumptions and 'fixed_assets_liquidation_horizon_days' in assumptions:
                horizon = assumptions['fixed_assets_liquidation_horizon_days']
                liquidation_date = calculation_date + timedelta(days=horizon)

                # Ликвидационная стоимость
                haircut = self.liquidity_haircut if self.liquidity_haircut else 0.5  # Default 50% haircut
                liquidation_amount = self.amount * Decimal(1 - haircut)

                cash_flows[liquidation_date] = liquidation_amount
            # Иначе - считаем неликвидным (не генерирует CF в модели)

        elif self.asset_category == 'receivables':
            # Дебиторка: ожидаемая дата погашения
            if assumptions and 'receivables_collection_days' in assumptions:
                collection_days = assumptions['receivables_collection_days']
            else:
                collection_days = 90  # Default 90 дней

            cash_flows[calculation_date + timedelta(days=collection_days)] = self.amount

        # Для остальных категорий (intangible, other) - не генерируем CF
        # или используем maturity_date если указан

        return cash_flows

    def apply_assumptions(self, assumptions: Dict) -> 'OtherAsset':
        """
        Применяет behavioral assumptions к прочему активу.

        Примеры:
        {
            'fixed_assets_liquidation_horizon_days': 365,  # Срок продажи ОС
            'receivables_collection_days': 90,             # Срок взыскания дебиторки
            'liquidity_haircut': 0.50                      # Дисконт при срочной продаже
        }
        """
        if 'liquidity_haircut' in assumptions:
            self.liquidity_haircut = assumptions['liquidity_haircut']

        logger.debug(
            f"Applied assumptions to Other Asset {self.instrument_id}",
            extra={
                'asset_category': self.asset_category,
                'liquidity_haircut': self.liquidity_haircut
            }
        )

        return self


class OtherLiability(BaseInstrument):
    """
    Прочие пассивы.

    Включает:
    - Кредиторская задолженность
    - Резервы под обязательства
    - Расчеты с персоналом
    - Прочие финансовые обязательства

    Особенности:
    - Обычно не генерируют процентных расходов
    - Могут иметь или не иметь дату погашения
    - Различная степень срочности
    - Минимальный процентный риск
    """

    instrument_type: InstrumentType = InstrumentType.OTHER_LIABILITY

    # Специфичные атрибуты
    liability_category: Optional[str] = None  # 'payables', 'reserves', 'payroll', 'other'
    is_monetary: bool = True  # Является ли денежным обязательством (влияет на FX risk)
    priority_level: Optional[str] = None  # 'senior', 'subordinated' (для расчета ликвидности)

    def calculate_risk_contribution(
        self,
        calculation_date: date,
        risk_params: Dict,
        assumptions: Optional[Dict] = None
    ) -> RiskContribution:
        """
        Расчет вклада прочего пассива в риски.
        """
        contribution = RiskContribution(
            instrument_id=self.instrument_id,
            instrument_type=self.instrument_type
        )

        # === Interest Rate Risk ===
        # Прочие пассивы обычно не имеют процентного риска
        if self.maturity_date and self.interest_rate:
            contribution.repricing_date = self.maturity_date
            contribution.repricing_amount = -self.amount  # Пассив

            years_to_maturity = (self.maturity_date - calculation_date).days / 365.25
            contribution.duration = years_to_maturity
            contribution.modified_duration = years_to_maturity / (1 + self.interest_rate)
            # Пассив - отрицательный DV01
            contribution.dv01 = -self.amount * Decimal(contribution.modified_duration) * Decimal(0.0001)
        else:
            contribution.repricing_date = None
            contribution.repricing_amount = Decimal(0)

        # === Liquidity Risk ===
        cash_flows = self._generate_cash_flows(calculation_date, assumptions)

        liquidity_buckets = risk_params.get('liquidity_buckets', [
            '0-30d', '30-90d', '90-180d', '180-365d', '1-2y', '2y+'
        ])

        for cf_date, cf_amount in cash_flows.items():
            bucket = assign_to_bucket(calculation_date, cf_date, liquidity_buckets)
            contribution.cash_flows[bucket] = contribution.cash_flows.get(bucket, Decimal(0)) + cf_amount

        # === FX Risk ===
        # Только денежные обязательства имеют валютный риск
        if self.is_monetary:
            contribution.currency_exposure[self.currency] = -self.amount  # Пассив

        logger.debug(
            f"Calculated risk contribution for Other Liability {self.instrument_id}",
            extra={
                'instrument_id': self.instrument_id,
                'liability_category': self.liability_category,
                'amount': float(self.amount)
            }
        )

        return contribution

    def _generate_cash_flows(
        self,
        calculation_date: date,
        assumptions: Optional[Dict] = None
    ) -> Dict[date, Decimal]:
        """
        Генерирует денежные потоки прочего пассива.

        Логика зависит от типа обязательства:
        - Кредиторская задолженность: дата платежа
        - Расчеты с персоналом: зарплатный график
        - Резервы: когда ожидается использование
        """
        cash_flows = {}

        if self.maturity_date and self.maturity_date >= calculation_date:
            # Есть четкая дата погашения
            # Outflow (отток денег)
            cash_flows[self.maturity_date] = -self.amount

        elif self.liability_category == 'payables':
            # Кредиторская задолженность
            if assumptions and 'payables_payment_days' in assumptions:
                payment_days = assumptions['payables_payment_days']
            else:
                payment_days = 30  # Default 30 дней

            cash_flows[calculation_date + timedelta(days=payment_days)] = -self.amount

        elif self.liability_category == 'payroll':
            # Расчеты с персоналом: обычно краткосрочные
            if assumptions and 'payroll_payment_days' in assumptions:
                payment_days = assumptions['payroll_payment_days']
            else:
                payment_days = 15  # Default 15 дней

            cash_flows[calculation_date + timedelta(days=payment_days)] = -self.amount

        elif self.liability_category == 'reserves':
            # Резервы: неопределенная дата использования
            # Консервативно - среднесрочный горизонт
            if assumptions and 'reserves_utilization_days' in assumptions:
                utilization_days = assumptions['reserves_utilization_days']
            else:
                utilization_days = 365  # Default 1 год

            cash_flows[calculation_date + timedelta(days=utilization_days)] = -self.amount

        return cash_flows

    def apply_assumptions(self, assumptions: Dict) -> 'OtherLiability':
        """
        Применяет behavioral assumptions к прочему пассиву.

        Примеры:
        {
            'payables_payment_days': 30,         # Срок оплаты кредиторки
            'payroll_payment_days': 15,          # Срок выплаты зарплаты
            'reserves_utilization_days': 365     # Ожидаемый срок использования резервов
        }
        """
        logger.debug(
            f"Applied assumptions to Other Liability {self.instrument_id}",
            extra={
                'liability_category': self.liability_category,
                'assumptions': assumptions
            }
        )

        return self
