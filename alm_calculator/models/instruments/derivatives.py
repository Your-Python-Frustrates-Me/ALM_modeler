"""
Derivative instruments implementation
Производные финансовые инструменты (ПФИ)
"""
from typing import Dict, Optional
from datetime import date

import logging

from alm_calculator.core.base_instrument import BaseInstrument, InstrumentType, RiskContribution
from alm_calculator.utils.date_utils import assign_to_bucket

logger = logging.getLogger(__name__)


class BaseDerivative(BaseInstrument):
    """
    Базовый класс для всех производных инструментов.

    Общие атрибуты для всех ПФИ.
    """

    instrument_type: InstrumentType = InstrumentType.DERIVATIVE

    # Базовые параметры ПФИ
    notional_amount: Optional[float] = None  # Номинальная стоимость контракта
    settlement_date: Optional[date] = None  # Дата расчетов/экспирации
    underlying_asset: Optional[str] = None  # Базовый актив
    derivative_type: Optional[str] = None  # Тип деривативa (IRS, FxSwap, etc.)

    # Дополнительные поля для классификации и учета
    instrument_class: Optional[str] = None  # Класс инструмента
    instrument_subclass: Optional[str] = None  # Подкласс инструмента
    counterparty_name: Optional[str] = None  # Имя контрагента

    # Параметры процентных платежей
    is_interest: bool = False  # False - платеж тела, True - процентный платеж

    # Параметры ставки
    is_fix: bool = True  # True - фиксированная ставка, False - плавающая
    fix_rate: Optional[float] = None  # Фиксированная ставка
    float_indicator: Optional[str] = None  # Индикатор плавающей ставки
    float_margin: Optional[float] = None  # Маржа плавающей ставки

    # Дополнительные даты
    trade_date: Optional[date] = None  # Дата заключения сделки

    # Портфельная принадлежность
    trading_portfolio: Optional[str] = None  # Торговый портфель

    # Параметры маржи
    initial_margin: Optional[float] = None  # Начальная маржа
    variation_margin: Optional[float] = None  # Вариационная маржа

    def calculate_risk_contribution(
        self,
        calculation_date: date,
        risk_params: Dict,
        assumptions: Optional[Dict] = None
    ) -> RiskContribution:
        """
        Базовый расчет вклада деривативa в риски.
        Должен быть переопределен в подклассах.
        """
        contribution = RiskContribution(
            instrument_id=self.instrument_id,
            instrument_type=self.instrument_type
        )

        # Базовые расчеты будут переопределены в подклассах
        return contribution

    def apply_assumptions(self, assumptions: Dict) -> 'BaseDerivative':
        """
        Применяет behavioral assumptions к деривативу.
        """
        return self


