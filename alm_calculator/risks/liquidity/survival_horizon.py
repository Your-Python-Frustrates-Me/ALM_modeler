"""
Survival Horizon Calculator
Расчет горизонта выживания банка

Горизонт выживания (Survival Horizon) - количество дней, в течение которых банк
может функционировать при отсутствии новых источников фондирования, используя
только имеющиеся ликвидные активы и контрактные денежные потоки.
"""
from typing import List, Dict, Optional
from datetime import date, timedelta
from decimal import Decimal
import pandas as pd
import logging

from alm_calculator.core.base_instrument import BaseInstrument, RiskContribution

logger = logging.getLogger(__name__)


class SurvivalHorizonCalculator:
    """
    Калькулятор горизонта выживания.

    Методология:
    1. Собирает все inflows и outflows по временным бакетам
    2. Рассчитывает кумулятивный gap ликвидности
    3. Определяет дату, когда кумулятивный gap становится отрицательным
    4. Учитывает доступные ликвидные активы (буфер ликвидности)
    """

    def __init__(
        self,
        calculation_date: date,
        liquidity_buckets: List[str],
        stress_scenario: Optional[str] = None
    ):
        """
        Args:
            calculation_date: Дата расчета
            liquidity_buckets: Временные корзины для анализа ликвидности
            stress_scenario: Сценарий стресса ('base', 'moderate', 'severe')
        """
        self.calculation_date = calculation_date
        self.liquidity_buckets = liquidity_buckets
        self.stress_scenario = stress_scenario or 'base'

    def calculate(
        self,
        instruments: List[BaseInstrument],
        risk_params: Dict,
        liquid_assets_buffer: Optional[Decimal] = None
    ) -> Dict:
        """
        Рассчитывает горизонт выживания.

        Args:
            instruments: Список инструментов
            risk_params: Параметры расчета рисков
            liquid_assets_buffer: Буфер высоколиквидных активов (HLA)

        Returns:
            Словарь с результатами:
            {
                'survival_horizon_days': int,
                'survival_horizon_date': date,
                'cumulative_gaps': pd.DataFrame,
                'liquid_assets_buffer': Decimal,
                'critical_bucket': str
            }
        """
        logger.info(
            f"Starting survival horizon calculation",
            extra={
                'calculation_date': str(self.calculation_date),
                'stress_scenario': self.stress_scenario,
                'instruments_count': len(instruments)
            }
        )

        # 1. Собираем cash flows по всем инструментам
        cash_flows_by_currency = self._collect_cash_flows(instruments, risk_params)

        # 2. Для каждой валюты рассчитываем горизонт выживания
        results_by_currency = {}

        for currency, cash_flows in cash_flows_by_currency.items():
            # Применяем стресс-коэффициенты
            stressed_cash_flows = self._apply_stress_scenario(cash_flows)

            # Рассчитываем кумулятивные гэпы
            cumulative_gaps = self._calculate_cumulative_gaps(stressed_cash_flows)

            # Определяем буфер ликвидных активов для этой валюты
            currency_buffer = liquid_assets_buffer if currency == 'RUB' else Decimal(0)
            # TODO: Распределить buffer по валютам

            # Находим горизонт выживания
            horizon_result = self._determine_survival_horizon(
                cumulative_gaps,
                currency_buffer
            )

            results_by_currency[currency] = {
                'survival_horizon_days': horizon_result['days'],
                'survival_horizon_date': horizon_result['date'],
                'cumulative_gaps': cumulative_gaps,
                'liquid_assets_buffer': currency_buffer,
                'critical_bucket': horizon_result['critical_bucket']
            }

            logger.info(
                f"Survival horizon for {currency}: {horizon_result['days']} days",
                extra={
                    'currency': currency,
                    'survival_days': horizon_result['days'],
                    'survival_date': str(horizon_result['date']),
                    'buffer': float(currency_buffer)
                }
            )

        # 3. Определяем минимальный горизонт (самая критичная валюта)
        min_horizon = min(
            r['survival_horizon_days']
            for r in results_by_currency.values()
        )

        return {
            'overall_survival_horizon_days': min_horizon,
            'by_currency': results_by_currency,
            'stress_scenario': self.stress_scenario,
            'calculation_date': self.calculation_date
        }

    def _collect_cash_flows(
        self,
        instruments: List[BaseInstrument],
        risk_params: Dict
    ) -> Dict[str, pd.DataFrame]:
        """
        Собирает cash flows по всем инструментам, группируя по валютам.

        Returns:
            Dict[currency, DataFrame] с колонками [bucket, inflow, outflow, net_flow]
        """
        cash_flows_by_currency = {}

        for instrument in instruments:
            # Рассчитываем risk contribution для инструмента
            contribution = instrument.calculate_risk_contribution(
                self.calculation_date,
                risk_params
            )

            # Группируем cash flows по валюте
            for currency, exposure in contribution.currency_exposure.items():
                if currency not in cash_flows_by_currency:
                    cash_flows_by_currency[currency] = {
                        bucket: {'inflow': Decimal(0), 'outflow': Decimal(0)}
                        for bucket in self.liquidity_buckets
                    }

                # Распределяем cash flows по бакетам
                for bucket, cf_amount in contribution.cash_flows.items():
                    if bucket not in cash_flows_by_currency[currency]:
                        cash_flows_by_currency[currency][bucket] = {
                            'inflow': Decimal(0),
                            'outflow': Decimal(0)
                        }

                    if cf_amount > 0:
                        cash_flows_by_currency[currency][bucket]['inflow'] += cf_amount
                    else:
                        cash_flows_by_currency[currency][bucket]['outflow'] += abs(cf_amount)

        # Конвертируем в DataFrame
        result = {}
        for currency, buckets_data in cash_flows_by_currency.items():
            df_data = []
            for bucket in self.liquidity_buckets:
                bucket_data = buckets_data.get(bucket, {'inflow': Decimal(0), 'outflow': Decimal(0)})
                df_data.append({
                    'bucket': bucket,
                    'inflow': float(bucket_data['inflow']),
                    'outflow': float(bucket_data['outflow']),
                    'net_flow': float(bucket_data['inflow'] - bucket_data['outflow'])
                })

            result[currency] = pd.DataFrame(df_data)

        return result

    def _apply_stress_scenario(self, cash_flows: pd.DataFrame) -> pd.DataFrame:
        """
        Применяет стресс-коэффициенты к денежным потокам.

        Стресс сценарии:
        - base: без изменений
        - moderate: inflows -20%, outflows +10%
        - severe: inflows -40%, outflows +30%
        """
        stressed_cf = cash_flows.copy()

        if self.stress_scenario == 'moderate':
            stressed_cf['inflow'] = stressed_cf['inflow'] * 0.80  # -20%
            stressed_cf['outflow'] = stressed_cf['outflow'] * 1.10  # +10%
        elif self.stress_scenario == 'severe':
            stressed_cf['inflow'] = stressed_cf['inflow'] * 0.60  # -40%
            stressed_cf['outflow'] = stressed_cf['outflow'] * 1.30  # +30%

        # Пересчитываем net flow
        stressed_cf['net_flow'] = stressed_cf['inflow'] - stressed_cf['outflow']

        return stressed_cf

    def _calculate_cumulative_gaps(self, cash_flows: pd.DataFrame) -> pd.DataFrame:
        """
        Рассчитывает кумулятивные гэпы ликвидности.

        Returns:
            DataFrame с дополнительной колонкой 'cumulative_gap'
        """
        gaps = cash_flows.copy()
        gaps['cumulative_gap'] = gaps['net_flow'].cumsum()

        return gaps

    def _determine_survival_horizon(
        self,
        cumulative_gaps: pd.DataFrame,
        liquid_assets_buffer: Decimal
    ) -> Dict:
        """
        Определяет горизонт выживания.

        Логика:
        - Начинаем с буфера ликвидных активов
        - Добавляем кумулятивный gap на каждую дату
        - Находим первую дату, когда позиция становится отрицательной

        Returns:
            {
                'days': int,
                'date': date,
                'critical_bucket': str
            }
        """
        buffer = float(liquid_assets_buffer)

        for idx, row in cumulative_gaps.iterrows():
            cumulative_position = buffer + row['cumulative_gap']

            if cumulative_position < 0:
                # Достигли отрицательной позиции
                critical_bucket = row['bucket']
                days_to_critical = self._bucket_to_days(critical_bucket)

                return {
                    'days': days_to_critical,
                    'date': self.calculation_date + timedelta(days=days_to_critical),
                    'critical_bucket': critical_bucket
                }

        # Если не достигли отрицательной позиции - горизонт выживания > последний бакет
        last_bucket = cumulative_gaps.iloc[-1]['bucket']
        last_bucket_days = self._bucket_to_days(last_bucket)

        return {
            'days': last_bucket_days,
            'date': self.calculation_date + timedelta(days=last_bucket_days),
            'critical_bucket': f'{last_bucket}+'
        }

    def _bucket_to_days(self, bucket: str) -> int:
        """
        Конвертирует название бакета в количество дней (конец периода бакета).
        """
        bucket_mapping = {
            'overnight': 1,
            '2-7d': 7,
            '8-14d': 14,
            '15-30d': 30,
            '30-90d': 90,
            '90-180d': 180,
            '180-365d': 365,
            '1-2y': 730,
            '2y+': 1095
        }

        return bucket_mapping.get(bucket, 30)


