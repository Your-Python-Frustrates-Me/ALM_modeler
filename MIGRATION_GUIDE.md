# Руководство по миграции: Удаление персональных предпосылок

## Обзор изменений

Этот проект был модифицирован для устранения всех персональных предпосылок (hardcoded assumptions) из кода расчета горизонта выживания. Вместо хардкода конкретных имен контрагентов (Газпром, Казначейство России, Роснефть, и т.д.) теперь используется **конфигурируемая система behavioral assumptions**.

## Основные изменения

### 1. Расчет горизонта выживания (`survival_horizon.py`)

**Было:**
- Расчет по бакетам ликвидности
- Один стресс-сценарий за раз
- Поиск горизонта через итерацию по бакетам

**Стало:**
- Расчет по дневным потокам (daily flows)
- Три сценария одновременно: **NAME**, **MARKET**, **COMBO**
- Поиск горизонта через `np.argmin()` - как в вашем оригинальном коде
- Ограничение горизонта: если < 0 или > 90 дней, устанавливается 90 дней

#### Пример использования:

```python
from alm_calculator.risks.liquidity.survival_horizon import SurvivalHorizonCalculator

# Создаем калькулятор
calculator = SurvivalHorizonCalculator(
    calculation_date=date(2025, 1, 15),
    max_horizon_days=90  # Максимальный горизонт
)

# DataFrame с дневными потоками
# Должен содержать: FLOW_DAY, NAME, MARKET, COMBO, IN_BUFFER (опционально)
daily_flows = pd.DataFrame([...])

# Буфер ликвидности
buffer = {
    'VALUE': 50_000_000_000.0,  # Полная стоимость
    'IMPAIRMENT': 2_000_000_000.0  # Обесценение
}

# Рассчитываем горизонт
results = calculator.calculate(
    daily_flows=daily_flows,
    buffer=buffer,
    exclude_from_buffer=True
)

# Результат:
# {
#     'horizon_days': {'NAME': 45, 'MARKET': 38, 'COMBO': 32},
#     'cumulative_report': DataFrame(...),
#     'calculation_date': date(2025, 1, 15),
#     'buffer_value': 50000000000.0,
#     'buffer_impaired_value': 48000000000.0
# }
```

### 2. Система Behavioral Assumptions (`behavioral_assumptions.py`)

**Новая система** заменяет все персональные предпосылки на конфигурируемые правила:

#### Основные компоненты:

1. **`AssumptionRule`** - правило применения assumptions
   - Условия (conditions): когда применять правило
   - Параметры (assumptions): что применять
   - Приоритет: какое правило важнее

2. **`CounterpartyAssumption`** - assumptions для конкретного контрагента
   - Устойчивая часть средств (stable_portion)
   - Средний срок жизни (avg_life_days)
   - Runoff rates по сценариям
   - Минимальный остаток / максимальный отток

3. **`BehavioralAssumptionsManager`** - менеджер для управления assumptions
   - Загрузка конфигурации из JSON
   - Применение правил к инструментам
   - Приоритизация правил

#### Пример использования:

```python
from alm_calculator.risks.liquidity.behavioral_assumptions import BehavioralAssumptionsManager
import json

# Загружаем конфигурацию
with open('behavioral_assumptions_config.json', 'r') as f:
    config = json.load(f)

manager = BehavioralAssumptionsManager()
manager.load_from_config(config)

# Получаем assumptions для инструмента
instrument_data = {
    'counterparty_name': 'ABC Corporation',
    'counterparty_type': 'corporate',
    'instrument_class': 'ДЮЛ',
    'amount': 5_000_000_000,
    'currency': 'RUB'
}

assumptions = manager.get_assumptions_for_instrument(instrument_data)
# Возвращает словарь с применимыми assumptions
```

## Соответствие старым персональным предпосылкам

Вот как старые хардкоженные предпосылки переведены в конфигурацию:

| Старая предпосылка | Новое решение | Пример в конфигурации |
|-------------------|---------------|---------------------|
| **Газпром**: 1 день, 100% отток, макс 20 млрд | Counterparty assumption с `overnight_treatment=true`, `full_outflow=true`, `maximum_outflow=20000000000` | `EXAMPLE_MAJOR_CORPORATION_A` |
| **Казначейство России**: досрочка, 100% отток, макс 30 млрд | Counterparty assumption с `early_withdrawal_probability=1.0`, `maximum_outflow=30000000000` | `EXAMPLE_TREASURY` |
| **ДепФин Москвы**: высокая стабильность (big) | Counterparty assumption с `stable_portion=0.95` | `EXAMPLE_MUNICIPAL_FINANCE` |
| **ГК МАРС**: средняя стабильность (small) | Counterparty assumption с `stable_portion=0.6` | `EXAMPLE_HOLDING_GROUP` |
| **Роснефть (юани)**: 70% отток в COMBO | Counterparty assumption + правило по валюте CNY | `EXAMPLE_OIL_COMPANY` + `rule_non_resident_cny` |
| **НСО** (неснижаемый остаток): 1 день | Правило по instrument_subclass с `maturity_override=1` | `rule_nso_overnight` |
| **VIP депозиты**: особая обработка | Правило по сумме >= 1 млрд | `rule_vip_deposits` |

