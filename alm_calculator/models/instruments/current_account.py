"""
Current Account instrument implementation
Текущие счета
"""
from typing import Dict, Optional
from datetime import date, timedelta

import logging

from alm_calculator.core.base_instrument import BaseInstrument, InstrumentType, RiskContribution
from alm_calculator.utils.date_utils import assign_to_bucket

logger = logging.getLogger(__name__)


class CurrentAccount(BaseInstrument):
    """
    Текущий счет (расчетный счет клиента).

    Особенности:
    - Пассив (обязательство банка перед клиентом)
    - Не имеет фиксированной даты погашения (demand deposit)
    - Обычно не приносит процентов или минимальная ставка
    - Очень волатильный остаток (транзакционные счета)
    - Критичны behavioral assumptions для моделирования стабильности
    - Важны для ликвидности (могут быть изъяты в любой момент)

    Типы:
    - Текущие счета юрлиц (корпоративные)
    - Текущие счета физлиц
    - Текущие счета государственных организаций
    """

    instrument_type: InstrumentType = InstrumentType.CURRENT_ACCOUNT

    # Текущие счета не имеют maturity_date
    maturity_date: Optional[date] = None

    # Специфичные атрибуты
    is_transactional: bool = True  # Является ли счет транзакционным
    avg_balance_30d: Optional[float] = None  # Средний остаток за 30 дней
    volatility_coefficient: Optional[float] = None  # Коэффициент волатильности остатков
    stable_portion: Optional[float] = None  # Устойчивая часть остатка (0-1)
    avg_life_days: Optional[int] = None  # Условный срок жизни устойчивой части

    # По умолчанию процентная ставка минимальная или нулевая
    interest_rate: Optional[float] = 0.0

    def calculate_risk_contribution(
        self,
        calculation_date: date,
        risk_params: Dict,
        assumptions: Optional[Dict] = None
    ) -> RiskContribution:
        """
        Расчет вклада текущего счета в риски.
        """
        contribution = RiskContribution(
            instrument_id=self.instrument_id,
            instrument_type=self.instrument_type
        )

        # === Interest Rate Risk ===
        # Текущие счета: repricing определяется behavioral assumptions
        if self.stable_portion and self.avg_life_days:
            # Устойчивая часть имеет условный срок
            repricing_days = self.avg_life_days
            contribution.repricing_date = calculation_date + timedelta(days=repricing_days)
            contribution.repricing_amount = -self.amount * float(self.stable_portion)
        else:
            # По умолчанию: очень короткий repricing (1 день)
            contribution.repricing_date = calculation_date + timedelta(days=1)
            contribution.repricing_amount = -self.amount

        # Duration для текущих счетов обычно не считается или очень мала
        if self.avg_life_days and self.stable_portion:
            years = self.avg_life_days / 365.25
            contribution.duration = years * self.stable_portion
            if self.interest_rate:
                contribution.modified_duration = contribution.duration / (1 + self.interest_rate)
                # Пассив - отрицательный DV01
                contribution.dv01 = -self.amount * float(contribution.modified_duration) * float(0.0001)

        # === Liquidity Risk ===
        # Текущие счета - критичный компонент для ликвидности
        cash_flows = self._generate_cash_flows(calculation_date, assumptions)

        liquidity_buckets = risk_params.get('liquidity_buckets', [
            'overnight', '2-7d', '8-14d', '15-30d', '30-90d', '90-180d', '180-365d', '1y+'
        ])

        for cf_date, cf_amount in cash_flows.items():
            bucket = assign_to_bucket(calculation_date, cf_date, liquidity_buckets)
            # Текущие счета - это outflow (могут быть изъяты)
            contribution.cash_flows[bucket] = contribution.cash_flows.get(bucket, 0.0) + cf_amount

        # === FX Risk ===
        # Текущие счета - пассив
        contribution.currency_exposure[self.currency] = -self.amount

        logger.debug(
            f"Calculated risk contribution for Current Account {self.instrument_id}",
            extra={
                'instrument_id': self.instrument_id,
                'amount': float(self.amount),
                'counterparty_type': self.counterparty_type,
                'stable_portion': self.stable_portion
            }
        )

        return contribution

    def _generate_cash_flows(
        self,
        calculation_date: date,
        assumptions: Optional[Dict] = None
    ) -> Dict[date, float]:
        """
        Генерирует денежные потоки текущего счета с учетом behavioral assumptions.

        Логика:
        - Unstable часть (волатильная) распределяется по runoff rates
        - Stable часть остается на условный срок
        """
        cash_flows = {}

        # Определяем stable и unstable части
        stable_portion = self.stable_portion if self.stable_portion is not None else 0.3  # Default 30%
        unstable_amount = self.amount * float(1 - stable_portion)
        stable_amount = self.amount * float(stable_portion)

        # Unstable часть: применяем runoff rates
        if assumptions and 'runoff_rates' in assumptions:
            runoff_rates = assumptions['runoff_rates']
            remaining = unstable_amount

            for bucket, rate in sorted(runoff_rates.items()):
                runoff_amount = remaining * float(rate)
                bucket_date = self._bucket_to_date(calculation_date, bucket)
                # Outflow (отток средств)
                cash_flows[bucket_date] = cash_flows.get(bucket_date, 0.0) - runoff_amount
                remaining -= runoff_amount

            # Остаток unstable части через 30 дней
            if remaining > 0:
                cash_flows[calculation_date + timedelta(days=30)] = \
                    cash_flows.get(calculation_date + timedelta(days=30), 0.0) - remaining
        else:
            # По умолчанию: unstable часть может быть изъята моментально
            cash_flows[calculation_date + timedelta(days=1)] = -unstable_amount

        # Stable часть: остается на условный срок
        stable_days = self.avg_life_days if self.avg_life_days else 180  # Default 180 дней
        stable_date = calculation_date + timedelta(days=stable_days)
        cash_flows[stable_date] = cash_flows.get(stable_date, 0.0) - stable_amount

        return cash_flows

    def _bucket_to_date(self, base_date: date, bucket: str) -> date:
        """Конвертирует название бакета в дату (середина бакета)"""
        bucket_days_mapping = {
            'overnight': 1,
            '2-7d': 4,
            '8-14d': 11,
            '15-30d': 22,
            '30-90d': 60,
            '90-180d': 135,
            '180-365d': 270,
            '1y+': 548
        }
        days = bucket_days_mapping.get(bucket, 30)
        return base_date + timedelta(days=days)

    def apply_assumptions(self, assumptions: Dict) -> 'CurrentAccount':
        """
        Применяет behavioral assumptions к текущему счету.

        Пример для корпоративного текущего счета:
        {
            'stable_portion': 0.40,        # 40% - устойчивая часть
            'avg_life_days': 180,           # Устойчивая часть ~6 месяцев
            'runoff_rates': {               # Runoff для неустойчивой части
                'overnight': 0.05,
                '2-7d': 0.10,
                '8-14d': 0.15,
                '15-30d': 0.30
            }
        }

        Для физлиц stable_portion может быть выше (50-60%).
        Для госучреждений - еще выше (70-80%).
        """
        if 'stable_portion' in assumptions:
            self.stable_portion = assumptions['stable_portion']

        if 'avg_life_days' in assumptions:
            self.avg_life_days = assumptions['avg_life_days']

        logger.debug(
            f"Applied assumptions to Current Account {self.instrument_id}",
            extra={
                'stable_portion': self.stable_portion,
                'avg_life_days': self.avg_life_days
            }
        )

        return self
