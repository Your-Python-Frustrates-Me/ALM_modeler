"""
Base classes and interfaces for financial instruments
"""
from abc import ABC, abstractmethod
from typing import Dict, Optional
from datetime import date
from decimal import Decimal
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
    OTHER = "other"


class RiskContribution(BaseModel):
    """
    Вклад инструмента в риск-метрики
    
    Этот класс собирает все риск-метрики для одного инструмента,
    которые затем агрегируются на портфельном уровне.
    """
    instrument_id: str
    instrument_type: InstrumentType
    
    # Interest Rate Risk
    repricing_amount: Decimal = Decimal(0)
    repricing_date: Optional[date] = None
    duration: Optional[float] = None
    modified_duration: Optional[float] = None
    dv01: Optional[Decimal] = None
    
    # Liquidity Risk
    cash_flows: Dict[str, Decimal] = Field(default_factory=dict)
    # Ключ - временная корзина ('0-30d'), значение - сумма CF
    
    # FX Risk
    currency_exposure: Dict[str, Decimal] = Field(default_factory=dict)
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
    amount: Decimal
    currency: str
    start_date: date
    as_of_date: date
    
    # Опциональные атрибуты
    maturity_date: Optional[date] = None
    interest_rate: Optional[float] = None
    counterparty_id: Optional[str] = None
    counterparty_type: Optional[str] = None  # 'retail', 'corporate', 'bank'
    
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
    
    def to_dict(self) -> Dict:
        """Сериализация в словарь"""
        return self.model_dump()
