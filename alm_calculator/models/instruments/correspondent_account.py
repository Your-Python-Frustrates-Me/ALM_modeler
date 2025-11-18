"""
Correspondent Account instrument implementation
Корреспондентские счета (НОСТРО и ЛОРО)
"""
from typing import Dict, Optional
from datetime import date, timedelta

import logging

from alm_calculator.core.base_instrument import BaseInstrument, InstrumentType, RiskContribution
from alm_calculator.utils.date_utils import assign_to_bucket

logger = logging.getLogger(__name__)


class CorrespondentAccount(BaseInstrument):
    """
    Корреспондентский счет.

    Типы:
    - НОСТРО (Nostro): Счет банка в другом банке (актив, amount > 0)
    - ЛОРО (Loro): Счет другого банка у нас (пассив, amount < 0)
    - Корсчет в ЦБ РФ: Обязательный резерв + операционный остаток

    Особенности:
    - Не имеет фиксированной даты погашения (demand)
    - Обычно не приносит процентов или минимальная ставка
    - Критичен для ликвидности (особенно корсчет в ЦБ)
    - Высоколиквидный актив (НОСТРО) или нестабильный пассив (ЛОРО)
    """

    instrument_type: InstrumentType = InstrumentType.CORRESPONDENT_ACCOUNT

    # Корсчета не имеют maturity_date
    maturity_date: Optional[date] = None

    # Специфичные атрибуты
    account_type: str  # 'nostro', 'loro', 'cbr_required_reserve', 'cbr_operational'
    correspondent_bank: Optional[str] = None  # Название банка-корреспондента
    is_required_reserve: bool = False  # Является ли частью обязательных резервов
    reserve_ratio: Optional[float] = None  # Норматив резервирования (для ЦБ)

    # По умолчанию контрагент - банк или ЦБ
    counterparty_type: str = 'bank'

    def __init__(self, **data):
        super().__init__(**data)
        # Устанавливаем counterparty_type в зависимости от account_type
        if self.account_type in ['cbr_required_reserve', 'cbr_operational']:
            self.counterparty_type = 'central_bank'

    def calculate_risk_contribution(
        self,
        calculation_date: date,
        risk_params: Dict,
        assumptions: Optional[Dict] = None
    ) -> RiskContribution:
        """
        Расчет вклада корсчета в риски.
        """
        contribution = RiskContribution(
            instrument_id=self.instrument_id,
            instrument_type=self.instrument_type
        )

        # === Interest Rate Risk ===
        # Корсчета: минимальный процентный риск (overnight repricing)
        contribution.repricing_date = calculation_date + timedelta(days=1)

        # Определяем знак amount для repricing
        if self.account_type in ['nostro', 'cbr_required_reserve', 'cbr_operational']:
            # Актив
            contribution.repricing_amount = self.amount
        else:
            # ЛОРО - пассив
            contribution.repricing_amount = -self.amount

        # Duration ~ 0 для overnight instruments
        contribution.duration = 1 / 365.25
        contribution.modified_duration = contribution.duration

        # === Liquidity Risk ===
        cash_flows = self._generate_cash_flows(calculation_date, assumptions)

        liquidity_buckets = risk_params.get('liquidity_buckets', [
            'overnight', '2-7d', '8-14d', '15-30d', '30-90d'
        ])

        for cf_date, cf_amount in cash_flows.items():
            bucket = assign_to_bucket(calculation_date, cf_date, liquidity_buckets)
            contribution.cash_flows[bucket] = contribution.cash_flows.get(bucket, 0.0) + cf_amount

        # === FX Risk ===
        # НОСТРО и корсчет в ЦБ - актив
        # ЛОРО - пассив
        if self.account_type in ['nostro', 'cbr_required_reserve', 'cbr_operational']:
            contribution.currency_exposure[self.currency] = self.amount
        else:
            contribution.currency_exposure[self.currency] = -self.amount

        logger.debug(
            f"Calculated risk contribution for {self.account_type} {self.instrument_id}",
            extra={
                'instrument_id': self.instrument_id,
                'account_type': self.account_type,
                'amount': float(self.amount),
                'is_required_reserve': self.is_required_reserve
            }
        )

        return contribution

    def _generate_cash_flows(
        self,
        calculation_date: date,
        assumptions: Optional[Dict] = None
    ) -> Dict[date, float]:
        """
        Генерирует денежные потоки корсчета.

        Логика:
        - Обязательные резервы (required reserve): не могут быть использованы (immobile)
        - Операционный остаток: высоколиквидный (overnight availability)
        - НОСТРО: обычно стабильный остаток для операций
        - ЛОРО: может быть изъят контрагентом
        """
        cash_flows = {}

        if self.account_type == 'cbr_required_reserve':
            # Обязательные резервы: не доступны для использования
            # Учитываем как immobile или очень долгосрочный
            if assumptions and 'required_reserve_horizon_days' in assumptions:
                horizon = assumptions['required_reserve_horizon_days']
            else:
                horizon = 365  # По умолчанию: 1 год (консервативно)

            cash_flows[calculation_date + timedelta(days=horizon)] = self.amount

        elif self.account_type == 'cbr_operational':
            # Операционный остаток в ЦБ: высоколиквидный актив (overnight)
            cash_flows[calculation_date + timedelta(days=1)] = self.amount

        elif self.account_type == 'nostro':
            # НОСТРО: стабильный operational остаток
            # Обычно сохраняется минимальный остаток для операций
            if assumptions and 'nostro_stable_portion' in assumptions:
                stable_portion = assumptions['nostro_stable_portion']
                operational_amount = self.amount * float(1 - stable_portion)
                stable_amount = self.amount * float(stable_portion)

                # Operational часть: доступна overnight
                cash_flows[calculation_date + timedelta(days=1)] = operational_amount
                # Stable часть: сохраняется долго
                cash_flows[calculation_date + timedelta(days=90)] = stable_amount
            else:
                # По умолчанию: весь остаток доступен overnight
                cash_flows[calculation_date + timedelta(days=1)] = self.amount

        elif self.account_type == 'loro':
            # ЛОРО: пассив, может быть изъят контрагентом
            # Моделируем как unstable funding
            if assumptions and 'loro_runoff_days' in assumptions:
                runoff_days = assumptions['loro_runoff_days']
            else:
                runoff_days = 7  # По умолчанию: неделя

            # Outflow
            cash_flows[calculation_date + timedelta(days=runoff_days)] = -self.amount

        return cash_flows

    def apply_assumptions(self, assumptions: Dict) -> 'CorrespondentAccount':
        """
        Применяет behavioral assumptions к корсчету.

        Примеры assumptions:
        {
            # Для обязательных резервов:
            'required_reserve_horizon_days': 365,

            # Для НОСТРО:
            'nostro_stable_portion': 0.70,  # 70% - стабильный operational остаток

            # Для ЛОРО:
            'loro_runoff_days': 7  # Ожидаемый срок до изъятия
        }
        """
        logger.debug(
            f"Applied assumptions to {self.account_type} {self.instrument_id}",
            extra={
                'account_type': self.account_type,
                'assumptions': assumptions
            }
        )

        return self
