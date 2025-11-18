"""
Behavioral Assumptions Configuration System
Система конфигурации поведенческих предпосылок для ликвидности

Этот модуль заменяет хардкод персональных предпосылок на конфигурируемую систему,
где правила применения assumptions определяются через конфигурационные файлы или словари.
"""
from typing import Dict, List, Optional, Any
from datetime import date, timedelta
from decimal import Decimal
from dataclasses import dataclass, field
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class AssumptionRuleType(str, Enum):
    """Типы правил для assumptions"""
    COUNTERPARTY_NAME = "counterparty_name"  # По имени контрагента
    COUNTERPARTY_TYPE = "counterparty_type"  # По типу контрагента (retail, corporate, bank)
    INSTRUMENT_CLASS = "instrument_class"  # По классу инструмента
    INSTRUMENT_SUBCLASS = "instrument_subclass"  # По подклассу инструмента
    CURRENCY = "currency"  # По валюте
    AMOUNT_THRESHOLD = "amount_threshold"  # По пороговым значениям суммы
    MATURITY_BUCKET = "maturity_bucket"  # По срочности (бакетам погашения)
    COMBINED = "combined"  # Комбинированное правило


@dataclass
class AssumptionRule:
    """
    Правило применения behavioral assumption.

    Определяет условия (критерии) и параметры assumptions для инструментов,
    соответствующих этим условиям.
    """
    rule_id: str
    rule_type: AssumptionRuleType
    priority: int = 0  # Приоритет применения (больше = выше приоритет)

    # Критерии для применения правила
    conditions: Dict[str, Any] = field(default_factory=dict)

    # Параметры assumptions для применения
    assumptions: Dict[str, Any] = field(default_factory=dict)

    # Дополнительные параметры
    description: Optional[str] = None
    active: bool = True

    def matches(self, instrument_data: Dict[str, Any]) -> bool:
        """
        Проверяет, соответствует ли инструмент условиям этого правила.

        Args:
            instrument_data: Словарь с данными инструмента для проверки

        Returns:
            True если инструмент соответствует всем условиям правила
        """
        if not self.active:
            return False

        for condition_key, condition_value in self.conditions.items():
            instrument_value = instrument_data.get(condition_key)

            # Проверка по типу условия
            if isinstance(condition_value, (list, tuple)):
                # Проверка вхождения в список
                if instrument_value not in condition_value:
                    return False
            elif isinstance(condition_value, dict):
                # Для dict - специальные операторы (>=, <=, in, etc.)
                if not self._check_dict_condition(instrument_value, condition_value):
                    return False
            else:
                # Простое равенство
                if instrument_value != condition_value:
                    return False

        return True

    def _check_dict_condition(self, value: Any, condition: Dict[str, Any]) -> bool:
        """Проверка словарных условий с операторами"""
        for operator, threshold in condition.items():
            if operator == '>=':
                if not (value >= threshold):
                    return False
            elif operator == '<=':
                if not (value <= threshold):
                    return False
            elif operator == '>':
                if not (value > threshold):
                    return False
            elif operator == '<':
                if not (value < threshold):
                    return False
            elif operator == 'in':
                if value not in threshold:
                    return False
            elif operator == 'not_in':
                if value in threshold:
                    return False

        return True


@dataclass
class CounterpartyAssumption:
    """
    Специализированный класс для assumptions по контрагентам.

    Заменяет хардкод персональных предпосылок (Газпром, Казначейство, и т.д.)
    на конфигурируемые правила.
    """
    counterparty_name: str

    # Параметры ликвидности
    stable_portion: Optional[float] = None  # Устойчивая часть средств (0-1)
    avg_life_days: Optional[int] = None  # Средний срок жизни средств

    # Параметры оттока/runoff для разных сценариев
    runoff_rates: Optional[Dict[str, Dict[str, float]]] = None  # {scenario: {bucket: rate}}

    # Минимальный остаток
    minimum_balance: Optional[Decimal] = None
    maximum_outflow: Optional[Decimal] = None  # Максимальный отток

    # Параметры досрочного изъятия
    early_withdrawal_probability: Optional[float] = None  # Вероятность досрочного изъятия
    early_withdrawal_portion: Optional[float] = None  # Доля средств при досрочке

    # Флаги особых режимов
    overnight_treatment: bool = False  # Рассматривать как overnight (1 день)
    full_outflow: bool = False  # 100% отток

    # Параметры эластичности для процентного риска
    elasticity_enabled: bool = False  # Включить моделирование эластичности
    base_elasticity: Optional[float] = None  # Базовая эластичность объема к ставке
    elasticity_asymmetric: bool = False  # Асимметричная реакция на рост/падение ставок
    elasticity_positive_shock: Optional[float] = None  # Эластичность при росте ставок
    elasticity_negative_shock: Optional[float] = None  # Эластичность при падении ставок
    elasticity_threshold: Optional[float] = None  # Порог изменения ставки (в п.п.)
    elasticity_adjustment_speed: Optional[float] = None  # Скорость адаптации (0-1)
    elasticity_max_change: Optional[float] = None  # Максимальное изменение объема (доля)