class IRS(BaseDerivative):
    """
    Interest Rate Swap (IRS) - Процентный своп.

    Обмен фиксированных процентных платежей на плавающие.
    """

    derivative_type: str = "IRS"

    # Параметры фиксированной ноги
    fixed_rate: Optional[float] = None  # Фиксированная ставка
    fixed_leg_frequency: Optional[int] = None  # Частота платежей по фиксированной ноге (в днях)

    # Параметры плавающей ноги
    floating_rate_index: Optional[str] = None  # Индекс плавающей ставки (RUONIA, KeyRate)
    floating_spread: Optional[float] = None  # Спред к плавающей ставке
    floating_leg_frequency: Optional[int] = None  # Частота платежей по плавающей ноге

    # Направление свопа
    is_payer: bool = True  # True - платим фикс, получаем float; False - наоборот

    def calculate_risk_contribution(
        self,
        calculation_date: date,
        risk_params: Dict,
        assumptions: Optional[Dict] = None
    ) -> RiskContribution:
        """
        Расчет вклада IRS в риски.
        """
        contribution = RiskContribution(
            instrument_id=self.instrument_id,
            instrument_type=self.instrument_type
        )

        # === Interest Rate Risk ===
        # IRS имеет две ноги с разными repricing dates
        if self.settlement_date or self.maturity_date:
            contribution.repricing_date = self.settlement_date or self.maturity_date
            # Для payer swap: короткая позиция по фикс, длинная по float
            # Для receiver swap: длинная по фикс, короткая по float
            sign = 1 if self.is_payer else -1
            contribution.repricing_amount = (self.notional_amount or self.amount) * sign

        # Duration calculation для IRS (упрощенный)
        if contribution.repricing_date and self.fixed_rate:
            years_to_maturity = (contribution.repricing_date - calculation_date).days / 365.25
            contribution.duration = years_to_maturity / 2  # Приблизительно
            contribution.modified_duration = contribution.duration / (1 + self.fixed_rate)
            contribution.dv01 = (self.notional_amount or self.amount) * float(contribution.modified_duration) * float(0.0001) * sign

        # === Liquidity Risk ===
        cash_flows = self._generate_cash_flows(calculation_date)
        liquidity_buckets = risk_params.get('liquidity_buckets', [
            '0-30d', '30-90d', '90-180d', '180-365d', '1-2y', '2-5y', '5y+'
        ])

        for cf_date, cf_amount in cash_flows.items():
            bucket = assign_to_bucket(calculation_date, cf_date, liquidity_buckets)
            contribution.cash_flows[bucket] = contribution.cash_flows.get(bucket, 0.0) + cf_amount

        # === FX Risk ===
        contribution.currency_exposure[self.currency] = self.amount

        logger.debug(
            f"Calculated risk contribution for IRS {self.instrument_id}",
            extra={
                'instrument_id': self.instrument_id,
                'is_payer': self.is_payer,
                'notional': float(self.notional_amount) if self.notional_amount else None
            }
        )

        return contribution

    def _generate_cash_flows(self, calculation_date: date) -> Dict[date, float]:
        """
        Генерирует денежные потоки IRS.
        Упрощенная модель: нетто CF между фикс и float ногами.
        """
        cash_flows = {}
        # TODO: Реализовать полную модель генерации CF для обеих ног
        return cash_flows


class FxSwap(BaseDerivative):
    """
    Foreign Exchange Swap (FX Swap) - Валютный своп.

    Комбинация спот и форвардной валютной сделки.
    """

    derivative_type: str = "FxSwap"

    # Параметры валютного свопа
    base_currency: Optional[str] = None  # Базовая валюта
    quote_currency: Optional[str] = None  # Котируемая валюта
    spot_rate: Optional[float] = None  # Спот курс
    forward_rate: Optional[float] = None  # Форвардный курс
    swap_points: Optional[float] = None  # Своп-пойнты

    # Даты
    near_leg_date: Optional[date] = None  # Дата ближней ноги (обычно спот)
    far_leg_date: Optional[date] = None  # Дата дальней ноги (форвард)

    # Направление
    is_buy: bool = True  # True - покупка базовой валюты на near leg

    def calculate_risk_contribution(
        self,
        calculation_date: date,
        risk_params: Dict,
        assumptions: Optional[Dict] = None
    ) -> RiskContribution:
        """
        Расчет вклада FX Swap в риски.
        """
        contribution = RiskContribution(
            instrument_id=self.instrument_id,
            instrument_type=self.instrument_type
        )

        # === FX Risk ===
        # FX Swap создает валютные позиции на обеих ногах
        if self.base_currency and self.quote_currency:
            sign = 1 if self.is_buy else -1
            notional = self.notional_amount or self.amount
            contribution.currency_exposure[self.base_currency] = notional * sign
            contribution.currency_exposure[self.quote_currency] = -notional * sign

        # === Liquidity Risk ===
        cash_flows = self._generate_cash_flows(calculation_date)
        liquidity_buckets = risk_params.get('liquidity_buckets', [
            '0-7d', '7-30d', '30-90d', '90-180d', '180-365d'
        ])

        for cf_date, cf_amount in cash_flows.items():
            bucket = assign_to_bucket(calculation_date, cf_date, liquidity_buckets)
            contribution.cash_flows[bucket] = contribution.cash_flows.get(bucket, 0.0) + cf_amount

        logger.debug(
            f"Calculated risk contribution for FxSwap {self.instrument_id}",
            extra={
                'instrument_id': self.instrument_id,
                'base_currency': self.base_currency,
                'quote_currency': self.quote_currency
            }
        )

        return contribution

    def _generate_cash_flows(self, calculation_date: date) -> Dict[date, float]:
        """
        Генерирует денежные потоки FX Swap (в базовой валюте).
        """
        cash_flows = {}

        if self.near_leg_date and self.near_leg_date >= calculation_date:
            sign = 1 if self.is_buy else -1
            cash_flows[self.near_leg_date] = (self.notional_amount or self.amount) * sign

        if self.far_leg_date and self.far_leg_date >= calculation_date:
            sign = -1 if self.is_buy else 1
            cash_flows[self.far_leg_date] = (self.notional_amount or self.amount) * sign

        return cash_flows


