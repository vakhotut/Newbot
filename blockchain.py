from hdwallet import HDWallet
from hdwallet.symbols import LTC
from hdwallet.utils import generate_mnemonic
import qrcode
import io
import asyncio
import aiohttp
import time
from typing import Dict, Optional

class BlockchainManager:
    def __init__(self, blockcypher_token, litecoin_api_key):
        self.blockcypher_token = blockcypher_token
        self.litecoin_api_key = litecoin_api_key
        self.mnemonic = generate_mnemonic(language="english", strength=128)
        self.hd_wallet = HDWallet(symbol=LTC)
        self.hd_wallet.from_mnemonic(mnemonic=self.mnemonic)
        self.last_request_time = 0
        self.request_interval = 0.4
        
    async def make_request(self, url):
        elapsed = time.time() - self.last_request_time
        if elapsed < self.request_interval:
            await asyncio.sleep(self.request_interval - elapsed)
        
        self.last_request_time = time.time()
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 429:
                        raise Exception("API limit exceeded. Please upgrade your plan or wait.")
                    if response.status != 200:
                        raise Exception(f"Blockcypher API error: {response.status}")
                    return await response.json()
        except Exception as e:
            print(f"Request error: {e}")
            return None
    
    def generate_address(self, user_id):
        self.hd_wallet.from_path(f"m/44'/2'/0'/0/{user_id}")
        address = self.hd_wallet.address()
        private_key = self.hd_wallet.private_key()
        self.hd_wallet.clean_derivation()
        return address, private_key
    
    async def create_invoice(self, user_id, amount_usd):
        address, private_key = self.generate_address(user_id)
        invoice_id = f"inv_{user_id}_{int(time.time())}"
        
        return {
            'address': address,
            'amount': amount_usd,
            'invoice_id': invoice_id,
            'crypto': 'LTC'
        }
    
    async def check_transaction(self, address, expected_amount):
        try:
            limits = await self.check_api_limits()
            if limits and limits['remaining'] < 10:
                print(f"Warning: Only {limits['remaining']} API calls remaining this hour")
            
            url = f"https://api.blockcypher.com/v1/ltc/main/addrs/{address}?token={self.blockcypher_token}"
            address_details = await self.make_request(url)
            
            if not address_details:
                return {
                    'confirmed': False,
                    'confirmations': 0,
                    'amount_received': 0
                }
            
            total_received = address_details.get('total_received', 0) / 10**8
            unconfirmed_balance = address_details.get('unconfirmed_balance', 0) / 10**8
            confirmations = address_details.get('txrefs', [{}])[0].get('confirmations', 0) if address_details.get('txrefs') else 0
            
            if total_received >= expected_amount or unconfirmed_balance >= expected_amount:
                return {
                    'confirmed': confirmations >= 4,
                    'confirmations': confirmations,
                    'amount_received': total_received
                }
            else:
                return {
                    'confirmed': False,
                    'confirmations': 0,
                    'amount_received': 0
                }
                
        except Exception as e:
            print(f"Error checking transaction: {e}")
            return {
                'confirmed': False,
                'confirmations': 0,
                'amount_received': 0
            }
    
    async def check_api_limits(self):
        try:
            url = f"https://api.blockcypher.com/v1/tokens/{self.blockcypher_token}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        return {
                            'limit': data['limits']['api/hour'],
                            'used': data['hits']['api/hour'],
                            'remaining': data['limits']['api/hour'] - data['hits']['api/hour']
                        }
        except Exception as e:
            print(f"Error checking API limits: {e}")
        return None
    
    async def generate_qr_code(self, address, amount):
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        
        payment_uri = f"litecoin:{address}?amount={amount}"
        qr.add_data(payment_uri)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='PNG')
        img_byte_arr.seek(0)
        
        return img_byte_arr
