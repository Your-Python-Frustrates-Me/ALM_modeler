"""
Скрипт для проверки уникальности ID продуктов во всех CSV файлах
"""

import pandas as pd
from pathlib import Path
from collections import Counter

def check_unique_ids(data_dir: Path):
    """
    Проверяет уникальность instrument_id во всех CSV файлах

    Args:
        data_dir: Директория с CSV файлами
    """
    all_ids = []
    file_stats = {}

    # Список CSV файлов
    csv_files = list(data_dir.glob('*.csv'))
    csv_files = [f for f in csv_files if f.name != 'summary_statistics.csv']

    print(f"Проверка уникальности ID в директории: {data_dir}\n")
    print(f"Найдено CSV файлов: {len(csv_files)}\n")

    # Читаем ID из каждого файла
    for csv_file in csv_files:
        try:
            df = pd.read_csv(csv_file)

            if 'instrument_id' not in df.columns:
                print(f"⚠️  {csv_file.name}: отсутствует колонка instrument_id")
                continue

            ids = df['instrument_id'].tolist()
            all_ids.extend(ids)

            # Проверяем уникальность внутри файла
            duplicates_in_file = [id for id, count in Counter(ids).items() if count > 1]

            file_stats[csv_file.name] = {
                'total': len(ids),
                'unique': len(set(ids)),
                'duplicates': duplicates_in_file
            }

            status = "✓" if len(duplicates_in_file) == 0 else "✗"
            print(f"{status} {csv_file.name:30s} | Записей: {len(ids):6d} | Уникальных: {len(set(ids)):6d}")

            if duplicates_in_file:
                print(f"  Дубликаты в файле: {duplicates_in_file[:5]}")  # Показываем первые 5

        except Exception as e:
            print(f"❌ {csv_file.name}: Ошибка при чтении - {e}")

    # Проверяем уникальность между файлами
    print(f"\n{'='*70}")
    print(f"ОБЩАЯ СТАТИСТИКА:")
    print(f"{'='*70}")
    print(f"Всего ID: {len(all_ids)}")
    print(f"Уникальных ID: {len(set(all_ids))}")

    # Ищем дубликаты между файлами
    duplicates_global = [id for id, count in Counter(all_ids).items() if count > 1]

    if duplicates_global:
        print(f"\n❌ НАЙДЕНЫ ДУБЛИКАТЫ МЕЖДУ ФАЙЛАМИ ({len(duplicates_global)} шт.):")
        for dup_id in duplicates_global[:10]:  # Показываем первые 10
            print(f"  - {dup_id}: встречается {Counter(all_ids)[dup_id]} раз")

        # Найдем, в каких файлах встречаются дубликаты
        for dup_id in duplicates_global[:5]:
            files_with_dup = []
            for csv_file in csv_files:
                df = pd.read_csv(csv_file)
                if 'instrument_id' in df.columns and dup_id in df['instrument_id'].values:
                    files_with_dup.append(csv_file.name)
            print(f"\n  {dup_id} найден в файлах: {', '.join(files_with_dup)}")
    else:
        print(f"\n✓ ВСЕ ID УНИКАЛЬНЫ!")

    return len(duplicates_global) == 0


if __name__ == '__main__':
    data_dir = Path(__file__).parent.parent / 'data' / 'mock_data'

    if not data_dir.exists():
        print(f"Директория не найдена: {data_dir}")
        exit(1)

    is_unique = check_unique_ids(data_dir)

    exit(0 if is_unique else 1)