class Futures(BaseDerivative):
    """
    Futures - Фьючерсный контракт.

    Стандартизированный биржевой контракт на покупку/продажу актива.
    """

    derivative_type: str = "Futures"

    # Параметры фьючерса
    contract_size: Optional[float] = None  # Размер контракта
    tick_size: Optional[float] = None  # Минимальный шаг цены
    futures_price: Optional[float] = None  # Цена фьючерса
    expiration_date: Optional[date] = None  # Дата экспирации

    # Тип контракта
    futures_type: Optional[str] = None  # Commodity, Currency, Interest Rate, Index

    # Позиция
    is_long: bool = True  # True - длинная позиция, False - короткая
    quantity: Optional[float] = None  # Количество контрактов

    def calculate_risk_contribution(
        self,
        calculation_date: date,
        risk_params: Dict,
        assumptions: Optional[Dict] = None
    ) -> RiskContribution:
        """
        Расчет вклада Futures в риски.
        """
        contribution = RiskContribution(
            instrument_id=self.instrument_id,
            instrument_type=self.instrument_type
        )

        # === Market Risk ===
        sign = 1 if self.is_long else -1
        exposure = (self.notional_amount or self.amount) * sign

        # === Liquidity Risk ===
        if self.expiration_date and self.expiration_date >= calculation_date:
            liquidity_buckets = risk_params.get('liquidity_buckets', [
                '0-30d', '30-90d', '90-180d', '180-365d'
            ])
            bucket = assign_to_bucket(calculation_date, self.expiration_date, liquidity_buckets)
            # Расчеты по фьючерсу происходят при экспирации
            contribution.cash_flows[bucket] = exposure

        # === Currency Exposure ===
        contribution.currency_exposure[self.currency] = exposure

        logger.debug(
            f"Calculated risk contribution for Futures {self.instrument_id}",
            extra={
                'instrument_id': self.instrument_id,
                'is_long': self.is_long,
                'futures_type': self.futures_type
            }
        )

        return contribution


class OIS(BaseDerivative):
    """
    Overnight Index Swap (OIS) - Своп на овернайт индекс.

    Процентный своп, где плавающая нога привязана к овернайт ставке.
    """

    derivative_type: str = "OIS"

    # Параметры OIS (похожи на IRS, но с особенностями)
    fixed_rate: Optional[float] = None  # Фиксированная ставка OIS
    overnight_index: Optional[str] = None  # Индекс овернайт (например, RUONIA)

    # Направление
    is_payer: bool = True  # True - платим фикс, получаем float

    # Особенности расчета
    compounding_method: Optional[str] = None  # Метод компаундирования (daily, etc.)

    def calculate_risk_contribution(
        self,
        calculation_date: date,
        risk_params: Dict,
        assumptions: Optional[Dict] = None
    ) -> RiskContribution:
        """
        Расчет вклада OIS в риски (аналогично IRS).
        """
        contribution = RiskContribution(
            instrument_id=self.instrument_id,
            instrument_type=self.instrument_type
        )

        # Логика похожа на IRS
        if self.settlement_date or self.maturity_date:
            contribution.repricing_date = self.settlement_date or self.maturity_date
            sign = 1 if self.is_payer else -1
            contribution.repricing_amount = (self.notional_amount or self.amount) * sign

        # Duration
        if contribution.repricing_date and self.fixed_rate:
            years_to_maturity = (contribution.repricing_date - calculation_date).days / 365.25
            contribution.duration = years_to_maturity / 2
            contribution.modified_duration = contribution.duration / (1 + self.fixed_rate)
            contribution.dv01 = (self.notional_amount or self.amount) * float(contribution.modified_duration) * float(0.0001) * sign

        contribution.currency_exposure[self.currency] = self.amount

        logger.debug(
            f"Calculated risk contribution for OIS {self.instrument_id}",
            extra={
                'instrument_id': self.instrument_id,
                'overnight_index': self.overnight_index
            }
        )

        return contribution


