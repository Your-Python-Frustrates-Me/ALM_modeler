"""
Mock Data Generator for ALM Calculator

Generates realistic balance sheet positions for testing ALM calculations.
Target: ~200,000 positions representing a mid-sized commercial bank.

Distribution:
- Loans: 40% (~80k positions)
- Deposits: 35% (~70k positions)
- Interbank operations: 10% (~20k positions)
- Repo operations: 5% (~10k positions)
- Current accounts: 5% (~10k positions)
- Correspondent accounts: 2% (~4k positions)
- Other assets/liabilities: 2% (~4k positions)
- Off-balance: 1% (~2k positions)
"""

import pandas as pd
import numpy as np
from datetime import date, timedelta
from decimal import Decimal
from typing import List, Dict
import random
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class MockDataGenerator:
    """
    Генератор mock данных для тестирования ALM системы.
    """

    def __init__(self, as_of_date: date, output_dir: Path, random_seed: int = 42):
        """
        Args:
            as_of_date: Дата, на которую генерируем балансовые данные
            output_dir: Директория для сохранения CSV файлов
            random_seed: Seed для воспроизводимости
        """
        self.as_of_date = as_of_date
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Set random seed for reproducibility
        random.seed(random_seed)
        np.random.seed(random_seed)

        # Справочники
        self.currencies = ['RUB', 'USD', 'EUR', 'CNY']
        self.currency_weights = [0.70, 0.15, 0.10, 0.05]  # RUB dominates

        self.counterparty_types = ['retail', 'corporate', 'bank', 'government', 'central_bank']

        # Торговые портфели (для определения книги)
        # Портфели с префиксом "TRADING_" относятся к торговой книге
        # Остальные - к банковской книге
        self.trading_portfolios = [
            'TRADING_BONDS',
            'TRADING_DERIVATIVES',
            'TRADING_FX',
            'TRADING_REPO',
            'BANKING_LOANS',
            'BANKING_DEPOSITS',
            'BANKING_INTERBANK',
            'BANKING_RETAIL'
        ]

        # Балансовые счета (упрощенная классификация)
        self.balance_accounts = {
            'loan': ['40101', '40102', '40103', '45201', '45202'],
            'deposit': ['42301', '42302', '42601', '42602', '47401'],
            'interbank_loan': ['32001', '32002', '32101', '32102'],
            'repo': ['50601', '50602'],
            'reverse_repo': ['50401', '50402'],
            'current_account': ['40702', '40703', '40802', '40817'],
            'correspondent': ['30102', '30109', '30110', '30114'],
            'other_asset': ['60101', '60201', '60301'],
            'other_liability': ['60302', '60303', '60401'],
        }

    def _assign_trading_portfolio(
        self,
        instrument_type: str,
        counterparty_type: str = None,
        is_short_term: bool = False
    ) -> str:
        """
        Определяет торговый портфель инструмента на основе его характеристик.

        Args:
            instrument_type: Тип инструмента
            counterparty_type: Тип контрагента
            is_short_term: Является ли инструмент краткосрочным

        Returns:
            Название торгового портфеля
        """
        # Вероятность попадания в торговую книгу зависит от типа инструмента
        trading_probability = {
            'loan': 0.05,  # Большинство кредитов - в банковской книге
            'deposit': 0.02,  # Депозиты обычно в банковской книге
            'interbank': 0.20,  # МБК могут быть в торговой книге если короткие
            'repo': 0.40,  # РЕПО часто для торговых целей
            'reverse_repo': 0.30,
            'bond': 0.50,  # Облигации могут быть в обеих книгах
            'derivative': 0.80,  # Деривативы чаще в торговой книге
            'current_account': 0.0,  # Текущие счета только в банковской
            'correspondent': 0.0,  # Корсчета только в банковской
            'other': 0.10
        }

        prob = trading_probability.get(instrument_type, 0.10)

        # Короткие инструменты чаще в торговой книге
        if is_short_term:
            prob *= 1.5

        # Определяем книгу
        is_trading = np.random.rand() < prob

        if is_trading:
            # Торговая книга
            if instrument_type in ['repo', 'reverse_repo']:
                return 'TRADING_REPO'
            elif instrument_type in ['derivative', 'off_balance']:
                return 'TRADING_DERIVATIVES'
            elif instrument_type == 'bond':
                return 'TRADING_BONDS'
            else:
                return 'TRADING_FX'
        else:
            # Банковская книга
            if instrument_type in ['loan']:
                return 'BANKING_LOANS'
            elif instrument_type in ['deposit']:
                return 'BANKING_DEPOSITS'
            elif instrument_type in ['interbank', 'repo', 'reverse_repo']:
                return 'BANKING_INTERBANK'
            elif counterparty_type == 'retail':
                return 'BANKING_RETAIL'
            else:
                return 'BANKING_DEPOSITS'

    def generate_all_instruments(
        self,
        total_positions: int = 200_000
    ) -> Dict[str, pd.DataFrame]:
        """
        Генерирует все типы инструментов согласно заданному распределению.

        Returns:
            Dict с DataFrames для каждого типа инструмента
        """
        logger.info(f"Starting mock data generation for {total_positions} total positions")

        # Распределение по типам инструментов
        distributions = {
            'loans': int(total_positions * 0.40),
            'deposits': int(total_positions * 0.35),
            'interbank': int(total_positions * 0.10),
            'repo': int(total_positions * 0.03),
            'reverse_repo': int(total_positions * 0.02),
            'current_accounts': int(total_positions * 0.05),
            'correspondent_accounts': int(total_positions * 0.02),
            'other_assets': int(total_positions * 0.01),
            'other_liabilities': int(total_positions * 0.01),
            'off_balance': int(total_positions * 0.01),
        }

        datasets = {}

        # Generate each instrument type
        datasets['loans'] = self._generate_loans(distributions['loans'])
        datasets['deposits'] = self._generate_deposits(distributions['deposits'])
        datasets['interbank'] = self._generate_interbank(distributions['interbank'])
        datasets['repo'] = self._generate_repo(distributions['repo'])
        datasets['reverse_repo'] = self._generate_reverse_repo(distributions['reverse_repo'])
        datasets['current_accounts'] = self._generate_current_accounts(distributions['current_accounts'])
        datasets['correspondent_accounts'] = self._generate_correspondent_accounts(distributions['correspondent_accounts'])
        datasets['other_assets'] = self._generate_other_assets(distributions['other_assets'])
        datasets['other_liabilities'] = self._generate_other_liabilities(distributions['other_liabilities'])
        datasets['off_balance'] = self._generate_off_balance(distributions['off_balance'])

        logger.info("Mock data generation completed")

        return datasets

    def _generate_loans(self, count: int) -> pd.DataFrame:
        """Генерирует кредиты"""
        logger.info(f"Generating {count} loans")

        loans = []
        for i in range(count):
            # Тип заемщика
            cpty_type = np.random.choice(
                ['retail', 'corporate', 'government'],
                p=[0.60, 0.35, 0.05]
            )

            # Сумма кредита зависит от типа заемщика
            if cpty_type == 'retail':
                amount = np.random.lognormal(mean=13.0, sigma=1.5)  # ~450k RUB average
                min_amount, max_amount = 50_000, 50_000_000
            elif cpty_type == 'corporate':
                amount = np.random.lognormal(mean=16.0, sigma=2.0)  # ~9M RUB average
                min_amount, max_amount = 500_000, 5_000_000_000
            else:  # government
                amount = np.random.lognormal(mean=18.0, sigma=1.5)  # ~65M RUB average
                min_amount, max_amount = 10_000_000, 10_000_000_000

            amount = np.clip(amount, min_amount, max_amount)

            # Валюта
            currency = np.random.choice(self.currencies, p=self.currency_weights)
            if currency != 'RUB':
                amount = amount / 85  # Convert to USD-equivalent

            # Срок кредита
            if cpty_type == 'retail':
                # Розница: ипотека (долго) или потреб (средне)
                is_mortgage = np.random.rand() < 0.3
                if is_mortgage:
                    maturity_days = int(np.random.uniform(3650, 10950))  # 10-30 лет
                else:
                    maturity_days = int(np.random.uniform(180, 1825))  # 6 мес - 5 лет
            elif cpty_type == 'corporate':
                maturity_days = int(np.random.uniform(365, 3650))  # 1-10 лет
            else:  # government
                maturity_days = int(np.random.uniform(1825, 7300))  # 5-20 лет

            start_date = self.as_of_date - timedelta(days=int(np.random.uniform(0, maturity_days * 0.8)))
            maturity_date = start_date + timedelta(days=maturity_days)

            # Процентная ставка
            if currency == 'RUB':
                base_rate = 16.0 if self.as_of_date.year >= 2024 else 7.5
            elif currency == 'USD':
                base_rate = 5.5
            elif currency == 'EUR':
                base_rate = 4.0
            else:  # CNY
                base_rate = 3.5

            # Добавляем спред в зависимости от типа заемщика
            if cpty_type == 'retail':
                spread = np.random.uniform(2.0, 8.0)
            elif cpty_type == 'corporate':
                spread = np.random.uniform(1.0, 5.0)
            else:
                spread = np.random.uniform(0.0, 2.0)

            interest_rate = (base_rate + spread) / 100

            # Repricing date (для плавающей ставки ~30% кредитов)
            if np.random.rand() < 0.3:
                repricing_days = int(np.random.choice([90, 180, 365]))
                repricing_date = self.as_of_date + timedelta(days=repricing_days)
            else:
                repricing_date = maturity_date  # Фиксированная ставка

            # Определяем торговый портфель
            is_short_term = maturity_days < 365
            trading_portfolio = self._assign_trading_portfolio('loan', cpty_type, is_short_term)

            loan = {
                'instrument_id': f'LOAN_{i:08d}',
                'instrument_type': 'loan',
                'balance_account': np.random.choice(self.balance_accounts['loan']),
                'amount': float(amount),
                'currency': currency,
                'start_date': start_date.isoformat(),
                'maturity_date': maturity_date.isoformat() if maturity_date > self.as_of_date else None,
                'interest_rate': interest_rate,
                'counterparty_id': f'CPTY_{cpty_type.upper()}_{i % 10000:05d}',
                'counterparty_type': cpty_type,
                'as_of_date': self.as_of_date.isoformat(),
                'repricing_date': repricing_date.isoformat() if repricing_date and repricing_date > self.as_of_date else None,
                'trading_portfolio': trading_portfolio,
                'data_source': 'mock_generator',
                'version': '1.0',
            }

            loans.append(loan)

        return pd.DataFrame(loans)

    def _generate_deposits(self, count: int) -> pd.DataFrame:
        """Генерирует депозиты"""
        logger.info(f"Generating {count} deposits")

        deposits = []
        for i in range(count):
            # Тип вкладчика
            cpty_type = np.random.choice(
                ['retail', 'corporate', 'government'],
                p=[0.55, 0.40, 0.05]
            )

            # Тип депозита: срочный или до востребования (NMD)
            is_demand = np.random.rand() < 0.30  # 30% - до востребования

            # Сумма депозита
            if cpty_type == 'retail':
                if is_demand:
                    amount = np.random.lognormal(mean=11.5, sigma=2.0)  # ~100k RUB average
                else:
                    amount = np.random.lognormal(mean=12.5, sigma=1.8)  # ~300k RUB average
                min_amount, max_amount = 1_000, 20_000_000
            elif cpty_type == 'corporate':
                if is_demand:
                    amount = np.random.lognormal(mean=14.5, sigma=2.5)  # ~2M RUB average
                else:
                    amount = np.random.lognormal(mean=15.5, sigma=2.0)  # ~5M RUB average
                min_amount, max_amount = 10_000, 2_000_000_000
            else:  # government
                amount = np.random.lognormal(mean=17.0, sigma=1.5)  # ~25M RUB average
                min_amount, max_amount = 1_000_000, 5_000_000_000

            amount = np.clip(amount, min_amount, max_amount)

            # Валюта
            currency = np.random.choice(self.currencies, p=self.currency_weights)
            if currency != 'RUB':
                amount = amount / 85

            # Даты
            if is_demand:
                maturity_date = None
                # NMD параметры
                if cpty_type == 'retail':
                    core_portion = np.random.uniform(0.60, 0.80)
                    avg_life_years = np.random.uniform(2.0, 4.0)
                elif cpty_type == 'corporate':
                    core_portion = np.random.uniform(0.30, 0.50)
                    avg_life_years = np.random.uniform(0.5, 2.0)
                else:  # government
                    core_portion = np.random.uniform(0.70, 0.90)
                    avg_life_years = np.random.uniform(1.0, 3.0)

                withdrawal_rates = {
                    '0-30d': np.random.uniform(0.05, 0.15),
                    '30-90d': np.random.uniform(0.05, 0.15),
                    '90-180d': np.random.uniform(0.02, 0.08),
                }
            else:
                # Срочный депозит
                if cpty_type == 'retail':
                    maturity_days = int(np.random.choice([90, 180, 365, 730, 1095], p=[0.3, 0.3, 0.25, 0.1, 0.05]))
                elif cpty_type == 'corporate':
                    maturity_days = int(np.random.choice([30, 90, 180, 365], p=[0.2, 0.4, 0.3, 0.1]))
                else:  # government
                    maturity_days = int(np.random.choice([180, 365, 730], p=[0.3, 0.5, 0.2]))

                start_date = self.as_of_date - timedelta(days=int(np.random.uniform(0, maturity_days * 0.7)))
                maturity_date = start_date + timedelta(days=maturity_days)
                core_portion = None
                avg_life_years = None
                withdrawal_rates = {}

            # Процентная ставка
            if currency == 'RUB':
                base_rate = 15.0 if self.as_of_date.year >= 2024 else 6.5
            elif currency == 'USD':
                base_rate = 4.5
            elif currency == 'EUR':
                base_rate = 3.0
            else:  # CNY
                base_rate = 2.5

            # Депозиты - ниже кредитных ставок
            if is_demand:
                interest_rate = (base_rate - np.random.uniform(3.0, 6.0)) / 100
                interest_rate = max(interest_rate, 0.001)  # Минимум 0.1%
            else:
                spread = np.random.uniform(-2.0, 1.0)
                interest_rate = (base_rate + spread) / 100
                interest_rate = max(interest_rate, 0.5 / 100)

            # Определяем торговый портфель
            is_short_term = not is_demand and maturity_days < 365 if not is_demand else False
            trading_portfolio = self._assign_trading_portfolio('deposit', cpty_type, is_short_term)

            deposit = {
                'instrument_id': f'DEPO_{i:08d}',
                'instrument_type': 'deposit',
                'balance_account': np.random.choice(self.balance_accounts['deposit']),
                'amount': float(amount),
                'currency': currency,
                'start_date': (start_date if not is_demand else self.as_of_date - timedelta(days=int(np.random.uniform(0, 1095)))).isoformat(),
                'maturity_date': maturity_date.isoformat() if maturity_date and maturity_date > self.as_of_date else None,
                'interest_rate': interest_rate,
                'counterparty_id': f'CPTY_{cpty_type.upper()}_{i % 15000:05d}',
                'counterparty_type': cpty_type,
                'as_of_date': self.as_of_date.isoformat(),
                'is_demand_deposit': is_demand,
                'core_portion': core_portion,
                'avg_life_years': avg_life_years,
                'withdrawal_rates': str(withdrawal_rates) if withdrawal_rates else None,
                'trading_portfolio': trading_portfolio,
                'data_source': 'mock_generator',
                'version': '1.0',
            }

            deposits.append(deposit)

        return pd.DataFrame(deposits)

    def _generate_interbank(self, count: int) -> pd.DataFrame:
        """Генерирует межбанковские кредиты (МБК)"""
        logger.info(f"Generating {count} interbank loans")

        interbank = []
        for i in range(count):
            # Направление: размещение (актив) или привлечение (пассив)
            is_placement = np.random.rand() < 0.50  # 50/50

            # Сумма МБК (обычно крупные суммы)
            amount = np.random.lognormal(mean=17.0, sigma=1.5)  # ~24M RUB average
            amount = np.clip(amount, 5_000_000, 10_000_000_000)

            # Валюта (МБК чаще в RUB или USD)
            currency = np.random.choice(['RUB', 'USD', 'EUR'], p=[0.70, 0.20, 0.10])
            if currency != 'RUB':
                amount = amount / 85

            # Срок МБК (обычно краткосрочные)
            maturity_days = int(np.random.choice([1, 7, 14, 30, 90, 180, 365], p=[0.15, 0.20, 0.15, 0.20, 0.15, 0.10, 0.05]))

            start_date = self.as_of_date - timedelta(days=int(np.random.uniform(0, min(maturity_days, 30))))
            maturity_date = start_date + timedelta(days=maturity_days)

            # Процентная ставка
            if currency == 'RUB':
                base_rate = 16.0 if self.as_of_date.year >= 2024 else 7.0
            elif currency == 'USD':
                base_rate = 5.5
            else:  # EUR
                base_rate = 4.0

            spread = np.random.uniform(-0.5, 1.5)
            interest_rate = (base_rate + spread) / 100

            # Определяем торговый портфель
            is_short_term = maturity_days <= 90
            trading_portfolio = self._assign_trading_portfolio('interbank', 'bank', is_short_term)

            mbk = {
                'instrument_id': f'MBK_{i:08d}',
                'instrument_type': 'interbank_loan',
                'balance_account': np.random.choice(self.balance_accounts['interbank_loan']),
                'amount': float(amount) if is_placement else float(-amount),
                'currency': currency,
                'start_date': start_date.isoformat(),
                'maturity_date': maturity_date.isoformat() if maturity_date > self.as_of_date else None,
                'interest_rate': interest_rate,
                'counterparty_id': f'BANK_{i % 100:03d}',
                'counterparty_type': 'bank',
                'as_of_date': self.as_of_date.isoformat(),
                'is_placement': is_placement,
                'counterparty_bank': f'Bank_{i % 100:03d}',
                'credit_rating': np.random.choice(['AAA', 'AA', 'A', 'BBB', 'BB'], p=[0.05, 0.15, 0.40, 0.30, 0.10]),
                'trading_portfolio': trading_portfolio,
                'data_source': 'mock_generator',
                'version': '1.0',
            }

            interbank.append(mbk)

        return pd.DataFrame(interbank)

    def _generate_repo(self, count: int) -> pd.DataFrame:
        """Генерирует прямые РЕПО"""
        logger.info(f"Generating {count} REPO transactions")

        repos = []
        for i in range(count):
            # Сумма РЕПО
            amount = np.random.lognormal(mean=17.5, sigma=1.5)  # ~40M RUB average
            amount = np.clip(amount, 10_000_000, 50_000_000_000)

            # Валюта (РЕПО преимущественно в RUB)
            currency = np.random.choice(['RUB', 'USD'], p=[0.90, 0.10])
            if currency != 'RUB':
                amount = amount / 85

            # Срок РЕПО (обычно очень короткие)
            maturity_days = int(np.random.choice([1, 2, 7, 14, 30, 90], p=[0.30, 0.20, 0.20, 0.15, 0.10, 0.05]))

            start_date = self.as_of_date - timedelta(days=int(np.random.uniform(0, min(maturity_days, 7))))
            maturity_date = start_date + timedelta(days=maturity_days)

            # Ставка РЕПО
            if currency == 'RUB':
                base_rate = 16.0 if self.as_of_date.year >= 2024 else 7.0
            else:  # USD
                base_rate = 5.5

            repo_rate = (base_rate + np.random.uniform(-0.5, 0.5)) / 100

            # Обеспечение
            collateral_type = np.random.choice(['OFZ', 'Corporate_Bonds', 'Bank_Bonds'], p=[0.60, 0.30, 0.10])
            haircut = np.random.uniform(0.05, 0.20) if collateral_type == 'Corporate_Bonds' else np.random.uniform(0.0, 0.10)
            collateral_value = amount * (1 + haircut)

            # Определяем торговый портфель (РЕПО часто в торговой книге)
            is_short_term = maturity_days <= 30
            trading_portfolio = self._assign_trading_portfolio('repo', 'bank', is_short_term)

            repo = {
                'instrument_id': f'REPO_{i:08d}',
                'instrument_type': 'repo',
                'balance_account': np.random.choice(self.balance_accounts['repo']),
                'amount': float(amount),
                'currency': currency,
                'start_date': start_date.isoformat(),
                'maturity_date': maturity_date.isoformat() if maturity_date > self.as_of_date else None,
                'interest_rate': repo_rate,
                'counterparty_id': f'REPO_CPTY_{i % 50:03d}',
                'counterparty_type': 'bank',
                'as_of_date': self.as_of_date.isoformat(),
                'repo_rate': repo_rate,
                'collateral_type': collateral_type,
                'collateral_value': float(collateral_value),
                'haircut': haircut,
                'trading_portfolio': trading_portfolio,
                'data_source': 'mock_generator',
                'version': '1.0',
            }

            repos.append(repo)

        return pd.DataFrame(repos)

    def _generate_reverse_repo(self, count: int) -> pd.DataFrame:
        """Генерирует обратные РЕПО"""
        logger.info(f"Generating {count} Reverse REPO transactions")

        reverse_repos = []
        for i in range(count):
            # Сумма обратного РЕПО
            amount = np.random.lognormal(mean=17.3, sigma=1.5)  # ~30M RUB average
            amount = np.clip(amount, 5_000_000, 30_000_000_000)

            # Валюта
            currency = np.random.choice(['RUB', 'USD'], p=[0.85, 0.15])
            if currency != 'RUB':
                amount = amount / 85

            # Срок
            maturity_days = int(np.random.choice([1, 2, 7, 14, 30], p=[0.25, 0.20, 0.25, 0.20, 0.10]))

            start_date = self.as_of_date - timedelta(days=int(np.random.uniform(0, min(maturity_days, 7))))
            maturity_date = start_date + timedelta(days=maturity_days)

            # Ставка РЕПО
            if currency == 'RUB':
                base_rate = 16.0 if self.as_of_date.year >= 2024 else 7.0
            else:
                base_rate = 5.5

            repo_rate = (base_rate + np.random.uniform(-1.0, 0.0)) / 100  # Размещение - ниже ставки

            # Обеспечение
            collateral_type = np.random.choice(['OFZ', 'Corporate_Bonds', 'CBR_Bonds'], p=[0.50, 0.30, 0.20])
            haircut = np.random.uniform(0.05, 0.15) if collateral_type == 'Corporate_Bonds' else np.random.uniform(0.0, 0.08)
            collateral_value = amount * (1 + haircut)

            # Определяем торговый портфель
            is_short_term = maturity_days <= 30
            trading_portfolio = self._assign_trading_portfolio('reverse_repo', 'bank', is_short_term)

            rrepo = {
                'instrument_id': f'RREPO_{i:08d}',
                'instrument_type': 'reverse_repo',
                'balance_account': np.random.choice(self.balance_accounts['reverse_repo']),
                'amount': float(amount),
                'currency': currency,
                'start_date': start_date.isoformat(),
                'maturity_date': maturity_date.isoformat() if maturity_date > self.as_of_date else None,
                'interest_rate': repo_rate,
                'counterparty_id': f'RREPO_CPTY_{i % 40:03d}',
                'counterparty_type': 'bank',
                'as_of_date': self.as_of_date.isoformat(),
                'repo_rate': repo_rate,
                'collateral_type': collateral_type,
                'collateral_value': float(collateral_value),
                'haircut': haircut,
                'trading_portfolio': trading_portfolio,
                'data_source': 'mock_generator',
                'version': '1.0',
            }

            reverse_repos.append(rrepo)

        return pd.DataFrame(reverse_repos)

    def _generate_current_accounts(self, count: int) -> pd.DataFrame:
        """Генерирует текущие счета"""
        logger.info(f"Generating {count} current accounts")

        current_accounts = []
        for i in range(count):
            # Тип владельца счета
            cpty_type = np.random.choice(['retail', 'corporate', 'government'], p=[0.50, 0.45, 0.05])

            # Сумма на счете
            if cpty_type == 'retail':
                amount = np.random.lognormal(mean=10.5, sigma=2.5)  # ~37k RUB average
                amount = np.clip(amount, 100, 10_000_000)
            elif cpty_type == 'corporate':
                amount = np.random.lognormal(mean=14.0, sigma=2.5)  # ~1.2M RUB average
                amount = np.clip(amount, 1_000, 500_000_000)
            else:  # government
                amount = np.random.lognormal(mean=16.0, sigma=2.0)  # ~9M RUB average
                amount = np.clip(amount, 100_000, 2_000_000_000)

            # Валюта
            currency = np.random.choice(self.currencies, p=[0.85, 0.08, 0.05, 0.02])
            if currency != 'RUB':
                amount = amount / 85

            # Stable portion зависит от типа
            if cpty_type == 'retail':
                stable_portion = np.random.uniform(0.50, 0.70)
                avg_life_days = int(np.random.uniform(180, 365))
            elif cpty_type == 'corporate':
                stable_portion = np.random.uniform(0.30, 0.50)
                avg_life_days = int(np.random.uniform(90, 270))
            else:  # government
                stable_portion = np.random.uniform(0.70, 0.90)
                avg_life_days = int(np.random.uniform(180, 365))

            # Процентная ставка (обычно низкая или 0)
            interest_rate = np.random.uniform(0.0, 0.5) / 100

            # Определяем торговый портфель (текущие счета всегда в банковской книге)
            trading_portfolio = self._assign_trading_portfolio('current_account', cpty_type, False)

            current_acc = {
                'instrument_id': f'CURR_ACC_{i:08d}',
                'instrument_type': 'current_account',
                'balance_account': np.random.choice(self.balance_accounts['current_account']),
                'amount': float(amount),
                'currency': currency,
                'start_date': (self.as_of_date - timedelta(days=int(np.random.uniform(30, 1825)))).isoformat(),
                'maturity_date': None,
                'interest_rate': interest_rate,
                'counterparty_id': f'CPTY_{cpty_type.upper()}_{i % 20000:05d}',
                'counterparty_type': cpty_type,
                'as_of_date': self.as_of_date.isoformat(),
                'is_transactional': True,
                'stable_portion': stable_portion,
                'avg_life_days': avg_life_days,
                'trading_portfolio': trading_portfolio,
                'data_source': 'mock_generator',
                'version': '1.0',
            }

            current_accounts.append(current_acc)

        return pd.DataFrame(current_accounts)

    def _generate_correspondent_accounts(self, count: int) -> pd.DataFrame:
        """Генерирует корреспондентские счета"""
        logger.info(f"Generating {count} correspondent accounts")

        corr_accounts = []
        for i in range(count):
            # Тип корсчета
            account_type = np.random.choice(
                ['nostro', 'loro', 'cbr_required_reserve', 'cbr_operational'],
                p=[0.40, 0.30, 0.15, 0.15]
            )

            # Сумма
            if account_type == 'cbr_required_reserve':
                # Обязательные резервы - крупные суммы
                amount = np.random.lognormal(mean=18.0, sigma=1.0)  # ~65M RUB
                amount = np.clip(amount, 10_000_000, 100_000_000_000)
            elif account_type == 'cbr_operational':
                # Операционный остаток в ЦБ
                amount = np.random.lognormal(mean=17.0, sigma=1.5)  # ~24M RUB
                amount = np.clip(amount, 1_000_000, 50_000_000_000)
            elif account_type == 'nostro':
                # НОСТРО счета
                amount = np.random.lognormal(mean=16.0, sigma=2.0)  # ~9M RUB
                amount = np.clip(amount, 100_000, 10_000_000_000)
            else:  # loro
                # ЛОРО счета
                amount = np.random.lognormal(mean=15.5, sigma=2.0)  # ~5M RUB
                amount = np.clip(amount, 50_000, 5_000_000_000)

            # Валюта
            if account_type in ['cbr_required_reserve', 'cbr_operational']:
                currency = 'RUB'
            elif account_type == 'nostro':
                currency = np.random.choice(['RUB', 'USD', 'EUR', 'CNY'], p=[0.40, 0.30, 0.20, 0.10])
            else:  # loro
                currency = np.random.choice(['RUB', 'USD', 'EUR'], p=[0.50, 0.30, 0.20])

            if currency != 'RUB':
                amount = amount / 85

            # Процентная ставка (обычно минимальная или 0)
            interest_rate = np.random.uniform(0.0, 0.1) / 100

            # Counterparty
            if account_type in ['cbr_required_reserve', 'cbr_operational']:
                counterparty_id = 'CBR_001'
                counterparty_type = 'central_bank'
                correspondent_bank = 'Central Bank of Russia'
            else:
                counterparty_id = f'BANK_{i % 150:03d}'
                counterparty_type = 'bank'
                correspondent_bank = f'Bank_{i % 150:03d}'

            # Определяем торговый портфель (корсчета всегда в банковской книге)
            trading_portfolio = self._assign_trading_portfolio('correspondent', counterparty_type, False)

            corr_acc = {
                'instrument_id': f'CORR_ACC_{i:08d}',
                'instrument_type': 'correspondent_account',
                'balance_account': np.random.choice(self.balance_accounts['correspondent']),
                'amount': float(amount) if account_type in ['nostro', 'cbr_required_reserve', 'cbr_operational'] else float(-amount),
                'currency': currency,
                'start_date': (self.as_of_date - timedelta(days=int(np.random.uniform(180, 3650)))).isoformat(),
                'maturity_date': None,
                'interest_rate': interest_rate,
                'counterparty_id': counterparty_id,
                'counterparty_type': counterparty_type,
                'as_of_date': self.as_of_date.isoformat(),
                'account_type': account_type,
                'correspondent_bank': correspondent_bank,
                'is_required_reserve': account_type == 'cbr_required_reserve',
                'trading_portfolio': trading_portfolio,
                'data_source': 'mock_generator',
                'version': '1.0',
            }

            corr_accounts.append(corr_acc)

        return pd.DataFrame(corr_accounts)

    def _generate_other_assets(self, count: int) -> pd.DataFrame:
        """Генерирует прочие активы"""
        logger.info(f"Generating {count} other assets")

        other_assets = []
        for i in range(count):
            # Категория актива
            asset_category = np.random.choice(
                ['fixed_assets', 'intangible', 'receivables', 'other'],
                p=[0.40, 0.20, 0.30, 0.10]
            )

            # Сумма
            if asset_category == 'fixed_assets':
                amount = np.random.lognormal(mean=15.0, sigma=2.0)  # ~3M RUB
                amount = np.clip(amount, 100_000, 1_000_000_000)
            elif asset_category == 'intangible':
                amount = np.random.lognormal(mean=13.0, sigma=1.5)  # ~450k RUB
                amount = np.clip(amount, 50_000, 100_000_000)
            else:  # receivables, other
                amount = np.random.lognormal(mean=14.0, sigma=2.0)  # ~1.2M RUB
                amount = np.clip(amount, 10_000, 500_000_000)

            # Валюта
            is_monetary = asset_category in ['receivables', 'other']
            currency = 'RUB' if not is_monetary or np.random.rand() < 0.90 else np.random.choice(['USD', 'EUR'])

            if currency != 'RUB':
                amount = amount / 85

            # Maturity date только для receivables
            if asset_category == 'receivables':
                maturity_days = int(np.random.uniform(30, 365))
                start_date = self.as_of_date - timedelta(days=int(np.random.uniform(0, maturity_days * 0.5)))
                maturity_date = start_date + timedelta(days=maturity_days)
            else:
                start_date = self.as_of_date - timedelta(days=int(np.random.uniform(365, 3650)))
                maturity_date = None

            # Liquidation parameters
            if asset_category == 'fixed_assets':
                liquidity_haircut = np.random.uniform(0.40, 0.70)
            else:
                liquidity_haircut = np.random.uniform(0.10, 0.30) if is_monetary else 1.0

            # Определяем торговый портфель
            trading_portfolio = self._assign_trading_portfolio('other', None, False)

            other_asset = {
                'instrument_id': f'OTHER_ASSET_{i:08d}',
                'instrument_type': 'other_asset',
                'balance_account': np.random.choice(self.balance_accounts['other_asset']),
                'amount': float(amount),
                'currency': currency,
                'start_date': start_date.isoformat(),
                'maturity_date': maturity_date.isoformat() if maturity_date and maturity_date > self.as_of_date else None,
                'interest_rate': None,
                'counterparty_id': None,
                'counterparty_type': None,
                'as_of_date': self.as_of_date.isoformat(),
                'asset_category': asset_category,
                'is_monetary': is_monetary,
                'liquidity_haircut': liquidity_haircut,
                'trading_portfolio': trading_portfolio,
                'data_source': 'mock_generator',
                'version': '1.0',
            }

            other_assets.append(other_asset)

        return pd.DataFrame(other_assets)

    def _generate_other_liabilities(self, count: int) -> pd.DataFrame:
        """Генерирует прочие пассивы"""
        logger.info(f"Generating {count} other liabilities")

        other_liabilities = []
        for i in range(count):
            # Категория пассива
            liability_category = np.random.choice(
                ['payables', 'reserves', 'payroll', 'other'],
                p=[0.40, 0.30, 0.20, 0.10]
            )

            # Сумма
            if liability_category == 'reserves':
                amount = np.random.lognormal(mean=15.5, sigma=2.0)  # ~5M RUB
                amount = np.clip(amount, 500_000, 2_000_000_000)
            elif liability_category == 'payroll':
                amount = np.random.lognormal(mean=13.5, sigma=1.5)  # ~650k RUB
                amount = np.clip(amount, 50_000, 50_000_000)
            else:  # payables, other
                amount = np.random.lognormal(mean=14.5, sigma=2.0)  # ~2M RUB
                amount = np.clip(amount, 10_000, 500_000_000)

            # Валюта
            is_monetary = liability_category in ['payables', 'payroll', 'other']
            currency = 'RUB' if not is_monetary or np.random.rand() < 0.95 else 'USD'

            if currency != 'RUB':
                amount = amount / 85

            # Maturity date
            if liability_category == 'payables':
                maturity_days = int(np.random.uniform(15, 90))
            elif liability_category == 'payroll':
                maturity_days = int(np.random.uniform(1, 30))
            else:  # reserves, other
                maturity_days = int(np.random.uniform(180, 730))

            start_date = self.as_of_date - timedelta(days=int(np.random.uniform(0, maturity_days * 0.3)))
            maturity_date = start_date + timedelta(days=maturity_days)

            # Определяем торговый портфель
            trading_portfolio = self._assign_trading_portfolio('other', None, False)

            other_liability = {
                'instrument_id': f'OTHER_LIAB_{i:08d}',
                'instrument_type': 'other_liability',
                'balance_account': np.random.choice(self.balance_accounts['other_liability']),
                'amount': float(amount),
                'currency': currency,
                'start_date': start_date.isoformat(),
                'maturity_date': maturity_date.isoformat() if maturity_date > self.as_of_date else None,
                'interest_rate': None,
                'counterparty_id': None,
                'counterparty_type': None,
                'as_of_date': self.as_of_date.isoformat(),
                'liability_category': liability_category,
                'is_monetary': is_monetary,
                'priority_level': np.random.choice(['senior', 'subordinated'], p=[0.90, 0.10]),
                'trading_portfolio': trading_portfolio,
                'data_source': 'mock_generator',
                'version': '1.0',
            }

            other_liabilities.append(other_liability)

        return pd.DataFrame(other_liabilities)

    def _generate_off_balance(self, count: int) -> pd.DataFrame:
        """Генерирует внебалансовые инструменты"""
        logger.info(f"Generating {count} off-balance instruments")

        off_balance = []
        for i in range(count):
            # Тип внебалансового инструмента
            off_balance_type = np.random.choice(
                ['guarantee', 'credit_line', 'forward', 'swap'],
                p=[0.40, 0.35, 0.15, 0.10]
            )

            # Notional amount
            if off_balance_type in ['guarantee', 'credit_line']:
                notional = np.random.lognormal(mean=16.5, sigma=2.0)  # ~13M RUB
                notional = np.clip(notional, 1_000_000, 5_000_000_000)
            else:  # derivatives
                notional = np.random.lognormal(mean=18.0, sigma=1.5)  # ~65M RUB
                notional = np.clip(notional, 10_000_000, 50_000_000_000)

            # Валюта
            currency = np.random.choice(['RUB', 'USD', 'EUR'], p=[0.60, 0.25, 0.15])
            if currency != 'RUB':
                notional = notional / 85

            # Даты
            if off_balance_type in ['guarantee', 'credit_line']:
                expiry_days = int(np.random.uniform(90, 1095))  # 3 мес - 3 года
                settlement_date = None
                draw_down_probability = np.random.uniform(0.20, 0.60)
            else:  # derivatives
                expiry_days = int(np.random.uniform(30, 730))  # 1 мес - 2 года
                settlement_date = self.as_of_date + timedelta(days=expiry_days)
                draw_down_probability = None

            expiry_date = self.as_of_date + timedelta(days=expiry_days)

            # Специфичные параметры для деривативов
            if off_balance_type == 'forward':
                derivative_type = 'FX_FORWARD'
                pay_currency = currency
                receive_currency = np.random.choice(['RUB', 'USD', 'EUR'])
                while receive_currency == pay_currency:
                    receive_currency = np.random.choice(['RUB', 'USD', 'EUR'])

                # FX rate (simplified)
                fx_rate = 85.0 if 'USD' in [pay_currency, receive_currency] else 90.0
                pay_amount = notional
                receive_amount = notional * fx_rate if pay_currency != 'RUB' else notional / fx_rate
            elif off_balance_type == 'swap':
                derivative_type = 'IRS'
                is_payer = np.random.rand() < 0.5
                pay_currency = currency
                receive_currency = currency
                pay_amount = None
                receive_amount = None
            else:
                derivative_type = None
                pay_currency = None
                receive_currency = None
                pay_amount = None
                receive_amount = None

            # Utilized amount для гарантий и кредитных линий
            if off_balance_type in ['guarantee', 'credit_line']:
                utilized_pct = np.random.uniform(0.0, 0.50)
                utilized_amount = notional * utilized_pct
                available_amount = notional - utilized_amount
            else:
                utilized_amount = None
                available_amount = None

            # Определяем торговый портфель (деривативы часто в торговой книге)
            is_short_term = expiry_days <= 180
            trading_portfolio = self._assign_trading_portfolio('derivative', None, is_short_term)

            off_bal = {
                'instrument_id': f'OFF_BAL_{i:08d}',
                'instrument_type': 'off_balance',
                'balance_account': '99999',  # Внебалансовый счет
                'amount': float(notional),
                'currency': currency,
                'start_date': (self.as_of_date - timedelta(days=int(np.random.uniform(0, 180)))).isoformat(),
                'maturity_date': None,
                'interest_rate': np.random.uniform(0.05, 0.15) if off_balance_type == 'swap' else None,
                'counterparty_id': f'CPTY_OFF_BAL_{i % 500:04d}',
                'counterparty_type': np.random.choice(['corporate', 'bank', 'government'], p=[0.50, 0.40, 0.10]),
                'as_of_date': self.as_of_date.isoformat(),
                'off_balance_type': off_balance_type,
                'notional_amount': float(notional),
                'draw_down_probability': draw_down_probability,
                'expiry_date': expiry_date.isoformat() if expiry_date > self.as_of_date else None,
                'settlement_date': settlement_date.isoformat() if settlement_date and settlement_date > self.as_of_date else None,
                'derivative_type': derivative_type,
                'pay_leg_currency': pay_currency,
                'receive_leg_currency': receive_currency,
                'pay_leg_amount': float(pay_amount) if pay_amount else None,
                'receive_leg_amount': float(receive_amount) if receive_amount else None,
                'is_payer': is_payer if off_balance_type == 'swap' else None,
                'utilized_amount': float(utilized_amount) if utilized_amount else None,
                'available_amount': float(available_amount) if available_amount else None,
                'trading_portfolio': trading_portfolio,
                'data_source': 'mock_generator',
                'version': '1.0',
            }

            off_balance.append(off_bal)

        return pd.DataFrame(off_balance)

    def save_to_csv(self, datasets: Dict[str, pd.DataFrame]) -> None:
        """
        Сохраняет все datasets в CSV файлы.

        Args:
            datasets: Dict с DataFrames для каждого типа инструмента
        """
        logger.info(f"Saving datasets to {self.output_dir}")

        for instrument_type, df in datasets.items():
            output_path = self.output_dir / f"{instrument_type}.csv"
            df.to_csv(output_path, index=False, encoding='utf-8')
            logger.info(f"Saved {len(df)} {instrument_type} to {output_path}")

        # Сводная статистика
        self._generate_summary(datasets)

    def _generate_summary(self, datasets: Dict[str, pd.DataFrame]) -> None:
        """Генерирует сводную статистику по созданным данным"""
        summary = []

        total_positions = 0
        total_assets = 0.0
        total_liabilities = 0.0

        for instrument_type, df in datasets.items():
            count = len(df)
            total_positions += count

            # Определяем знак (актив/пассив) для каждого типа
            if instrument_type in ['loans', 'reverse_repo', 'other_assets']:
                total_assets += df['amount'].sum()
                sign = 'Asset'
            elif instrument_type in ['deposits', 'repo', 'current_accounts', 'other_liabilities']:
                total_liabilities += df['amount'].sum()
                sign = 'Liability'
            elif instrument_type == 'interbank':
                # МБК может быть активом или пассивом
                assets_sum = df[df['amount'] > 0]['amount'].sum()
                liabilities_sum = abs(df[df['amount'] < 0]['amount'].sum())
                total_assets += assets_sum
                total_liabilities += liabilities_sum
                sign = 'Mixed'
            elif instrument_type == 'correspondent_accounts':
                # Корсчета тоже могут быть активами или пассивами
                assets_sum = df[df['amount'] > 0]['amount'].sum()
                liabilities_sum = abs(df[df['amount'] < 0]['amount'].sum())
                total_assets += assets_sum
                total_liabilities += liabilities_sum
                sign = 'Mixed'
            else:
                sign = 'Off-Balance'

            summary.append({
                'instrument_type': instrument_type,
                'count': count,
                'total_amount': df['amount'].sum(),
                'avg_amount': df['amount'].mean(),
                'sign': sign
            })

        summary_df = pd.DataFrame(summary)
        summary_path = self.output_dir / 'summary_statistics.csv'
        summary_df.to_csv(summary_path, index=False)

        logger.info(f"\n{'='*60}")
        logger.info("SUMMARY STATISTICS")
        logger.info(f"{'='*60}")
        logger.info(f"Total positions generated: {total_positions:,}")
        logger.info(f"Total Assets (approx): {total_assets:,.2f}")
        logger.info(f"Total Liabilities (approx): {total_liabilities:,.2f}")
        logger.info(f"Net Position: {total_assets - total_liabilities:,.2f}")
        logger.info(f"{'='*60}\n")
        logger.info(summary_df.to_string())
        logger.info(f"\nSummary saved to {summary_path}")


def main():
    """
    Главная функция для генерации mock данных.
    """
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Parameters
    as_of_date = date(2024, 12, 31)  # Дата баланса
    output_dir = Path(__file__).parent.parent.parent / 'data' / 'mock_data'
    total_positions = 200_000

    logger.info("="*60)
    logger.info("ALM Mock Data Generator")
    logger.info("="*60)
    logger.info(f"As of date: {as_of_date}")
    logger.info(f"Total positions: {total_positions:,}")
    logger.info(f"Output directory: {output_dir}")
    logger.info("="*60)

    # Initialize generator
    generator = MockDataGenerator(
        as_of_date=as_of_date,
        output_dir=output_dir,
        random_seed=42
    )

    # Generate all instruments
    datasets = generator.generate_all_instruments(total_positions=total_positions)

    # Save to CSV
    generator.save_to_csv(datasets)

    logger.info("\nMock data generation completed successfully!")


if __name__ == '__main__':
    main()
