import aiohttp
import asyncio
from typing import Optional, Tuple, Dict, Any
from config import config

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

    async def create_ltc_address(self) -> Optional[str]:
        """
        Создание нового LTC-адреса
        ВАЖНО: В документации BitAPS не указан прямой метод создания адресов.
        Этот метод может потребовать адаптации под конкретную реализацию API.
        """
        # Это предположительная реализация - необходимо уточнить в документации BitAPS
        try:
            # Альтернативный подход: генерация адреса на стороне клиента
            import hashlib
            import base58
            import ecdsa
            import os
            
            # Генерация приватного ключа
            private_key = os.urandom(32)
            
            # Получение публичного ключа
            sk = ecdsa.SigningKey.from_string(private_key, curve=ecdsa.SECP256k1)
            vk = sk.get_verifying_key()
            public_key = b'\x04' + vk.to_string()
            
            # Хеширование публичного ключа
            sha256 = hashlib.sha256(public_key).digest()
            ripemd160 = hashlib.new('ripemd160', sha256).digest()
            
            # Добавление префикса сети Litecoin (0x30 для mainnet)
            network_byte = b'\x30'
            payload = network_byte + ripemd160
            
            # Двойное хеширование для checksum
            checksum = hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
            
            # Формирование адреса
            address = base58.b58encode(payload + checksum).decode('utf-8')
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