def export_to_excel(results: Dict, output_path: str) -> None:
    """
    Экспортирует результаты в Excel для анализа.

    Args:
        results: Результаты расчета от SurvivalHorizonCalculator
        output_path: Путь к выходному Excel файлу
    """
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils.dataframe import dataframe_to_rows

    wb = openpyxl.Workbook()

    # Лист 1: Summary
    ws_summary = wb.active
    ws_summary.title = "Summary"

    ws_summary['A1'] = "Survival Horizon Analysis"
    ws_summary['A1'].font = Font(size=14, bold=True)

    ws_summary['A3'] = "Calculation Date:"
    ws_summary['B3'] = results['calculation_date'].strftime('%Y-%m-%d')

    ws_summary['A4'] = "Stress Scenario:"
    ws_summary['B4'] = results['stress_scenario']

    ws_summary['A5'] = "Overall Survival Horizon (days):"
    ws_summary['B5'] = results['overall_survival_horizon_days']
    ws_summary['B5'].font = Font(bold=True, color="FF0000" if results['overall_survival_horizon_days'] < 30 else "000000")

    # Лист 2+: По каждой валюте
    for currency, currency_result in results['by_currency'].items():
        ws = wb.create_sheet(title=f"Currency_{currency}")

        ws['A1'] = f"Survival Horizon - {currency}"
        ws['A1'].font = Font(size=12, bold=True)

        ws['A3'] = "Survival Horizon (days):"
        ws['B3'] = currency_result['survival_horizon_days']

        ws['A4'] = "Survival Date:"
        ws['B4'] = currency_result['survival_horizon_date'].strftime('%Y-%m-%d')

        ws['A5'] = "Critical Bucket:"
        ws['B5'] = currency_result['critical_bucket']

        ws['A6'] = "Liquid Assets Buffer:"
        ws['B6'] = float(currency_result['liquid_assets_buffer'])

        # Cumulative gaps table
        ws['A8'] = "Cumulative Gaps Analysis"
        ws['A8'].font = Font(bold=True)

        cumulative_gaps = currency_result['cumulative_gaps']
        for r_idx, row in enumerate(dataframe_to_rows(cumulative_gaps, index=False, header=True), 9):
            for c_idx, value in enumerate(row, 1):
                cell = ws.cell(row=r_idx, column=c_idx, value=value)
                if r_idx == 9:  # Header
                    cell.font = Font(bold=True)
                    cell.fill = PatternFill(start_color="DDDDDD", end_color="DDDDDD", fill_type="solid")

    wb.save(output_path)
    logger.info(f"Survival horizon results exported to {output_path}")