class BehavioralAssumptionsManager:
    """
    Менеджер для управления behavioral assumptions.

    Применяет правила assumptions к инструментам на основе их характеристик,
    заменяя хардкод персональных предпосылок.
    """

    def __init__(self):
        self.rules: List[AssumptionRule] = []
        self.counterparty_assumptions: Dict[str, CounterpartyAssumption] = {}

    def add_rule(self, rule: AssumptionRule) -> None:
        """Добавляет правило в менеджер"""
        self.rules.append(rule)
        # Сортируем по приоритету (высший приоритет первым)
        self.rules.sort(key=lambda r: r.priority, reverse=True)

        logger.debug(f"Added assumption rule: {rule.rule_id} (priority: {rule.priority})")

    def add_counterparty_assumption(
        self,
        counterparty_name: str,
        assumption: CounterpartyAssumption
    ) -> None:
        """Добавляет assumption для конкретного контрагента"""
        self.counterparty_assumptions[counterparty_name] = assumption
        logger.debug(f"Added counterparty assumption for: {counterparty_name}")

    def get_assumptions_for_instrument(
        self,
        instrument_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Получает применимые assumptions для инструмента.

        Args:
            instrument_data: Словарь с характеристиками инструмента:
                {
                    'counterparty_name': str,
                    'counterparty_type': str,
                    'instrument_class': str,
                    'instrument_subclass': str,
                    'currency': str,
                    'amount': Decimal,
                    'maturity_days': int,
                    ...
                }

        Returns:
            Словарь с assumptions для применения
        """
        # Проверяем специальные assumptions для контрагента
        counterparty_name = instrument_data.get('counterparty_name')
        if counterparty_name and counterparty_name in self.counterparty_assumptions:
            cp_assumption = self.counterparty_assumptions[counterparty_name]
            return self._counterparty_assumption_to_dict(cp_assumption)

        # Применяем правила по приоритету
        for rule in self.rules:
            if rule.matches(instrument_data):
                logger.debug(
                    f"Applied rule {rule.rule_id} to instrument",
                    extra={
                        'rule_id': rule.rule_id,
                        'counterparty': instrument_data.get('counterparty_name'),
                        'instrument_class': instrument_data.get('instrument_class')
                    }
                )
                return rule.assumptions.copy()

        # Дефолтные assumptions
        return self._get_default_assumptions(instrument_data)

    def _counterparty_assumption_to_dict(
        self,
        cp_assumption: CounterpartyAssumption
    ) -> Dict[str, Any]:
        """Конвертирует CounterpartyAssumption в словарь"""
        result = {}

        if cp_assumption.stable_portion is not None:
            result['stable_portion'] = cp_assumption.stable_portion

        if cp_assumption.avg_life_days is not None:
            result['avg_life_days'] = cp_assumption.avg_life_days

        if cp_assumption.runoff_rates is not None:
            result['runoff_rates'] = cp_assumption.runoff_rates

        if cp_assumption.minimum_balance is not None:
            result['minimum_balance'] = cp_assumption.minimum_balance

        if cp_assumption.maximum_outflow is not None:
            result['maximum_outflow'] = cp_assumption.maximum_outflow

        if cp_assumption.early_withdrawal_probability is not None:
            result['early_withdrawal_probability'] = cp_assumption.early_withdrawal_probability

        if cp_assumption.early_withdrawal_portion is not None:
            result['early_withdrawal_portion'] = cp_assumption.early_withdrawal_portion

        if cp_assumption.overnight_treatment:
            result['maturity_override'] = 1  # Переопределить срок на 1 день

        if cp_assumption.full_outflow:
            result['runoff_override'] = 1.0  # 100% отток

        # Параметры эластичности
        if cp_assumption.elasticity_enabled:
            result['elasticity_enabled'] = True

            if cp_assumption.base_elasticity is not None:
                result['base_elasticity'] = cp_assumption.base_elasticity

            if cp_assumption.elasticity_asymmetric:
                result['elasticity_asymmetric'] = True
                if cp_assumption.elasticity_positive_shock is not None:
                    result['elasticity_positive_shock'] = cp_assumption.elasticity_positive_shock
                if cp_assumption.elasticity_negative_shock is not None:
                    result['elasticity_negative_shock'] = cp_assumption.elasticity_negative_shock

            if cp_assumption.elasticity_threshold is not None:
                result['elasticity_threshold'] = cp_assumption.elasticity_threshold

            if cp_assumption.elasticity_adjustment_speed is not None:
                result['elasticity_adjustment_speed'] = cp_assumption.elasticity_adjustment_speed

            if cp_assumption.elasticity_max_change is not None:
                result['elasticity_max_change'] = cp_assumption.elasticity_max_change

        return result

    def _get_default_assumptions(self, instrument_data: Dict[str, Any]) -> Dict[str, Any]:
        """Возвращает дефолтные assumptions на основе типа инструмента"""
        instrument_class = instrument_data.get('instrument_class', '')
        counterparty_type = instrument_data.get('counterparty_type', '')

        # Дефолтные assumptions для депозитов
        if 'deposit' in instrument_class.lower() or 'депозит' in instrument_class.lower():
            if counterparty_type == 'retail':
                return {
                    'stable_portion': 0.6,
                    'avg_life_days': 180,
                    'runoff_rates': {
                        'NAME': {'overnight': 0.05, '2-7d': 0.10, '8-30d': 0.15},
                        'MARKET': {'overnight': 0.10, '2-7d': 0.15, '8-30d': 0.20},
                        'COMBO': {'overnight': 0.15, '2-7d': 0.20, '8-30d': 0.25}
                    }
                }
            elif counterparty_type == 'corporate':
                return {
                    'stable_portion': 0.4,
                    'avg_life_days': 90,
                    'runoff_rates': {
                        'NAME': {'overnight': 0.10, '2-7d': 0.15, '8-30d': 0.20},
                        'MARKET': {'overnight': 0.20, '2-7d': 0.25, '8-30d': 0.30},
                        'COMBO': {'overnight': 0.30, '2-7d': 0.35, '8-30d': 0.40}
                    }
                }

        # Дефолтные для текущих счетов
        if 'current' in instrument_class.lower() or 'тсюл' in instrument_class.lower():
            return {
                'stable_portion': 0.3,
                'avg_life_days': 30,
                'runoff_rates': {
                    'NAME': {'overnight': 0.20, '2-7d': 0.30},
                    'MARKET': {'overnight': 0.30, '2-7d': 0.40},
                    'COMBO': {'overnight': 0.40, '2-7d': 0.50}
                }
            }

        return {}

    def load_from_config(self, config: Dict[str, Any]) -> None:
        """
        Загружает правила и assumptions из конфигурации.

        Args:
            config: Словарь конфигурации в формате:
                {
                    'rules': [
                        {
                            'rule_id': 'rule_1',
                            'rule_type': 'counterparty_name',
                            'priority': 100,
                            'conditions': {'counterparty_name': 'ABC'},
                            'assumptions': {...}
                        }
                    ],
                    'counterparty_assumptions': {
                        'ABC': {
                            'stable_portion': 0.8,
                            ...
                        }
                    }
                }
        """
        # Загружаем правила
        for rule_config in config.get('rules', []):
            rule = AssumptionRule(
                rule_id=rule_config['rule_id'],
                rule_type=AssumptionRuleType(rule_config['rule_type']),
                priority=rule_config.get('priority', 0),
                conditions=rule_config.get('conditions', {}),
                assumptions=rule_config.get('assumptions', {}),
                description=rule_config.get('description'),
                active=rule_config.get('active', True)
            )
            self.add_rule(rule)

        # Загружаем counterparty assumptions
        for cp_name, cp_config in config.get('counterparty_assumptions', {}).items():
            assumption = CounterpartyAssumption(
                counterparty_name=cp_name,
                **cp_config
            )
            self.add_counterparty_assumption(cp_name, assumption)

        logger.info(
            f"Loaded behavioral assumptions configuration",
            extra={
                'rules_count': len(self.rules),
                'counterparty_assumptions_count': len(self.counterparty_assumptions)
            }
        )
