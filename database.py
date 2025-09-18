import asyncpg
import os
from datetime import datetime

class Database:
    def __init__(self):
        self.conn = None
    
    async def connect(self):
        self.conn = await asyncpg.connect(
            host=os.getenv('DB_HOST'),
            port=os.getenv('DB_PORT'),
            database=os.getenv('DB_NAME'),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD')
        )
        
        await self.create_tables()
    
    async def create_tables(self):
        await self.conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                user_id BIGINT UNIQUE NOT NULL,
                balance DECIMAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW()
            )
        ''')
        
        await self.conn.execute('''
            CREATE TABLE IF NOT EXISTS invoices (
                id SERIAL PRIMARY KEY,
                invoice_id VARCHAR(100) UNIQUE NOT NULL,
                user_id BIGINT NOT NULL,
                amount DECIMAL NOT NULL,
                address VARCHAR(100) NOT NULL,
                crypto VARCHAR(10) NOT NULL,
                status VARCHAR(20) DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT NOW(),
                updated_at TIMESTAMP DEFAULT NOW()
            )
        ''')
        
        await self.conn.execute('''
            CREATE TABLE IF NOT EXISTS purchases (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                product_id INTEGER NOT NULL,
                product_name VARCHAR(100) NOT NULL,
                amount DECIMAL NOT NULL,
                district VARCHAR(50),
                delivery_type VARCHAR(50),
                created_at TIMESTAMP DEFAULT NOW()
            )
        ''')
        
        await self.conn.execute('''
            CREATE TABLE IF NOT EXISTS products (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                price DECIMAL NOT NULL,
                description TEXT
            )
        ''')
    
    async def user_exists(self, user_id):
        return await self.conn.fetchval(
            'SELECT 1 FROM users WHERE user_id = $1',
            user_id
        )
    
    async def create_user(self, user_id):
        await self.conn.execute(
            'INSERT INTO users (user_id) VALUES ($1)',
            user_id
        )
    
    async def get_balance(self, user_id):
        return await self.conn.fetchval(
            'SELECT balance FROM users WHERE user_id = $1',
            user_id
        )
    
    async def update_balance(self, user_id, amount):
        await self.conn.execute(
            'UPDATE users SET balance = balance + $1 WHERE user_id = $2',
            amount, user_id
        )
    
    async def create_invoice(self, user_id, amount, address, crypto, invoice_id):
        await self.conn.execute(
            'INSERT INTO invoices (invoice_id, user_id, amount, address, crypto) VALUES ($1, $2, $3, $4, $5)',
            invoice_id, user_id, amount, address, crypto
        )
    
    async def get_invoice(self, invoice_id):
        return await self.conn.fetchrow(
            'SELECT * FROM invoices WHERE invoice_id = $1',
            invoice_id
        )
    
    async def update_invoice_status(self, invoice_id, status):
        await self.conn.execute(
            'UPDATE invoices SET status = $1, updated_at = NOW() WHERE invoice_id = $2',
            status, invoice_id
        )
    
    async def get_pending_invoices(self, limit=10):
        return await self.conn.fetch(
            'SELECT * FROM invoices WHERE status = $1 ORDER BY created_at ASC LIMIT $2',
            'pending', limit
        )
    
    async def get_product(self, product_id):
        return await self.conn.fetchrow(
            'SELECT * FROM products WHERE id = $1',
            product_id
        )
    
    async def get_purchase_history(self, user_id):
        return await self.conn.fetch(
            'SELECT * FROM purchases WHERE user_id = $1 ORDER BY created_at DESC',
            user_id
        )
    
    async def create_purchase(self, user_id, product_id, product_name, amount, district, delivery_type):
        await self.conn.execute(
            'INSERT INTO purchases (user_id, product_id, product_name, amount, district, delivery_type) VALUES ($1, $2, $3, $4, $5, $6)',
            user_id, product_id, product_name, amount, district, delivery_type
        )
    
    async def update_invoice_check_time(self, invoice_id):
        await self.conn.execute(
            'UPDATE invoices SET last_check_time = NOW() WHERE invoice_id = $1',
            invoice_id
        )
