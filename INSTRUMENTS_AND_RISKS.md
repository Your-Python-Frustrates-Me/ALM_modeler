# Инструменты и шаблоны рисков для ALM Calculator

## 📋 Обзор

Данный релиз добавляет полный набор классов финансовых инструментов и шаблоны для расчета основных ALM-рисков.

## 🎯 Созданные классы инструментов

### 1. Межбанковские операции

#### `InterbankLoan` (МБК)
- **Файл:** `alm_calculator/models/instruments/interbank.py`
- **Функциональность:**
  - Поддержка МБК-размещения (актив) и МБК-привлечения (пассив)
  - Расчет процентного риска для краткосрочных инструментов
  - Учет в гэпах ликвидности
  - Автоматическое определение направления операции по знаку amount

#### `Repo` и `ReverseRepo` (РЕПО)
- **Файл:** `alm_calculator/models/instruments/repo.py`
- **Функциональность:**
  - Прямое РЕПО (привлечение ликвидности)
  - Обратное РЕПО (размещение ликвидности)
  - Учет обеспечения (collateral_type, haircut)
  - Моделирование вероятности пролонгации

### 2. Расчетные счета

#### `CurrentAccount` (Текущие счета)
- **Файл:** `alm_calculator/models/instruments/current_account.py`
- **Функциональность:**
  - Behavioral assumptions для устойчивой и неустойчивой частей
  - Runoff rates для моделирования оттока средств
  - Поддержка различных типов клиентов (retail, corporate, government)
  - Условный срок жизни устойчивой части

#### `CorrespondentAccount` (Корсчета и ЛОРО)
- **Файл:** `alm_calculator/models/instruments/correspondent_account.py`
- **Функциональность:**
  - НОСТРО счета (актив)
  - ЛОРО счета (пассив)
  - Корсчет в ЦБ РФ (обязательные резервы и операционный остаток)
  - Моделирование доступности средств

### 3. Прочие балансовые позиции

#### `OtherAsset` и `OtherLiability`
- **Файл:** `alm_calculator/models/instruments/other_balance_items.py`
- **Функциональность:**
  - Основные средства
  - Дебиторская/кредиторская задолженность
  - Резервы
  - Расчеты с бюджетом и персоналом
  - Ликвидационная стоимость и haircut для активов

### 4. Внебалансовые инструменты

#### `OffBalanceInstrument`
- **Файл:** `alm_calculator/models/instruments/off_balance.py`
- **Функциональность:**
  - Гарантии выданные и полученные
  - Незадействованные кредитные линии
  - Форварды и свопы (FX, IRS, XCCY)
  - Опционы (упрощенная модель)
  - Draw-down probability для contingent obligations

## 📊 Шаблоны расчета рисков

### 1. Горизонт выживания (Survival Horizon)

**Класс:** `SurvivalHorizonCalculator`
**Файл:** `alm_calculator/risks/liquidity/survival_horizon.py`

**Возможности:**
- Расчет горизонта выживания по валютам
- Учет буфера ликвидных активов (HLA)
- Стресс-сценарии (base, moderate, severe)
- Кумулятивные гэпы ликвидности
- Экспорт результатов в Excel с графиками

**Пример использования:**
```python
from alm_calculator.risks.liquidity.survival_horizon import SurvivalHorizonCalculator
from datetime import date

calculator = SurvivalHorizonCalculator(
    calculation_date=date(2025, 1, 15),
    liquidity_buckets=['overnight', '2-7d', '8-14d', '15-30d', '30-90d', '90-180d', '180-365d', '1y+'],
    stress_scenario='moderate'
)

results = calculator.calculate(
    instruments=instruments_list,
    risk_params=risk_params,
    liquid_assets_buffer=Decimal('1000000000')  # 1 млрд руб буфер
)

# Экспорт в Excel
from alm_calculator.risks.liquidity.survival_horizon import export_to_excel
export_to_excel(results, 'survival_horizon.xlsx')
```

### 2. Гэпы ликвидности по валютам

**Класс:** `CurrencyLiquidityGapCalculator`
**Файл:** `alm_calculator/risks/liquidity/currency_liquidity_gaps.py`

**Возможности:**
- Inflows и outflows по временным бакетам
- Чистые гэпы (net gaps)
- Кумулятивные гэпы
- Coverage ratios (коэффициенты покрытия)
- Анализ критических зон
- Экспорт в Excel с графиками

**Пример использования:**
```python
from alm_calculator.risks.liquidity.currency_liquidity_gaps import CurrencyLiquidityGapCalculator

calculator = CurrencyLiquidityGapCalculator(
    calculation_date=date(2025, 1, 15),
    liquidity_buckets=['overnight', '2-7d', '8-14d', '15-30d', '30-90d', '90-180d'],
    target_currencies=['RUB', 'USD', 'EUR']
)

gaps_by_currency = calculator.calculate(
    instruments=instruments_list,
    risk_params=risk_params
)

# Анализ
analysis = calculator.analyze_gaps(gaps_by_currency)

# Экспорт
from alm_calculator.risks.liquidity.currency_liquidity_gaps import export_to_excel
export_to_excel(gaps_by_currency, analysis, 'liquidity_gaps.xlsx')
```

### 3. Процентные гэпы по валютам

**Класс:** `CurrencyInterestRateGapCalculator`
**Файл:** `alm_calculator/risks/interest_rate/currency_interest_rate_gaps.py`

