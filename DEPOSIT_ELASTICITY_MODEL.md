# Модель эластичности депозитов для процентного риска

## Обзор

Модель эластичности депозитов позволяет моделировать изменение объемов депозитов в ответ на изменение процентных ставок. Это критически важно для точной оценки процентного риска, так как традиционные модели предполагают статический баланс и не учитывают поведенческую реакцию клиентов.

### Ключевые особенности

- **Отдельный расчет** от текущего процентного риска
- **Сегментация клиентов**: различная эластичность для физических лиц (ФЛ) и юридических лиц (ЮЛ)
- **Типы депозитов**: до востребования, краткосрочные, среднесрочные, долгосрочные
- **Нелинейные модели**: асимметричная реакция, пороговые эффекты
- **Динамический баланс**: автоматическое построение баланса с обновленными объемами
- **Сравнительный анализ**: статический vs динамический процентный риск

## Математическая модель

### Базовая формула эластичности

```
ΔVolume% = elasticity × ΔRate%
```

где:
- `ΔVolume%` - процентное изменение объема депозитов
- `elasticity` - коэффициент эластичности (обычно отрицательный)
- `ΔRate%` - изменение процентной ставки

### Пример

При эластичности `-0.5` и росте ставки на `2%`:
```
ΔVolume% = -0.5 × 2% = -1%
```
Объем депозитов снизится на 1% (отток к конкурентам).

### Модели эластичности

#### 1. Линейная модель (базовая)

Простая линейная зависимость:
```
ΔVolume = base_elasticity × ΔRate × OriginalVolume
```

#### 2. Асимметричная модель

Различная реакция на рост и падение ставок:
```python
if ΔRate > 0:
    elasticity = positive_shock_elasticity  # Например, -0.6
else:
    elasticity = negative_shock_elasticity  # Например, -0.4
```

**Обоснование**: Клиенты сильнее реагируют на рост ставок конкурентов (переток), чем на снижение своих ставок (инерция).

#### 3. Пороговая модель

Разная эластичность выше и ниже порога:
```python
if abs(ΔRate) < threshold:
    elasticity = below_threshold_elasticity  # Слабая реакция
else:
    elasticity = above_threshold_elasticity  # Сильная реакция
```

**Обоснование**: Малые изменения ставок клиенты могут не замечать или игнорировать.

#### 4. Модель с ограничениями

```python
# Скорость адаптации
volume_change *= adjustment_speed  # 0-1

# Конкурентный фактор
volume_change *= competitive_factor  # >1 для высококонкурентных рынков

# Ограничения
volume_change = min(max_volume_change, volume_change)
new_volume = max(min_remaining_volume * original_volume, new_volume)
```

## Архитектура

### Основные компоненты

```
alm_calculator/
├── risks/interest_rate/
│   ├── deposit_elasticity.py           # Модель эластичности
│   ├── dynamic_balance_irr_calculator.py  # Динамический IRR
│   └── currency_interest_rate_gaps.py   # Стандартный IRR
├── config/
│   └── elasticity_config_example.py    # Конфигурации параметров
└── examples/
    └── elasticity_example.py           # Примеры использования
```

### Основные классы

#### `ElasticityParameters`

Параметры эластичности для конкретного сегмента:

```python
ElasticityParameters(
    customer_segment=CustomerSegment.RETAIL,
    deposit_type=DepositType.DEMAND,
    base_elasticity=-0.3,           # Базовая эластичность
    asymmetric=True,                 # Асимметричная модель
    positive_shock_elasticity=-0.2,  # При росте ставок
    negative_shock_elasticity=-0.4,  # При падении ставок
    adjustment_speed=0.5,            # Скорость адаптации
    lag_days=30,                     # Задержка реакции
    max_volume_change=0.15,          # Максимум 15% изменения
    min_remaining_volume=0.60        # Минимум 60% остается
)
```

#### `DepositElasticityCalculator`

Калькулятор изменений объемов депозитов:

```python
calculator = DepositElasticityCalculator(
    calculation_date=date(2025, 1, 1),
    elasticity_params=create_baseline_elasticity_config()
)

# Расчет изменений
volume_changes = calculator.calculate_volume_changes(
    deposits=deposits,
    rate_shocks={'RUB': 200.0}  # +200 б.п.
)

# Создание динамического баланса
new_deposits, changes_df = calculator.create_dynamic_balance_sheet(
    deposits=deposits,
    rate_shocks={'RUB': 200.0}
)
```

#### `DynamicBalanceIRRCalculator`

Калькулятор процентного риска на динамическом балансе:

```python
calculator = DynamicBalanceIRRCalculator(
    calculation_date=date(2025, 1, 1),
    repricing_buckets=['0-1m', '1-3m', '3-6m', '6-12m', '1-2y', '2-3y'],
    elasticity_params=create_baseline_elasticity_config()
)

result = calculator.calculate_dynamic_irr(
    instruments=instruments,
    rate_shocks={'RUB': 200.0},
    risk_params={'liquidity_buckets': [...]}
)
```