class TOM(BaseDerivative):
    """
    TOM (Tomorrow) - Сделка Том.

    Валютная сделка с датой расчетов на следующий рабочий день.
    """

    derivative_type: str = "TOM"

    # Параметры сделки TOM
    base_currency: Optional[str] = None  # Базовая валюта
    quote_currency: Optional[str] = None  # Котируемая валюта
    exchange_rate: Optional[float] = None  # Курс обмена

    # Направление
    is_buy: bool = True  # True - покупка базовой валюты

    def calculate_risk_contribution(
        self,
        calculation_date: date,
        risk_params: Dict,
        assumptions: Optional[Dict] = None
    ) -> RiskContribution:
        """
        Расчет вклада TOM в риски.
        """
        contribution = RiskContribution(
            instrument_id=self.instrument_id,
            instrument_type=self.instrument_type
        )

        # === FX Risk ===
        if self.base_currency and self.quote_currency:
            sign = 1 if self.is_buy else -1
            notional = self.notional_amount or self.amount
            contribution.currency_exposure[self.base_currency] = notional * sign
            contribution.currency_exposure[self.quote_currency] = -notional * sign

        # === Liquidity Risk ===
        # TOM - очень короткий срок (T+1)
        from datetime import timedelta
        settlement = calculation_date + timedelta(days=1)
        if settlement >= calculation_date:
            liquidity_buckets = risk_params.get('liquidity_buckets', ['overnight', '2-7d'])
            bucket = assign_to_bucket(calculation_date, settlement, liquidity_buckets)
            sign = 1 if self.is_buy else -1
            contribution.cash_flows[bucket] = (self.notional_amount or self.amount) * sign

        logger.debug(
            f"Calculated risk contribution for TOM {self.instrument_id}",
            extra={'instrument_id': self.instrument_id}
        )

        return contribution


class DepositMargin(BaseDerivative):
    """
    Депозитная маржа СПФИ НКЦ.

    Маржинальное обеспечение для сделок с производными инструментами.
    """

    derivative_type: str = "DepositMargin"

    # Параметры маржи
    margin_type: Optional[str] = None  # Тип маржи (initial, variation, etc.)
    clearing_house: Optional[str] = None  # Клиринговая организация (НКЦ)
    margin_currency: Optional[str] = None  # Валюта маржи

    # Связанные контракты
    related_contracts: Optional[str] = None  # ID связанных деривативов

    def calculate_risk_contribution(
        self,
        calculation_date: date,
        risk_params: Dict,
        assumptions: Optional[Dict] = None
    ) -> RiskContribution:
        """
        Расчет вклада депозитной маржи в риски.
        """
        contribution = RiskContribution(
            instrument_id=self.instrument_id,
            instrument_type=self.instrument_type
        )

        # Маржа - это актив (замороженные средства)
        contribution.currency_exposure[self.margin_currency or self.currency] = self.amount

        # === Liquidity Risk ===
        # Маржа обычно может быть возвращена при закрытии позиций
        # Предполагаем среднесрочную ликвидность
        if self.maturity_date and self.maturity_date >= calculation_date:
            liquidity_buckets = risk_params.get('liquidity_buckets', [
                '0-30d', '30-90d', '90-180d'
            ])
            bucket = assign_to_bucket(calculation_date, self.maturity_date, liquidity_buckets)
            contribution.cash_flows[bucket] = self.amount

        logger.debug(
            f"Calculated risk contribution for DepositMargin {self.instrument_id}",
            extra={
                'instrument_id': self.instrument_id,
                'margin_type': self.margin_type
            }
        )

        return contribution


