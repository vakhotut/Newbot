import asyncio
from functools import wraps
from typing import Callable, Any

def retry_async(max_retries: int = 3, delay: float = 1.0):
    """
    Декоратор для повторения асинхронных операций при ошибках
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_retries - 1:
                        raise e
                    await asyncio.sleep(delay * (2 ** attempt))  # Экспоненциальная задержка
            return None
        return wrapper
    return decorator

def format_ltc_amount(satoshi: int) -> str:
    """Форматирование суммы LTC из сатоши"""
    return f"{satoshi / 100000000:.8f}"

def parse_ltc_amount(ltc_amount: str) -> int:
    """Парсинг суммы LTC в сатоши"""
    try:
        return int(float(ltc_amount) * 100000000)
    except ValueError:
        return 0
