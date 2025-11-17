# models/instruments/deposit.py
from typing import Dict, List, Optional
from datetime import date, timedelta
from decimal import Decimal

from core.base_instrument import BaseInstrument, InstrumentType, RiskContribution
from utils.date_utils import assign_to_bucket


class Deposit(BaseInstrument):
    """
    Депозитный инструмент.

    Особенности:
    - Пассив (amount < 0 в балансе, но здесь храним abs)
    - Может быть срочным или до востребования (NMD)
    - Для NMD критичны behavioral assumptions
    """

    instrument_type: InstrumentType = InstrumentType.DEPOSIT

    # Специфичные атрибуты
    is_demand_deposit: bool = False  # До востребования (NMD)
    core_portion: Optional[float] = None  # Устойчивая часть для NMD (0-1)
    avg_life_years: Optional[float] = None  # Условный срок для NMD
    withdrawal_rates: Optional[Dict[str, float]] = None  # Rates of runoff по бакетам

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

    # Параметры досрочного изъятия
    early_withdrawal_allowed: bool = False  # Возможность досрочного изъятия
    early_withdrawal_start_date: Optional[date] = None  # Дата начала возможности досрочного изъятия
    early_withdrawal_end_date: Optional[date] = None  # Дата окончания возможности досрочного изъятия
    minimum_balance: Optional[Decimal] = None  # Минимальный остаток на счете

    def calculate_risk_contribution(
            self,
            calculation_date: date,
            risk_params: Dict,
            assumptions: Optional[Dict] = None
    ) -> RiskContribution:
        """
        Расчет вклада депозита в риски.
        """
        contribution = RiskContribution(
            instrument_id=self.instrument_id,
            instrument_type=self.instrument_type
        )

        # === Interest Rate Risk ===
        if self.is_demand_deposit:
            # NMD: repricing date определяется через behavioral assumptions
            if self.avg_life_years:
                repricing_days = int(self.avg_life_years * 365.25)
                contribution.repricing_date = calculation_date + timedelta(days=repricing_days)
            else:
                # По умолчанию: overnight
                contribution.repricing_date = calculation_date + timedelta(days=1)
        else:
            # Срочный депозит: используем maturity_date
            contribution.repricing_date = self.maturity_date

        # Amount для repricing (с учетом core portion для NMD)
        if self.is_demand_deposit and self.core_portion:
            contribution.repricing_amount = self.amount * Decimal(self.core_portion)
        else:
            contribution.repricing_amount = self.amount

        # Duration для срочных депозитов
        if not self.is_demand_deposit and self.maturity_date and self.interest_rate:
            years_to_maturity = (self.maturity_date - calculation_date).days / 365.25
            contribution.duration = years_to_maturity
            contribution.modified_duration = years_to_maturity / (1 + self.interest_rate)
            contribution.dv01 = -self.amount * contribution.modified_duration * Decimal(0.0001)

        # === Liquidity Risk ===
        cash_flows = self._generate_cash_flows(calculation_date, assumptions)

        liquidity_buckets = risk_params.get('liquidity_buckets', [
            '0-30d', '30-90d', '90-180d', '180-365d', '1-2y', '2y+'
        ])

        for cf_date, cf_amount in cash_flows.items():
            bucket = assign_to_bucket(calculation_date, cf_date, liquidity_buckets)
            # Депозиты - это outflow (отрицательный CF)
            contribution.cash_flows[bucket] = contribution.cash_flows.get(bucket, Decimal(0)) - cf_amount

        # === FX Risk ===
        # Депозиты - пассив, поэтому отрицательная позиция
        contribution.currency_exposure[self.currency] = -self.amount

        return contribution

    def _generate_cash_flows(
            self,
            calculation_date: date,
            assumptions: Optional[Dict] = None
    ) -> Dict[date, Decimal]:
        """
        Генерирует денежные потоки депозита.

        Для NMD: применяет withdrawal/runoff rates
        Для срочных: дата погашения
        """
        cash_flows = {}

        if self.is_demand_deposit:
            # NMD: распределяем по runoff rates
            if self.withdrawal_rates:
                remaining_balance = self.amount

                for bucket, rate in sorted(self.withdrawal_rates.items()):
                    withdrawal_amount = remaining_balance * Decimal(rate)
                    # Определяем среднюю дату в бакете
                    bucket_mid_date = self._bucket_to_date(calculation_date, bucket)
                    cash_flows[bucket_mid_date] = withdrawal_amount
                    remaining_balance -= withdrawal_amount

                # Остаток - устойчивая часть
                if remaining_balance > 0:
                    if self.avg_life_years:
                        stable_date = calculation_date + timedelta(days=int(self.avg_life_years * 365.25))
                    else:
                        stable_date = calculation_date + timedelta(days=3 * 365)  # Default: 3 года
                    cash_flows[stable_date] = remaining_balance
            else:
                # По умолчанию: overnight
                cash_flows[calculation_date + timedelta(days=1)] = self.amount

        else:
            # Срочный депозит: единая дата погашения
            if self.maturity_date and self.maturity_date >= calculation_date:
                cash_flows[self.maturity_date] = self.amount

        return cash_flows

    def _bucket_to_date(self, base_date: date, bucket: str) -> date:
        """Конвертирует название бакета в дату (середина бакета)"""
        # Простая логика для примера
        bucket_days = {
            '0-30d': 15,
            '30-90d': 60,
            '90-180d': 135,
            '180-365d': 270,
            '1-2y': 548,
            '2y+': 1095
        }
        days = bucket_days.get(bucket, 180)
        return base_date + timedelta(days=days)

    def apply_assumptions(self, assumptions: Dict) -> 'Deposit':
        """
        Применяет behavioral assumptions к депозиту.

        Пример для NMD:
        {
            'core_portion': 0.70,
            'avg_life_years': 3.0,
            'withdrawal_rates': {
                '0-30d': 0.10,
                '30-90d': 0.15,
                '90-180d': 0.05
            }
        }
        """
        if 'core_portion' in assumptions:
            self.core_portion = assumptions['core_portion']

        if 'avg_life_years' in assumptions:
            self.avg_life_years = assumptions['avg_life_years']

        if 'withdrawal_rates' in assumptions:
            self.withdrawal_rates = assumptions['withdrawal_rates']

        return self
