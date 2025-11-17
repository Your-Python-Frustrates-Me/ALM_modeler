# models/instrument_factory.py
from typing import Dict, List, Type
from decimal import Decimal
import logging

from alm_calculator.core.base_instrument import BaseInstrument, InstrumentType
from alm_calculator.models.instruments.loan import Loan
from alm_calculator.models.instruments.deposit import Deposit
from alm_calculator.models.instruments.interbank import InterbankLoan
from alm_calculator.models.instruments.repo import Repo, ReverseRepo
from alm_calculator.models.instruments.bond import Bond
from alm_calculator.models.instruments.derivatives import (
    BaseDerivative, IRS, FxSwap, Futures, OIS, TOM, DepositMargin, Forward, XCCY
)
from alm_calculator.models.instruments.current_account import CurrentAccount
from alm_calculator.models.instruments.correspondent_account import CorrespondentAccount
from alm_calculator.models.instruments.other_balance_items import OtherAsset, OtherLiability
from alm_calculator.models.instruments.off_balance import OffBalanceInstrument

# from models.instruments.equity import Equity

logger = logging.getLogger(__name__)


class InstrumentFactory:
    """
    Фабрика для создания объектов инструментов из сырых данных баланса.

    Responsibilities:
    1. Маппинг balance account → instrument type
    2. Валидация данных
    3. Создание типизированных instrument objects
    """

    # Маппинг типов инструментов на классы
    INSTRUMENT_CLASSES: Dict[InstrumentType, Type[BaseInstrument]] = {
        InstrumentType.LOAN: Loan,
        InstrumentType.DEPOSIT: Deposit,
        InstrumentType.INTERBANK_LOAN: InterbankLoan,
        InstrumentType.REPO: Repo,
        InstrumentType.REVERSE_REPO: ReverseRepo,
        InstrumentType.BOND: Bond,
        InstrumentType.DERIVATIVE: BaseDerivative,  # Базовый класс, подтип определяется отдельно
        InstrumentType.CURRENT_ACCOUNT: CurrentAccount,
        InstrumentType.CORRESPONDENT_ACCOUNT: CorrespondentAccount,
        InstrumentType.OTHER_ASSET: OtherAsset,
        InstrumentType.OTHER_LIABILITY: OtherLiability,
        InstrumentType.OFF_BALANCE: OffBalanceInstrument,
        # InstrumentType.EQUITY: Equity,
    }

    # Маппинг подтипов деривативов на классы
    DERIVATIVE_SUBTYPE_CLASSES: Dict[str, Type[BaseDerivative]] = {
        'IRS': IRS,
        'FxSwap': FxSwap,
        'Futures': Futures,
        'OIS': OIS,
        'TOM': TOM,
        'DepositMargin': DepositMargin,
        'Forward': Forward,
        'XCCY': XCCY,
    }

    def __init__(self, mapping_config: Dict):
        """
        Args:
            mapping_config: Конфигурация маппинга balance accounts → instrument types
                            Пример:
                            {
                                'balance_account_patterns': {
                                    '40817': 'deposit',
                                    '45502': 'loan',
                                    ...
                                }
                            }
        """
        self.mapping_config = mapping_config
        self.account_to_type = mapping_config.get('balance_account_patterns', {})

    def create_instrument(self, balance_row: Dict) -> BaseInstrument:
        """
        Создает объект инструмента из строки баланса.

        Args:
            balance_row: Словарь с данными из баланса
                        {
                            'position_id': '12345',
                            'balance_account': '40817',
                            'amount': 1000000.00,
                            'currency': 'RUB',
                            'start_date': '2024-01-01',
                            'maturity_date': None,
                            'interest_rate': 0.08,
                            'counterparty_type': 'retail',
                            'as_of_date': '2025-01-15',
                            ...
                        }

        Returns:
            Объект конкретного класса инструмента (Loan, Deposit, etc.)

        Raises:
            ValueError: Если невозможно определить тип инструмента
        """
        # Определяем тип инструмента
        instrument_type = self._determine_instrument_type(balance_row)

        # Получаем класс для этого типа
        instrument_class = self.INSTRUMENT_CLASSES.get(instrument_type)
        if not instrument_class:
            logger.warning(
                f"No instrument class for type {instrument_type}, using BaseInstrument",
                extra={'position_id': balance_row.get('position_id')}
            )
            # Fallback: создаем generic instrument
            # TODO: Реализовать GenericInstrument для неизвестных типов
            raise ValueError(f"Unsupported instrument type: {instrument_type}")

        # Для деривативов выбираем конкретный подкласс по derivative_type
        if instrument_type == InstrumentType.DERIVATIVE:
            derivative_type = balance_row.get('derivative_type') or balance_row.get('instrument_subclass')
            if derivative_type in self.DERIVATIVE_SUBTYPE_CLASSES:
                instrument_class = self.DERIVATIVE_SUBTYPE_CLASSES[derivative_type]
                logger.debug(
                    f"Selected derivative subclass {derivative_type}",
                    extra={'position_id': balance_row.get('position_id')}
                )
            else:
                logger.warning(
                    f"Unknown derivative type {derivative_type}, using BaseDerivative",
                    extra={'position_id': balance_row.get('position_id')}
                )

        # Подготавливаем данные для инициализации
        init_data = self._prepare_init_data(balance_row, instrument_type)

        # Создаем объект
        try:
            instrument = instrument_class(**init_data)
            logger.debug(
                f"Created {instrument_type} instrument",
                extra={
                    'instrument_id': instrument.instrument_id,
                    'amount': float(instrument.amount)
                }
            )
            return instrument

        except Exception as e:
            logger.error(
                f"Failed to create instrument",
                extra={
                    'position_id': balance_row.get('position_id'),
                    'instrument_type': instrument_type,
                    'error': str(e)
                },
                exc_info=True
            )
            raise

    def _determine_instrument_type(self, balance_row: Dict) -> InstrumentType:
        """
        Определяет тип инструмента по balance account или другим признакам.
        """
        balance_account = balance_row.get('balance_account', '')

        # Ищем паттерн в конфиге
        for pattern, inst_type in self.account_to_type.items():
            if balance_account.startswith(pattern):
                return InstrumentType(inst_type)

        # Если не нашли - пробуем по другим полям
        if 'instrument_type' in balance_row:
            return InstrumentType(balance_row['instrument_type'])

        logger.warning(
            f"Cannot determine instrument type for account {balance_account}, defaulting to OTHER",
            extra={'position_id': balance_row.get('position_id')}
        )
        return InstrumentType.OTHER

    def _prepare_init_data(self, balance_row: Dict, instrument_type: InstrumentType) -> Dict:
        """
        Подготавливает данные для инициализации инструмента.
        Конвертирует типы, добавляет defaults, определяет специфичные поля.
        """
        from datetime import datetime

        # Базовые поля для всех инструментов
        init_data = {
            'instrument_id': balance_row['position_id'],
            'instrument_type': instrument_type,
            'balance_account': balance_row['balance_account'],
            'amount': Decimal(str(balance_row['amount'])),
            'currency': balance_row['currency'],
            'start_date': self._parse_date(balance_row['start_date']),
            'as_of_date': self._parse_date(balance_row['as_of_date']),
        }

        # Опциональные общие поля
        if balance_row.get('maturity_date'):
            init_data['maturity_date'] = self._parse_date(balance_row['maturity_date'])

        if balance_row.get('interest_rate'):
            init_data['interest_rate'] = float(balance_row['interest_rate'])

        if balance_row.get('counterparty_id'):
            init_data['counterparty_id'] = balance_row['counterparty_id']

        if balance_row.get('counterparty_type'):
            init_data['counterparty_type'] = balance_row['counterparty_type']

        # Специфичные поля для разных типов
        if instrument_type == InstrumentType.DEPOSIT:
            # Определяем, является ли депозит до востребования
            is_nmd = balance_row.get('maturity_date') is None
            init_data['is_demand_deposit'] = is_nmd

        elif instrument_type == InstrumentType.LOAN:
            if balance_row.get('repricing_date'):
                init_data['repricing_date'] = self._parse_date(balance_row['repricing_date'])

        return init_data

    def _parse_date(self, date_value):
        """Парсит дату из различных форматов"""
        from datetime import datetime, date

        if isinstance(date_value, date):
            return date_value

        if isinstance(date_value, str):
            # Пробуем разные форматы
            for fmt in ['%Y-%m-%d', '%d.%m.%Y', '%Y%m%d']:
                try:
                    return datetime.strptime(date_value, fmt).date()
                except ValueError:
                    continue

        raise ValueError(f"Cannot parse date: {date_value}")

    def create_instruments_batch(self, balance_data: List[Dict]) -> List[BaseInstrument]:
        """
        Создает список инструментов из пакета данных баланса.

        Args:
            balance_data: Список словарей с данными баланса

        Returns:
            Список объектов инструментов
        """
        instruments = []
        errors = []

        for idx, row in enumerate(balance_data):
            try:
                instrument = self.create_instrument(row)
                instruments.append(instrument)
            except Exception as e:
                errors.append({
                    'row_index': idx,
                    'position_id': row.get('position_id'),
                    'error': str(e)
                })

        if errors:
            logger.warning(
                f"Failed to create {len(errors)} instruments out of {len(balance_data)}",
                extra={'error_count': len(errors)}
            )

        logger.info(
            f"Successfully created {len(instruments)} instruments",
            extra={'total_positions': len(balance_data)}
        )

        return instruments