**Возможности:**
- Rate-sensitive assets (RSA) и liabilities (RSL) по бакетам
- Процентные гэпы (Gap = RSA - RSL)
- Кумулятивные гэпы
- Gap ratios (Gap / Total Assets)
- Sensitivity analysis (NII impact, EVE impact)
- Сценарный анализ параллельного сдвига кривой доходности
- Экспорт в Excel с графиками

**Пример использования:**
```python
from alm_calculator.risks.interest_rate.currency_interest_rate_gaps import CurrencyInterestRateGapCalculator

calculator = CurrencyInterestRateGapCalculator(
    calculation_date=date(2025, 1, 15),
    repricing_buckets=['0-1m', '1-3m', '3-6m', '6-12m', '1-2y', '2-3y', '3-5y', '5-7y', '7-10y', '10y+'],
    target_currencies=['RUB', 'USD', 'EUR']
)

gaps_by_currency = calculator.calculate(
    instruments=instruments_list,
    risk_params=risk_params
)

# Sensitivity analysis (шок +100 б.п.)
sensitivity = calculator.calculate_sensitivity(
    gaps_by_currency,
    rate_shock_bps=100
)

# Экспорт
from alm_calculator.risks.interest_rate.currency_interest_rate_gaps import export_to_excel
export_to_excel(gaps_by_currency, sensitivity, 'interest_rate_gaps.xlsx')
```

## 🏗️ Архитектурные улучшения

### Обновленный `InstrumentType` enum

```python
class InstrumentType(str, Enum):
    LOAN = "loan"
    DEPOSIT = "deposit"

    # Interbank operations
    INTERBANK_LOAN = "interbank_loan"
    REPO = "repo"
    REVERSE_REPO = "reverse_repo"

    # Accounts
    CURRENT_ACCOUNT = "current_account"
    CORRESPONDENT_ACCOUNT = "correspondent_account"

    # Other balance sheet items
    OTHER_ASSET = "other_asset"
    OTHER_LIABILITY = "other_liability"

    # Off-balance sheet
    OFF_BALANCE = "off_balance"

    OTHER = "other"
```

### Обновленный `InstrumentFactory`

`InstrumentFactory` теперь поддерживает все новые типы инструментов и автоматически создает соответствующие классы на основе данных баланса.

## 📁 Структура проекта

```
alm_calculator/
├── core/
│   ├── base_instrument.py          # Обновлен InstrumentType enum
│   └── exceptions.py
├── models/
│   ├── instruments/
│   │   ├── __init__.py             # Новый
│   │   ├── loan.py
│   │   ├── deposit.py
│   │   ├── interbank.py            # Новый
│   │   ├── repo.py                 # Новый
│   │   ├── current_account.py      # Новый
│   │   ├── correspondent_account.py # Новый
│   │   ├── other_balance_items.py  # Новый
│   │   └── off_balance.py          # Новый
│   └── instrument_factory.py       # Обновлен
├── risks/
│   ├── __init__.py                 # Новый
│   ├── liquidity/
│   │   ├── __init__.py             # Новый
│   │   ├── survival_horizon.py     # Новый
│   │   └── currency_liquidity_gaps.py # Новый
│   └── interest_rate/
│       ├── __init__.py             # Новый
│       └── currency_interest_rate_gaps.py # Новый
└── utils/
    └── date_utils.py
```

## 🎯 Ключевые особенности

### 1. Behavioral Assumptions

Все инструменты поддерживают метод `apply_assumptions()` для применения модельных допущений:

```python
# Пример для текущих счетов
assumptions = {
    'stable_portion': 0.40,
    'avg_life_days': 180,
    'runoff_rates': {
        'overnight': 0.05,
        '2-7d': 0.10,
        '8-14d': 0.15,
        '15-30d': 0.30
    }
}

current_account.apply_assumptions(assumptions)
```

### 2. Векторизация

Все расчеты используют pandas для векторизации операций, что обеспечивает высокую производительность для 200k+ позиций.

### 3. Логирование

Все модули используют structured logging для отслеживания расчетов:

```python
logger.info(
    "Calculated survival horizon",
    extra={
        'currency': 'RUB',
        'survival_days': 45,
        'buffer': 1000000000
    }
)
```

### 4. Excel Export

Все шаблоны рисков включают функции экспорта в Excel с:
- Форматированными таблицами
- Графиками
- Подсветкой критических значений
- Автоматическими расчетами

## 🔜 Следующие шаги

1. **Создать unit-тесты** для всех новых классов
2. **Добавить конфигурационные файлы** для параметров расчета
3. **Создать Excel-шаблоны** для ввода behavioral assumptions
4. **Разработать главный калькулятор** (engine/calculator.py) для оркестрации всех расчетов
5. **Добавить сценарный анализ** для стресс-тестирования

## 📚 Зависимости

Для работы новых модулей требуются:
- `pandas >= 1.5.0`
- `numpy >= 1.23.0`
- `openpyxl >= 3.0.0` (для экспорта в Excel)
- `pydantic >= 2.0.0`

## 💡 Примечания

- Все суммы хранятся в `Decimal` для точности
- Даты используют `datetime.date` (не `datetime.datetime`)
- Type hints используются везде для статической проверки типов
- Docstrings следуют Google style
- Все модули совместимы с Python 3.10+

---

**Автор:** Claude (Anthropic)
**Дата:** 2025-11-17
**Версия:** 1.0.0