## Использование

### Быстрый старт

```python
from datetime import date
from decimal import Decimal
from alm_calculator.models.instruments.deposit import Deposit
from alm_calculator.risks.interest_rate.dynamic_balance_irr_calculator import (
    DynamicBalanceIRRCalculator
)
from alm_calculator.config.elasticity_config_example import (
    create_baseline_elasticity_config
)

# 1. Создаем депозиты
deposits = [
    Deposit(
        instrument_id="DEP_001",
        amount=Decimal("10000000"),
        currency="RUB",
        interest_rate=0.08,
        start_date=date(2024, 1, 1),
        maturity_date=date(2026, 1, 1),
        is_demand_deposit=True,
        counterparty_type="retail"
    ),
    # ... другие депозиты
]

# 2. Создаем калькулятор
calculator = DynamicBalanceIRRCalculator(
    calculation_date=date(2025, 1, 1),
    repricing_buckets=['0-1m', '1-3m', '3-6m', '6-12m', '1-2y'],
    elasticity_params=create_baseline_elasticity_config()
)

# 3. Рассчитываем динамический IRR
result = calculator.calculate_dynamic_irr(
    instruments=deposits,
    rate_shocks={'RUB': 200.0},  # +200 б.п.
    risk_params={'liquidity_buckets': ['0-30d', '30-90d', '90-180d']}
)

# 4. Анализируем результаты
print("Статический баланс:")
print(f"  NII Impact: {result['static']['sensitivity']['RUB']['nii_impact_1y']}")

print("\nДинамический баланс (с эластичностью):")
print(f"  NII Impact: {result['dynamic']['sensitivity']['RUB']['nii_impact_1y']}")

print("\nРазница:")
print(f"  {result['comparison']['nii_impact_difference']['RUB']}")
```

### Запуск примеров

```bash
cd /home/user/ALM_modeler
python examples/elasticity_example.py
```

Пример создает:
- Портфель из 48 депозитов и 45 кредитов
- Анализ базового сценария (+200 б.п.)
- Сравнение различных конфигураций эластичности
- Анализ различных шоков ставок

Результаты сохраняются в `output/elasticity_*.xlsx`.

## Конфигурации параметров

### Доступные конфигурации

#### 1. Baseline (базовая)

Сбалансированная конфигурация для обычных расчетов:

```python
from alm_calculator.config.elasticity_config_example import (
    create_baseline_elasticity_config
)

config = create_baseline_elasticity_config()
```

**Параметры для ФЛ до востребования:**
- Эластичность: -0.3
- Асимметричная модель
- Скорость адаптации: 0.5
- Задержка: 30 дней
- Макс. изменение: 15%

#### 2. Conservative (консервативная)

Для стресс-тестирования (более сильная реакция):

```python
config = create_conservative_elasticity_config()
```

**Параметры для ФЛ до востребования:**
- Эластичность: -0.5
- Скорость адаптации: 0.7
- Задержка: 15 дней
- Макс. изменение: 25%

#### 3. Optimistic (оптимистичная)

Для базовых сценариев (более слабая реакция):

```python
config = create_optimistic_elasticity_config()
```

**Параметры для ФЛ до востребования:**
- Эластичность: -0.2
- Скорость адаптации: 0.3
- Задержка: 60 дней
- Макс. изменение: 10%

### Создание кастомной конфигурации

```python
from alm_calculator.risks.interest_rate.deposit_elasticity import (
    ElasticityParameters,
    CustomerSegment,
    DepositType
)

custom_config = {
    (CustomerSegment.RETAIL, DepositType.DEMAND): ElasticityParameters(
        customer_segment=CustomerSegment.RETAIL,
        deposit_type=DepositType.DEMAND,
        base_elasticity=-0.25,
        asymmetric=True,
        positive_shock_elasticity=-0.15,
        negative_shock_elasticity=-0.35,
        adjustment_speed=0.6,
        lag_days=20,
        max_volume_change=0.12,
        min_remaining_volume=0.70,
        competitive_factor=1.1
    ),
    # ... другие сегменты
}

calculator = DynamicBalanceIRRCalculator(
    calculation_date=date(2025, 1, 1),
    repricing_buckets=['0-1m', '1-3m', '3-6m'],
    elasticity_params=custom_config
)
```

## Калибровка параметров

### Рекомендации по подбору параметров

#### 1. Анализ исторических данных

