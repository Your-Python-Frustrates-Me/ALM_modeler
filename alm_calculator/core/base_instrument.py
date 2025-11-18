"""
Base classes and interfaces for financial instruments
"""
from abc import ABC, abstractmethod
from typing import Dict, Optional
from datetime import date
from pydantic import BaseModel, Field
from enum import Enum


class InstrumentType(str, Enum):
    """Типы финансовых инструментов"""
    LOAN = "loan"
    DEPOSIT = "deposit"
    BOND = "bond"
    EQUITY = "equity"
    DERIVATIVE = "derivative"
    CASH = "cash"

    # Interbank operations
    INTERBANK_LOAN = "interbank_loan"  # МБК (размещение и привлечение)
    REPO = "repo"  # Прямое РЕПО
    REVERSE_REPO = "reverse_repo"  # Обратное РЕПО

    # Accounts
    CURRENT_ACCOUNT = "current_account"  # Текущие счета
    CORRESPONDENT_ACCOUNT = "correspondent_account"  # Корреспондентские счета и ЛОРО

    # Other balance sheet items
    OTHER_ASSET = "other_asset"  # Прочие активы
    OTHER_LIABILITY = "other_liability"  # Прочие пассивы

    # Off-balance sheet
    OFF_BALANCE = "off_balance"  # Внебалансовые инструменты

    OTHER = "other"


class BookType(str, Enum):
    """
    Классификация инструментов по книгам банка.

    TRADING - Торговая книга (инструменты, предназначенные для торговли)
    BANKING - Банковская книга (инструменты, удерживаемые до погашения)
    """
    TRADING = "trading"
    BANKING = "banking"


class RiskContribution(BaseModel):
    """
    Вклад инструмента в риск-метрики

    Этот класс собирает все риск-метрики для одного инструмента,
    которые затем агрегируются на портфельном уровне.
    """
    instrument_id: str
    instrument_type: InstrumentType

    # Interest Rate Risk
    repricing_amount: float = 0.0
    repricing_date: Optional[date] = None
    duration: Optional[float] = None
    modified_duration: Optional[float] = None
    dv01: Optional[float] = None

    # Liquidity Risk
    cash_flows: Dict[str, float] = Field(default_factory=dict)
    # Ключ - временная корзина ('0-30d'), значение - сумма CF

    # FX Risk
    currency_exposure: Dict[str, float] = Field(default_factory=dict)
    # Ключ - валюта, значение - позиция

    class Config:
        frozen = False


class BaseInstrument(ABC, BaseModel):
    """
    Базовый класс для всех финансовых инструментов.
    
    Каждый инструмент:
    1. Хранит свои атрибуты (amount, rates, dates)
    2. Умеет рассчитывать свой вклад в риск-метрики
    3. Применяет behavioral assumptions к себе
    
    Наследники должны реализовать:
    - calculate_risk_contribution: расчет вклада в риски
    - apply_assumptions: применение behavioral assumptions
    """
    
    # Обязательные атрибуты для всех инструментов
    instrument_id: str
    instrument_type: InstrumentType
    balance_account: str
    amount: float
    currency: str
    start_date: date
    as_of_date: date
    
    # Опциональные атрибуты
    maturity_date: Optional[date] = None
    interest_rate: Optional[float] = None
    counterparty_id: Optional[str] = None
    counterparty_type: Optional[str] = None  # 'retail', 'corporate', 'bank'

    # Портфельная принадлежность и книга
    trading_portfolio: Optional[str] = None  # Торговый портфель (определяет принадлежность к книге)
    book: Optional['BookType'] = None  # Книга (trading/banking), автоматически определяется по trading_portfolio

    # Метаданные
    data_source: str = "balance"
    version: str = "1.0"
    
    class Config:
        frozen = False
        arbitrary_types_allowed = True
    
    @abstractmethod
    def calculate_risk_contribution(
        self, 
        calculation_date: date,
        risk_params: Dict,
        assumptions: Optional[Dict] = None
    ) -> RiskContribution:
        """
        Рассчитывает вклад инструмента во все риск-метрики.
        
        Args:
            calculation_date: Дата расчета
            risk_params: Параметры для расчета рисков (yield curves, buckets, etc.)
            assumptions: Behavioral assumptions для этого инструмента
            
        Returns:
            RiskContribution с заполненными метриками
        """
        pass
    
    @abstractmethod
    def apply_assumptions(self, assumptions: Dict) -> 'BaseInstrument':
        """
        Применяет behavioral assumptions к инструменту.
        Может модифицировать инструмент (например, разбить NMD на части).
        
        Args:
            assumptions: Словарь с параметрами assumptions
            
        Returns:
            Модифицированный инструмент (или список инструментов)
        """
        pass
    
    def days_to_maturity(self, as_of: date) -> Optional[int]:
        """Количество дней до погашения"""
        if self.maturity_date is None:
            return None
        return (self.maturity_date - as_of).days
    
    def is_asset(self) -> bool:
        """Является ли инструмент активом (True) или пассивом (False)"""
        return self.amount > 0

    def determine_book(self) -> 'BookType':
        """
        Определяет принадлежность инструмента к торговой или банковской книге.

        Логика определения:
        - Если trading_portfolio указан и начинается с "TRADING_" - торговая книга
        - В противном случае - банковская книга

        Returns:
            BookType: TRADING или BANKING
        """
        if self.trading_portfolio and self.trading_portfolio.startswith("TRADING_"):
            return BookType.TRADING
        return BookType.BANKING

    def get_book(self) -> 'BookType':
        """
        Возвращает книгу инструмента (торговую или банковскую).

        Если book не установлена явно, определяет автоматически по trading_portfolio.

        Returns:
            BookType: TRADING или BANKING
        """
        if self.book is None:
            return self.determine_book()
        return self.book

    def to_dict(self) -> Dict:
        """Сериализация в словарь"""
        return self.model_dump()
