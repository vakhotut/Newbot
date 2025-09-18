# ltc.py
import aiohttp
import asyncio
from typing import Optional, Tuple, Dict, Any
from config import config
from hdwallet import get_address_from_path
import db

class LTCBitAPSAPI:
    def __init__(self):
        self.base_url = config.API_BASE_URL
        self.session = None
        self.rate_limit_remaining = 15  # Стандартный лимит
        self.rate_limit_reset = 5       # Сброс через 5 секунд

    async def get_session(self) -> aiohttp.ClientSession:
        """Получение или создание aiohttp сессии"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def make_request(self, endpoint: str, params: Optional[dict] = None) -> Optional[dict]:
        """
        Универсальный метод для выполнения запросов к API BitAPS
        с учетом ограничений скорости запросов
        """
        # Проверяем лимит запросов
        if self.rate_limit_remaining <= 0:
            await asyncio.sleep(self.rate_limit_reset)
            self.rate_limit_remaining = 15

        session = await self.get_session()
        url = f"{self.base_url}{endpoint}"
        
        try:
            async with session.get(url, params=params) as response:
                # Обновляем информацию о лимитах
                self.rate_limit_remaining = int(response.headers.get('Ratelimit-Remaining', 15))
                self.rate_limit_reset = int(response.headers.get('Ratelimit-Reset', 5))
                
                if response.status == 200:
                    data = await response.json()
                    return data
                elif response.status == 429:
                    # Превышен лимит запросов
                    await asyncio.sleep(self.rate_limit_reset)
                    return await self.make_request(endpoint, params)
                else:
                    print(f"API Error: {response.status} - {await response.text()}")
                    return None
        except Exception as e:
            print(f"Request failed: {e}")
            return None

    async def get_address_state(self, address: str) -> Optional[dict]:
        """Получение состояния адреса"""
        endpoint = f"/address/state/{address}"
        return await self.make_request(endpoint)

    async def get_address_transactions(self, address: str, limit: int = 10, page: int = 1) -> Optional[dict]:
        """Получение транзакций адреса"""
        endpoint = f"/address/transactions/{address}"
        params = {
            'limit': limit,
            'page': page,
            'mode': 'brief'
        }
        return await self.make_request(endpoint, params)

    async def get_unconfirmed_transactions(self, address: str) -> Optional[dict]:
        """Получение неподтвержденных транзакций адреса"""
        endpoint = f"/address/unconfirmed/transactions/{address}"
        return await self.make_request(endpoint)

    async def get_transaction(self, tx_hash: str) -> Optional[dict]:
        """Получение информации о транзакции"""
        endpoint = f"/transaction/{tx_hash}"
        return await self.make_request(endpoint)

    async def create_ltc_address(self, user_id: int) -> Optional[str]:
        """
        Создание нового LTC-адреса с использованием HD-кошелька
        Для каждого пользователя генерируется уникальный адрес на основе его ID
        """
        try:
            # Используем ID пользователя для генерации уникального пути
            # Формат: m/84'/2'/0'/0/{user_id % 1000000}
            # Ограничиваем user_id модулем 1000000 чтобы избежать слишком больших чисел
            derivation_path = f"m/84'/2'/0'/0/{user_id % 1000000}"
            address = get_address_from_path(derivation_path)
            return address
        except Exception as e:
            print(f"Error generating LTC address: {e}")
            return None

    async def check_transaction_status(self, tx_hash: str) -> Tuple[str, int]:
        """Проверка статуса транзакции"""
        data = await self.get_transaction(tx_hash)
        if data and 'data' in data:
            confirmations = data['data'].get('confirmations', 0)
            status = 'confirmed' if confirmations > 0 else 'pending'
            return status, confirmations
        return 'error', 0

# Глобальный экземпляр API
ltc_api = LTCBitAPSAPI()