```python
# Соберите данные об изменениях объемов депозитов
# и изменениях ставок за прошлые периоды

import pandas as pd
from sklearn.linear_model import LinearRegression

# Данные
historical_data = pd.DataFrame({
    'rate_change': [0.5, 1.0, 1.5, -0.5, -1.0],  # Изменение ставки (%)
    'volume_change': [-0.2, -0.5, -0.7, 0.3, 0.5]  # Изменение объема (%)
})

# Регрессия
model = LinearRegression()
model.fit(
    historical_data[['rate_change']],
    historical_data['volume_change']
)

estimated_elasticity = model.coef_[0]
print(f"Оценочная эластичность: {estimated_elasticity}")
```

#### 2. Экспертные оценки

Используйте мнение экспертов банка о поведении клиентов:

- **Высокая лояльность**: эластичность ближе к 0 (слабая реакция)
- **Низкая лояльность**: эластичность дальше от 0 (сильная реакция)
- **Высокая конкуренция**: больший competitive_factor

#### 3. Бенчмаркинг

Типичные значения эластичности по рынку:

| Сегмент | Тип депозита | Диапазон эластичности |
|---------|--------------|----------------------|
| ФЛ | До востребования | -0.2 до -0.4 |
| ФЛ | Срочные | -0.4 до -0.7 |
| ЮЛ | До востребования | -0.6 до -0.9 |
| ЮЛ | Срочные | -0.8 до -1.2 |

### Валидация модели

```python
# 1. Бэктестинг на исторических данных
# 2. Проверка разумности результатов
# 3. Сравнение с альтернативными моделями

def validate_elasticity_model(calculator, historical_deposits, historical_shocks):
    """
    Проверяет точность модели на исторических данных.
    """
    predictions = []
    actuals = []

    for period, (deposits, shock) in enumerate(zip(historical_deposits, historical_shocks)):
        # Предсказание модели
        volume_changes = calculator.calculate_volume_changes(deposits, shock)
        predicted_change = sum(vc.volume_change for vc in volume_changes)

        # Фактическое изменение
        actual_change = get_actual_change(period)  # Ваша функция

        predictions.append(predicted_change)
        actuals.append(actual_change)

    # Метрики точности
    from sklearn.metrics import mean_absolute_error, r2_score
    mae = mean_absolute_error(actuals, predictions)
    r2 = r2_score(actuals, predictions)

    print(f"MAE: {mae}")
    print(f"R²: {r2}")

    return mae, r2
```

## Интеграция с текущими расчетами

### Сравнение подходов

| Характеристика | Статический баланс | Динамический баланс (эластичность) |
|----------------|-------------------|-----------------------------------|
| Объемы депозитов | Фиксированы | Меняются при изменении ставок |
| Сложность | Низкая | Средняя |
| Точность | Ниже | Выше |
| Использование | Стандартные расчеты | Стресс-тесты, прогнозы |

### Когда использовать

**Динамический баланс рекомендуется для:**

1. **Стресс-тестирование**: оценка рисков при больших шоках ставок
2. **Долгосрочное планирование**: прогнозирование структуры баланса
3. **ALM стратегия**: оптимизация соотношения активов и пассивов
4. **Ценообразование**: анализ влияния изменения ставок на депозиты

**Статический баланс достаточен для:**

1. Регулярной отчетности
2. Малых изменений ставок (< 50 б.п.)
3. Краткосрочных горизонтов (< 1 месяца)

## Тестирование

### Запуск тестов

```bash
cd /home/user/ALM_modeler
pytest tests/test_deposit_elasticity.py -v
pytest tests/test_dynamic_balance_irr.py -v
```

### Основные тесты

- `test_calculate_volume_changes_positive_shock`: реакция на рост ставок
- `test_calculate_volume_changes_negative_shock`: реакция на падение ставок
- `test_min_remaining_volume_constraint`: проверка ограничений
- `test_asymmetric_positive_vs_negative_shock`: асимметричная модель
- `test_static_vs_dynamic_gaps_different`: различия статики и динамики

## Ограничения и допущения

### Допущения модели

1. **Линейность внутри сегмента**: эластичность постоянна для всех депозитов сегмента
2. **Независимость**: изменения объемов не зависят от других факторов (кроме ставки)
3. **Мгновенная реакция**: при `adjustment_speed=1.0` реакция происходит сразу
4. **Одновалютность**: эластичность рассчитывается отдельно по валютам

### Ограничения

1. **Требуется калибровка**: параметры нужно настраивать под конкретный банк
2. **Не учитывает**: макроэкономические факторы, сезонность, PR-кампании
3. **Упрощения**: реальное поведение клиентов сложнее моделей

## Дальнейшее развитие

### Планируемые улучшения

- [ ] Добавление машинного обучения для калибровки параметров
- [ ] Учет сезонности
- [ ] Кросс-валютные эффекты
- [ ] Интеграция с ликвидным риском
- [ ] Dashboard для визуализации результатов

## Контакты и поддержка

Для вопросов и предложений создайте issue в репозитории проекта.

## Лицензия

MIT License - см. LICENSE файл для деталей.