class Forward(BaseDerivative):
    """
    Forward - Форвардный контракт.

    Внебиржевой контракт на покупку/продажу актива в будущем.
    """

    derivative_type: str = "Forward"

    # Параметры форварда
    forward_price: Optional[float] = None  # Форвардная цена
    spot_price: Optional[float] = None  # Спот цена на момент заключения
    delivery_date: Optional[date] = None  # Дата поставки

    # Тип форварда
    forward_type: Optional[str] = None  # Currency, Commodity, Interest Rate

    # Позиция
    is_long: bool = True  # True - длинная позиция (покупатель)

    # Параметры поставки
    settlement_type: Optional[str] = None  # Physical или Cash settlement

    def calculate_risk_contribution(
        self,
        calculation_date: date,
        risk_params: Dict,
        assumptions: Optional[Dict] = None
    ) -> RiskContribution:
        """
        Расчет вклада Forward в риски.
        """
        contribution = RiskContribution(
            instrument_id=self.instrument_id,
            instrument_type=self.instrument_type
        )

        # === Market Risk ===
        sign = 1 if self.is_long else -1
        exposure = (self.notional_amount or self.amount) * sign

        # === Liquidity Risk ===
        delivery = self.delivery_date or self.settlement_date or self.maturity_date
        if delivery and delivery >= calculation_date:
            liquidity_buckets = risk_params.get('liquidity_buckets', [
                '0-30d', '30-90d', '90-180d', '180-365d', '1-2y'
            ])
            bucket = assign_to_bucket(calculation_date, delivery, liquidity_buckets)
            contribution.cash_flows[bucket] = exposure

        # === Currency Exposure ===
        contribution.currency_exposure[self.currency] = exposure

        logger.debug(
            f"Calculated risk contribution for Forward {self.instrument_id}",
            extra={
                'instrument_id': self.instrument_id,
                'is_long': self.is_long,
                'forward_type': self.forward_type
            }
        )

        return contribution


class XCCY(BaseDerivative):
    """
    Cross-Currency Swap (XCCY) - Кросс-валютный своп.

    Обмен процентных платежей и номиналов в разных валютах.
    """

    derivative_type: str = "XCCY"

    # Параметры первой ноги
    leg1_currency: Optional[str] = None  # Валюта первой ноги
    leg1_notional: Optional[float] = None  # Номинал первой ноги
    leg1_rate: Optional[float] = None  # Ставка первой ноги
    leg1_is_fixed: bool = True  # Фиксированная или плавающая

    # Параметры второй ноги
    leg2_currency: Optional[str] = None  # Валюта второй ноги
    leg2_notional: Optional[float] = None  # Номинал второй ноги
    leg2_rate: Optional[float] = None  # Ставка второй ноги
    leg2_is_fixed: bool = False  # Фиксированная или плавающая

    # Обмен номиналами
    exchange_notional_at_start: bool = True  # Обмен номиналами в начале
    exchange_notional_at_maturity: bool = True  # Обмен номиналами в конце

    # Курс обмена
    fx_rate: Optional[float] = None  # FX курс для обмена номиналов

    def calculate_risk_contribution(
        self,
        calculation_date: date,
        risk_params: Dict,
        assumptions: Optional[Dict] = None
    ) -> RiskContribution:
        """
        Расчет вклада XCCY в риски.
        """
        contribution = RiskContribution(
            instrument_id=self.instrument_id,
            instrument_type=self.instrument_type
        )

        # === Interest Rate Risk ===
        # XCCY имеет процентный риск в двух валютах
        if self.settlement_date or self.maturity_date:
            contribution.repricing_date = self.settlement_date or self.maturity_date
            # Эффект зависит от направления ног
            contribution.repricing_amount = self.amount  # Упрощенно

        # === FX Risk ===
        # XCCY создает валютные позиции в обеих валютах
        if self.leg1_currency and self.leg2_currency:
            contribution.currency_exposure[self.leg1_currency] = self.leg1_notional or self.amount
            contribution.currency_exposure[self.leg2_currency] = -(self.leg2_notional or self.amount)

        # === Liquidity Risk ===
        cash_flows = self._generate_cash_flows(calculation_date)
        liquidity_buckets = risk_params.get('liquidity_buckets', [
            '0-30d', '30-90d', '90-180d', '180-365d', '1-2y', '2-5y', '5y+'
        ])

        for cf_date, cf_amount in cash_flows.items():
            bucket = assign_to_bucket(calculation_date, cf_date, liquidity_buckets)
            contribution.cash_flows[bucket] = contribution.cash_flows.get(bucket, 0.0) + cf_amount

        logger.debug(
            f"Calculated risk contribution for XCCY {self.instrument_id}",
            extra={
                'instrument_id': self.instrument_id,
                'leg1_currency': self.leg1_currency,
                'leg2_currency': self.leg2_currency
            }
        )

        return contribution

    def _generate_cash_flows(self, calculation_date: date) -> Dict[date, float]:
        """
        Генерирует денежные потоки XCCY.
        Упрощенная модель.
        """
        cash_flows = {}
        # TODO: Реализовать полную модель с обменом номиналов и процентных платежей
        return cash_flows