## Как мигрировать ваш код

### Шаг 1: Создайте конфигурацию assumptions

Используйте `examples/behavioral_assumptions_config_example.json` как шаблон:

```json
{
  "rules": [
    {
      "rule_id": "your_rule_1",
      "rule_type": "counterparty_type",
      "priority": 100,
      "conditions": {
        "counterparty_type": "corporate"
      },
      "assumptions": {
        "stable_portion": 0.5,
        "avg_life_days": 90,
        "runoff_rates": {
          "NAME": {"overnight": 0.15, "2-7d": 0.20},
          "MARKET": {"overnight": 0.25, "2-7d": 0.30},
          "COMBO": {"overnight": 0.35, "2-7d": 0.40}
        }
      }
    }
  ],
  "counterparty_assumptions": {
    "YOUR_SPECIAL_CLIENT": {
      "stable_portion": 0.9,
      "overnight_treatment": false,
      "maximum_outflow": 10000000000
    }
  }
}
```

### Шаг 2: Замените старую логику расчета

**Было (ваш старый код):**

```python
# Хардкод персональных предпосылок
report.loc[(report["COUNTERPARTY_NAME"] == 'ПАО "ГАЗПРОМ"') &
           (report['INSTRUMENT_CLASS'] == 'ПроцТСЮЛ'), 'CF_DATE'] = new_date_dt + timedelta(days=1)

report.loc[(report["COUNTERPARTY_NAME"] == 'ПАО "ГАЗПРОМ"') &
           (report['INSTRUMENT_CLASS'] == 'ПроцТСЮЛ'), 'LIQUIDITY_GAP'] = 1

# ... и т.д. для каждого контрагента
```

**Стало:**

```python
# Загружаем конфигурацию
manager = load_assumptions_config('config.json')

# Применяем assumptions к каждому инструменту
for idx, row in report.iterrows():
    instrument_data = {
        'counterparty_name': row['COUNTERPARTY_NAME'],
        'counterparty_type': row['COUNTERPARTY_TYPE'],
        'instrument_class': row['INSTRUMENT_CLASS'],
        # ...
    }

    assumptions = manager.get_assumptions_for_instrument(instrument_data)

    # Применяем assumptions
    if 'maturity_override' in assumptions:
        report.at[idx, 'CF_DATE'] = calculation_date + timedelta(days=assumptions['maturity_override'])

    # ...
```

### Шаг 3: Используйте новый калькулятор горизонта выживания

**Было (ваш старый код):**

```python
handler = FlowsHandler(
    flows=all_flows.loc[all_flows['IN_BUFFER'] == 0, ['FLOW_DAY', 'NAME_RUB', 'MARKET_RUB', 'COMBO_RUB']],
    buffer=buffer,
    report_date=new_date_dt
)

report, horizon_days = handler.make_report()
```

**Стало:**

```python
calculator = SurvivalHorizonCalculator(
    calculation_date=new_date_dt,
    max_horizon_days=90
)

results = calculator.calculate(
    daily_flows=all_flows,  # Уже содержит NAME, MARKET, COMBO
    buffer={'VALUE': buffer_value, 'IMPAIRMENT': impairment},
    exclude_from_buffer=True
)

horizon_days = results['horizon_days']  # {'NAME': 45, 'MARKET': 38, 'COMBO': 32}
cumulative_report = results['cumulative_report']
```

## Преимущества новой системы

1. **Нет персональных данных в коде** - все в конфигурации
2. **Легко изменять** - редактируете JSON вместо кода
3. **Прозрачная система приоритетов** - понятно, какие правила применяются
4. **Гибкость** - можно комбинировать условия (по типу, сумме, валюте, и т.д.)
5. **Расширяемость** - легко добавлять новые правила без изменения кода
6. **Тестируемость** - можно тестировать на разных конфигурациях
7. **Соответствие лучшим практикам** - separation of concerns

## Примеры использования

См. файл `examples/survival_horizon_example.py` для полного примера.

## Структура файлов

```
alm_calculator/
  risks/
    liquidity/
      survival_horizon.py          # Новый калькулятор горизонта выживания
      behavioral_assumptions.py     # Система assumptions

examples/
  behavioral_assumptions_config_example.json  # Пример конфигурации
  survival_horizon_example.py                  # Пример использования

MIGRATION_GUIDE.md                  # Этот файл
```

## FAQ

**Q: Можно ли использовать старый подход?**
A: Технически да, но не рекомендуется. Новая система более гибкая и не содержит персональных данных.

**Q: Как добавить нового контрагента с особыми условиями?**
A: Добавьте его в секцию `counterparty_assumptions` конфигурации. Не нужно менять код.

**Q: Что если нужно разное поведение для одного контрагента в разных инструментах?**
A: Используйте комбинированные правила (rule_type: "combined") с условиями по counterparty_name + instrument_class.

**Q: Как отладить, какие assumptions применились к инструменту?**
A: Включите DEBUG logging - BehavioralAssumptionsManager логирует каждое применение правила.

**Q: Поддерживается ли расчет по валютам?**
A: Да, можно добавить правила с условием по currency. Группировка по валютам происходит на уровне потоков.

## Дополнительная информация

Для вопросов и предложений создавайте issue в репозитории проекта.
