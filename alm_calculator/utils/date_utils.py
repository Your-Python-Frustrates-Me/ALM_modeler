# utils/date_utils.py
from datetime import date, timedelta
from typing import List


def assign_to_bucket(base_date: date, target_date: date, buckets: List[str]) -> str:
    """
    Определяет, в какую временную корзину попадает дата.

    Args:
        base_date: Базовая дата (calculation date)
        target_date: Целевая дата (maturity/CF date)
        buckets: Список названий корзин, например ['0-30d', '30-90d', ...]

    Returns:
        Название корзины

    Example:
        >>> assign_to_bucket(date(2025, 1, 15), date(2025, 2, 10), ['0-30d', '30-90d'])
        '0-30d'
    """
    days_diff = (target_date - base_date).days

    # Определяем границы корзин
    # Формат: '0-30d', '30-90d', '90-180d', '180-365d', '1-2y', '2y+'

    if days_diff <= 0:
        return 'overnight'
    elif days_diff <= 30:
        return '0-30d'
    elif days_diff <= 90:
        return '30-90d'
    elif days_diff <= 180:
        return '90-180d'
    elif days_diff <= 365:
        return '180-365d'
    elif days_diff <= 730:
        return '1-2y'
    else:
        return '2y+'


def parse_bucket_to_days(bucket: str) -> tuple[int, int]:
    """
    Конвертирует название бакета в диапазон дней.

    Returns:
        (min_days, max_days)
    """
    mapping = {
        'overnight': (0, 1),
        '0-30d': (0, 30),
        '30-90d': (30, 90),
        '90-180d': (90, 180),
        '180-365d': (180, 365),
        '1-2y': (365, 730),
        '2y+': (730, 36500)  # До 100 лет
    }
    return mapping.get(bucket, (0, 36500))
