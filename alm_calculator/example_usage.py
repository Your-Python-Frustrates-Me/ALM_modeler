# example_usage.py
from datetime import date

from models.instrument_factory import InstrumentFactory
import logging

logging.basicConfig(level=logging.INFO)

# 1. Конфигурация маппинга
mapping_config = {
    'balance_account_patterns': {
        '408': 'deposit',  # Счета клиентов
        '455': 'loan',  # Кредиты
        '501': 'bond',  # Облигации
    }
}

# 2. Создаем фабрику
factory = InstrumentFactory(mapping_config)

# 3. Данные из баланса (пример)
balance_data = [
    {
        'position_id': 'LOAN_001',
        'balance_account': '45502',
        'amount': 5000000.00,
        'currency': 'RUB',
        'start_date': '2024-01-01',
        'maturity_date': '2026-01-01',
        'repricing_date': '2025-06-01',
        'interest_rate': 0.12,
        'counterparty_type': 'corporate',
        'as_of_date': '2025-01-15'
    },
    {
        'position_id': 'DEP_001',
        'balance_account': '40817',
        'amount': 3000000.00,
        'currency': 'RUB',
        'start_date': '2024-06-01',
        'maturity_date': None,  # NMD
        'interest_rate': 0.05,
        'counterparty_type': 'retail',
        'as_of_date': '2025-01-15'
    }
]

# 4. Создаем инструменты
instruments = factory.create_instruments_batch(balance_data)

print(f"\nCreated {len(instruments)} instruments:\n")

for inst in instruments:
    print(f"  {inst.instrument_type}: {inst.instrument_id}")
    print(f"    Amount: {inst.amount:,.2f} {inst.currency}")
    print(f"    Maturity: {inst.maturity_date}")
    print()

# 5. Рассчитываем risk contributions
calculation_date = date(2025, 1, 15)
risk_params = {
    'liquidity_buckets': ['0-30d', '30-90d', '90-180d', '180-365d', '1-2y', '2y+']
}

print("=== RISK CONTRIBUTIONS ===\n")

for inst in instruments:
    # Применяем assumptions (пример для NMD)
    if isinstance(inst, Deposit) and inst.is_demand_deposit:
        assumptions = {
            'core_portion': 0.70,
            'avg_life_years': 3.0,
            'withdrawal_rates': {
                '0-30d': 0.10,
                '30-90d': 0.15,
                '90-180d': 0.05
            }
        }
        inst.apply_assumptions(assumptions)

    # Рассчитываем вклад в риски
    contribution = inst.calculate_risk_contribution(calculation_date, risk_params)

    print(f"{inst.instrument_id}:")
    print(f"  IRR - Repricing: {contribution.repricing_amount:,.2f} on {contribution.repricing_date}")
    if contribution.duration:
        print(f"  IRR - Duration: {contribution.duration:.2f} years, DV01: {contribution.dv01:,.2f}")

    print(f"  Liquidity CF:")
    for bucket, amount in sorted(contribution.cash_flows.items()):
        print(f"    {bucket}: {amount:,.2f}")

    print(f"  FX Exposure: {contribution.currency_exposure}")
    print()