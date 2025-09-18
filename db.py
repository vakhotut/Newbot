# db.py
import asyncpg
import asyncio
from contextlib import asynccontextmanager
from config import config
from typing import Optional, List, Dict, Any
import logging
from hdwallet import create_ltc_address_for_user

# Настройка логирования
logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.pool = None

    async def init_pool(self):
        """Инициализация пула соединений с PostgreSQL"""
        if not self.pool:
            self.pool = await asyncpg.create_pool(
                dsn=config.DATABASE_URL,
                min_size=5,
                max_size=20,
                command_timeout=60
            )

    @asynccontextmanager
    async def get_connection(self):
        """Контекстный менеджер для получения соединения"""
        if not self.pool:
            await self.init_pool()
        async with self.pool.acquire() as connection:
            yield connection

    async def init_db(self):
        """Инициализация таблиц в базе данных"""
        async with self.get_connection() as conn:
            # Таблица пользователей
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    balance BIGINT DEFAULT 0,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            ''')
            
            # Таблица адресов
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS ltc_addresses (
                    user_id BIGINT REFERENCES users(user_id),
                    address TEXT NOT NULL UNIQUE,
                    created_at TIMESTAMP DEFAULT NOW(),
                    PRIMARY KEY (user_id, address)
                )
            ''')
            
            # Таблица транзакций
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS transactions (
                    txid TEXT PRIMARY KEY,
                    user_id BIGINT REFERENCES users(user_id),
                    amount BIGINT,
                    status TEXT CHECK (status IN ('pending', 'confirmed', 'error')),
                    address TEXT,
                    confirmations INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            ''')
            
            # Индексы для оптимизации запросов
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_transactions_user_id ON transactions(user_id)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_transactions_status ON transactions(status)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_ltc_addresses_user_id ON ltc_addresses(user_id)')

    async def create_user_if_not_exists(self, user_id: int) -> None:
        """Создает пользователя, если его еще нет"""
        async with self.get_connection() as conn:
            await conn.execute('''
                INSERT INTO users (user_id, balance)
                VALUES ($1, 0)
                ON CONFLICT (user_id) DO NOTHING
            ''', user_id)

    async def get_user_balance(self, user_id: int) -> int:
        """Получение баланса пользователя"""
        async with self.get_connection() as conn:
            row = await conn.fetchrow(
                'SELECT balance FROM users WHERE user_id = $1',
                user_id
            )
            return row['balance'] if row else 0

    async def update_user_balance(self, user_id: int, amount: int) -> None:
        """Обновление баланса пользователя"""
        async with self.get_connection() as conn:
            # Добавляем пользователя, если его нет
            await self.create_user_if_not_exists(user_id)
            
            await conn.execute('''
                UPDATE users 
                SET balance = balance + $2, updated_at = NOW()
                WHERE user_id = $1
            ''', user_id, amount)

    async def save_ltc_address(self, user_id: int, address: str) -> None:
        """Сохранение LTC-адреса пользователя"""
        async with self.get_connection() as conn:
            # Сначала убедимся, что пользователь существует
            await self.create_user_if_not_exists(user_id)
            
            await conn.execute('''
                INSERT INTO ltc_addresses (user_id, address)
                VALUES ($1, $2)
                ON CONFLICT (user_id, address) 
                DO UPDATE SET address = EXCLUDED.address
            ''', user_id, address)

    async def get_ltc_address(self, user_id: int) -> Optional[str]:
        """Получение LTC-адреса пользователя"""
        async with self.get_connection() as conn:
            row = await conn.fetchrow(
                'SELECT address FROM ltc_addresses WHERE user_id = $1 ORDER BY created_at DESC LIMIT 1',
                user_id
            )
            return row['address'] if row else None

    async def get_or_create_ltc_address(self, user_id: int) -> str:
        """Получает существующий LTC-адрес пользователя или создает новый"""
        async with self.get_connection() as conn:
            # Пытаемся получить существующий адрес
            address = await conn.fetchval(
                'SELECT address FROM ltc_addresses WHERE user_id = $1 ORDER BY created_at DESC LIMIT 1',
                user_id
            )
            
            if address:
                logger.info(f"Found existing LTC address for user {user_id}: {address}")
                return address
            
            # Если адреса нет, создаем новый через HD-кошелек
            logger.info(f"Creating new LTC address for user {user_id}")
            new_address = create_ltc_address_for_user(user_id)
            if new_address:
                await self.save_ltc_address(user_id, new_address)
                logger.info(f"Successfully created LTC address for user {user_id}: {new_address}")
                return new_address
            else:
                error_msg = "Не удалось создать LTC-адрес"
                logger.error(error_msg)
                raise Exception(error_msg)

    async def add_transaction(self, txid: str, user_id: int, amount: int, address: str, status: str = 'pending') -> None:
        """Добавление информации о транзакции"""
        async with self.get_connection() as conn:
            # Сначала убедимся, что пользователь существует
            await self.create_user_if_not_exists(user_id)
            
            await conn.execute('''
                INSERT INTO transactions (txid, user_id, amount, address, status)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (txid) 
                DO UPDATE SET 
                    status = EXCLUDED.status,
                    updated_at = NOW()
            ''', txid, user_id, amount, address, status)

    async def get_transaction(self, txid: str) -> Optional[dict]:
        """Получение информации о транзакции"""
        async with self.get_connection() as conn:
            row = await conn.fetchrow(
                'SELECT * FROM transactions WHERE txid = $1',
                txid
            )
            return dict(row) if row else None

    async def delete_transaction(self, txid: str) -> None:
        """Удаление информации о транзакции"""
        async with self.get_connection() as conn:
            await conn.execute(
                'DELETE FROM transactions WHERE txid = $1',
                txid
            )

    async def get_user_transactions(self, user_id: int, limit: int = 10) -> List[dict]:
        """Получение последних транзакций пользователя"""
        async with self.get_connection() as conn:
            rows = await conn.fetch(
                'SELECT * FROM transactions WHERE user_id = $1 ORDER BY created_at DESC LIMIT $2',
                user_id, limit
            )
            return [dict(row) for row in rows]

# Глобальный экземпляр базы данных
db = Database()
