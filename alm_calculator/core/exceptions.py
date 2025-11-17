"""
Core exceptions for ALM Calculator
"""


class ALMCalculatorError(Exception):
    """Базовое исключение для всех ошибок калькулятора"""
    pass


class DataValidationError(ALMCalculatorError):
    """Ошибка валидации входных данных"""
    pass


class CalculationError(ALMCalculatorError):
    """Ошибка в процессе расчета"""
    pass


class ConfigurationError(ALMCalculatorError):
    """Ошибка в конфигурации"""
    pass


class InstrumentCreationError(ALMCalculatorError):
    """Ошибка при создании инструмента"""
    pass
