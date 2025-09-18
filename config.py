import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
BLOCKCYPHER_TOKEN = os.getenv('BLOCKCYPHER_TOKEN')
LITECOIN_API_KEY = os.getenv('LITECOIN_API_KEY')
ADMIN_USER_ID = os.getenv('ADMIN_USER_ID')

DB_HOST = os.getenv('DB_HOST')
DB_PORT = os.getenv('DB_PORT')
DB_NAME = os.getenv('DB_NAME')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')

MAX_REQUESTS_PER_HOUR = 200
REQUEST_INTERVAL = 0.4
