# ltc.py
import aiohttp
import asyncio
from typing import Optional, Tuple, Dict, Any
from config import config
import logging

# Настройка логирования
logger = logging.getLogger(__name__)

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
                    logger.error(f"API Error: {response.status} - {await response.text()}")
                    return None
        except Exception as e:
            logger.error(f"Request failed: {e}")
            return None

    async def get_address_state(self, address: str) -> Optional[dict]:
        """Получение состояния адреса"""
        logger.info(f"Getting address state for: {address}")
        endpoint = f"/address/state/{address}"
        return await self.make_request(endpoint)

    async def get_address_transactions(self, address: str, limit: int = 10, page: int = 1) -> Optional[dict]:
        """Получение транзакций адреса"""
        logger.info(f"Getting transactions for address: {address}")
        endpoint = f"/address/transactions/{address}"
        params = {
            'limit': limit,
            'page': page,
            'mode': 'brief'
        }
        return await self.make_request(endpoint, params)

    async def get_unconfirmed_transactions(self, address: str) -> Optional[dict]:
        """Получение неподтвержденных транзакций адреса"""
        logger.info(f"Getting unconfirmed transactions for address: {address}")
        endpoint = f"/address/unconfirmed/transactions/{address}"
        return await self.make_request(endpoint)

    async def get_transaction(self, tx_hash: str) -> Optional[dict]:
        """Получение информации о транзакции"""
        logger.info(f"Getting transaction: {tx_hash}")
        endpoint = f"/transaction/{tx_hash}"
        return await self.make_request(endpoint)

    async def check_transaction_status(self, tx_hash: str) -> Tuple[str, int]:
        """Проверка статуса транзакции"""
        logger.info(f"Checking transaction status: {tx_hash}")
        data = await self.get_transaction(tx_hash)
        if data and 'data' in data:
            confirmations = data['data'].get('confirmations', 0)
            status = 'confirmed' if confirmations > 0 else 'pending'
            logger.info(f"Transaction {tx_hash} status: {status}, confirmations: {confirmations}")
            return status, confirmations
        logger.warning(f"Transaction {tx_hash} not found or error")
        return 'error', 0

# Глобальный экземпляр API
ltc_api = LTCBitAPSAPI()
