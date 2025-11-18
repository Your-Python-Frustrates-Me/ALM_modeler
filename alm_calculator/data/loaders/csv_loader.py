"""
CSV Data Loader for ALM Calculator

Loads balance sheet positions from CSV files and converts them to instrument objects.
"""

import pandas as pd
import logging
from pathlib import Path
from typing import List, Dict, Union, Optional
from datetime import datetime, date
import ast

from alm_calculator.models.instruments.loan import Loan
from alm_calculator.models.instruments.deposit import Deposit
from alm_calculator.models.instruments.interbank import InterbankLoan
from alm_calculator.models.instruments.repo import Repo, ReverseRepo
from alm_calculator.models.instruments.current_account import CurrentAccount
from alm_calculator.models.instruments.correspondent_account import CorrespondentAccount
from alm_calculator.models.instruments.other_balance_items import OtherAsset, OtherLiability
from alm_calculator.models.instruments.off_balance import OffBalanceInstrument
from alm_calculator.core.base_instrument import BaseInstrument

logger = logging.getLogger(__name__)


class CSVDataLoader:
    """
    Загрузчик балансовых данных из CSV файлов.

    Преобразует CSV -> pandas DataFrame -> Instrument objects
    """

    def __init__(self, data_dir: Path):
        """
        Args:
            data_dir: Директория с CSV файлами
        """
        self.data_dir = Path(data_dir)

        if not self.data_dir.exists():
            raise FileNotFoundError(f"Data directory not found: {self.data_dir}")

        # Mapping CSV filenames to instrument classes
        self.instrument_mapping = {
            'loans.csv': Loan,
            'deposits.csv': Deposit,
            'interbank.csv': InterbankLoan,
            'repo.csv': Repo,
            'reverse_repo.csv': ReverseRepo,
            'current_accounts.csv': CurrentAccount,
            'correspondent_accounts.csv': CorrespondentAccount,
            'other_assets.csv': OtherAsset,
            'other_liabilities.csv': OtherLiability,
            'off_balance.csv': OffBalanceInstrument,
        }

    def load_all_instruments(self) -> List[BaseInstrument]:
        """
        Загружает все инструменты из всех CSV файлов.

        Returns:
            List of all instrument objects
        """
        logger.info("Loading all instruments from CSV files")

        all_instruments = []

        for csv_filename, instrument_class in self.instrument_mapping.items():
            csv_path = self.data_dir / csv_filename

            if not csv_path.exists():
                logger.warning(f"CSV file not found: {csv_path}, skipping...")
                continue

            instruments = self._load_instrument_file(csv_path, instrument_class)
            all_instruments.extend(instruments)

            logger.info(
                f"Loaded {len(instruments)} instruments from {csv_filename}",
                extra={'instrument_type': instrument_class.__name__, 'count': len(instruments)}
            )

        logger.info(f"Total instruments loaded: {len(all_instruments)}")

        return all_instruments

    def load_by_type(self, instrument_type: str) -> List[BaseInstrument]:
        """
        Загружает инструменты конкретного типа.

        Args:
            instrument_type: Тип инструмента ('loans', 'deposits', etc.)

        Returns:
            List of instruments of specified type
        """
        csv_filename = f"{instrument_type}.csv"
        csv_path = self.data_dir / csv_filename

        if csv_filename not in self.instrument_mapping:
            raise ValueError(f"Unknown instrument type: {instrument_type}")

        if not csv_path.exists():
            raise FileNotFoundError(f"CSV file not found: {csv_path}")

        instrument_class = self.instrument_mapping[csv_filename]
        instruments = self._load_instrument_file(csv_path, instrument_class)

        logger.info(f"Loaded {len(instruments)} {instrument_type}")

        return instruments

    def _load_instrument_file(
        self,
        csv_path: Path,
        instrument_class: type
    ) -> List[BaseInstrument]:
        """
        Загружает инструменты из одного CSV файла.

        Args:
            csv_path: Путь к CSV файлу
            instrument_class: Класс инструмента

        Returns:
            List of instrument objects
        """
        logger.debug(f"Loading {csv_path}")

        # Read CSV
        df = pd.read_csv(csv_path)

        # Convert to instruments
        instruments = []

        for idx, row in df.iterrows():
            try:
                # Convert row to dict and clean up
                instrument_data = self._prepare_instrument_data(row)

                # Create instrument object
                instrument = instrument_class(**instrument_data)
                instruments.append(instrument)

            except Exception as e:
                logger.error(
                    f"Failed to create instrument from row {idx} in {csv_path}: {e}",
                    extra={'row_index': idx, 'error': str(e)}
                )
                # Continue processing other rows
                continue

        success_rate = len(instruments) / len(df) * 100 if len(df) > 0 else 0
        logger.debug(
            f"Successfully created {len(instruments)}/{len(df)} instruments ({success_rate:.1f}%)"
        )

        return instruments

    def _prepare_instrument_data(self, row: pd.Series) -> Dict:
        """
        Подготавливает данные из CSV строки для создания инструмента.

        Преобразует типы данных, парсит даты, обрабатывает None/NaN.

        Args:
            row: Строка из DataFrame

        Returns:
            Dict готовый для передачи в конструктор инструмента
        """
        data = {}

        for key, value in row.items():
            # Skip NaN values
            if pd.isna(value):
                continue

            # Convert dates
            if key.endswith('_date'):
                if isinstance(value, str):
                    try:
                        data[key] = datetime.fromisoformat(value).date()
                    except Exception:
                        logger.warning(f"Failed to parse date: {key}={value}")
                        data[key] = None
                else:
                    data[key] = None

            # Convert amounts to float
            elif key in ['amount', 'notional_amount', 'collateral_value',
                         'pay_leg_amount', 'receive_leg_amount',
                         'utilized_amount', 'available_amount']:
                try:
                    data[key] = float(value)
                except Exception:
                    logger.warning(f"Failed to convert to float: {key}={value}")
                    data[key] = 0.0

            # Parse dict strings (for withdrawal_rates, etc.)
            elif isinstance(value, str) and value.startswith('{'):
                try:
                    data[key] = ast.literal_eval(value)
                except Exception:
                    logger.warning(f"Failed to parse dict: {key}={value}")
                    data[key] = {}

            # Boolean values
            elif key in ['is_demand_deposit', 'is_placement', 'is_transactional',
                         'is_required_reserve', 'is_monetary', 'is_payer']:
                data[key] = bool(value) if not pd.isna(value) else None

            # Float values
            elif key in ['interest_rate', 'repo_rate', 'core_portion', 'avg_life_years',
                         'stable_portion', 'volatility_coefficient', 'haircut',
                         'liquidity_haircut', 'draw_down_probability', 'prepayment_rate']:
                try:
                    data[key] = float(value) if not pd.isna(value) else None
                except Exception:
                    data[key] = None

            # Integer values
            elif key in ['avg_life_days']:
                try:
                    data[key] = int(value) if not pd.isna(value) else None
                except Exception:
                    data[key] = None

            # String values (default)
            else:
                data[key] = str(value) if not pd.isna(value) else None

        return data

    def get_portfolio_summary(self, instruments: List[BaseInstrument]) -> pd.DataFrame:
        """
        Генерирует сводку по портфелю инструментов.

        Args:
            instruments: Список инструментов

        Returns:
            DataFrame со сводной статистикой
        """
        if not instruments:
            return pd.DataFrame()

        # Group by instrument type
        summary_data = []

        instruments_by_type = {}
        for instrument in instruments:
            inst_type = instrument.instrument_type.value
            if inst_type not in instruments_by_type:
                instruments_by_type[inst_type] = []
            instruments_by_type[inst_type].append(instrument)

        for inst_type, inst_list in instruments_by_type.items():
            amounts = [float(inst.amount) for inst in inst_list]

            summary_data.append({
                'instrument_type': inst_type,
                'count': len(inst_list),
                'total_amount': sum(amounts),
                'avg_amount': sum(amounts) / len(amounts) if amounts else 0,
                'min_amount': min(amounts) if amounts else 0,
                'max_amount': max(amounts) if amounts else 0,
            })

        summary_df = pd.DataFrame(summary_data)
        summary_df = summary_df.sort_values('total_amount', ascending=False)

        return summary_df


def load_mock_data(data_dir: Optional[Union[str, Path]] = None) -> List[BaseInstrument]:
    """
    Convenience function для быстрой загрузки mock данных.

    Args:
        data_dir: Директория с данными (default: ./data/mock_data)

    Returns:
        List of all instruments
    """
    if data_dir is None:
        # Default path
        project_root = Path(__file__).parent.parent.parent.parent
        data_dir = project_root / 'data' / 'mock_data'

    loader = CSVDataLoader(data_dir)
    instruments = loader.load_all_instruments()

    return instruments


if __name__ == '__main__':
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Test loader
    logger.info("Testing CSV Data Loader")

    instruments = load_mock_data()

    logger.info(f"\nSuccessfully loaded {len(instruments)} instruments")

    # Print summary
    loader = CSVDataLoader(Path(__file__).parent.parent.parent.parent / 'data' / 'mock_data')
    summary = loader.get_portfolio_summary(instruments)

    logger.info("\nPortfolio Summary:")
    logger.info(f"\n{summary.to_string()}")
