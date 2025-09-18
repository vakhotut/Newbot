import hashlib
import hmac
import os
import binascii
from typing import Tuple, List, Optional
import base58
import ecdsa
from mnemonic import Mnemonic
import logging

# Настройка логирования
logger = logging.getLogger(__name__)

class HDWallet:
    def __init__(self, mnemonic: str = None, passphrase: str = ""):
        """
        Инициализация HD кошелька с мнемоникой и парольной фразой
        Если мнемоника не предоставлена, генерируется новая
        """
        if mnemonic is None:
            self.mnemonic = self.generate_mnemonic()
            logger.info("Generated new mnemonic phrase")
        else:
            if not self.validate_mnemonic(mnemonic):
                raise ValueError("Invalid mnemonic phrase")
            self.mnemonic = mnemonic
            logger.info("Initialized with existing mnemonic phrase")
        self.passphrase = passphrase
        self.seed = self.mnemonic_to_seed(self.mnemonic, self.passphrase)
        
    @staticmethod
    def generate_mnemonic(strength: int = 128) -> str:
        """Генерация мнемонической фразы (12 слов)"""
        mnemo = Mnemonic("english")
        return mnemo.generate(strength=strength)
    
    @staticmethod
    def validate_mnemonic(mnemonic: str) -> bool:
        """Проверка валидности мнемонической фразы"""
        mnemo = Mnemonic("english")
        return mnemo.check(mnemonic)
    
    @staticmethod
    def mnemonic_to_seed(mnemonic: str, passphrase: str = "") -> bytes:
        """Преобразование мнемоники в seed с использованием passphrase"""
        mnemo = Mnemonic("english")
        return mnemo.to_seed(mnemonic, passphrase=passphrase)
    
    @staticmethod
    def derive_master_key(seed: bytes) -> Tuple[bytes, bytes]:
        """Получение мастер-ключа из seed"""
        # HMAC-SHA512 с "Bitcoin seed" в качестве ключа
        I = hmac.new(b"Bitcoin seed", seed, hashlib.sha512).digest()
        return I[:32], I[32:]  # master private key, master chain code
    
    @staticmethod
    def CKDpriv(parent_priv: bytes, parent_chain: bytes, index: int) -> Tuple[bytes, bytes]:
        """Child Key Derivation (private) - BIP32"""
        if index >= 0x80000000:
            # Hardened derivation
            data = b'\x00' + parent_priv + index.to_bytes(4, 'big')
        else:
            # Normal derivation - нужен публичный ключ
            sk = ecdsa.SigningKey.from_string(parent_priv, curve=ecdsa.SECP256k1)
            vk = sk.get_verifying_key()
            parent_pub = b'\x02' + vk.to_string()[:32] if vk.to_string()[63] % 2 == 0 else b'\x03' + vk.to_string()[:32]
            data = parent_pub + index.to_bytes(4, 'big')
        
        I = hmac.new(parent_chain, data, hashlib.sha512).digest()
        I_left = int.from_bytes(I[:32], 'big')
        parent_priv_int = int.from_bytes(parent_priv, 'big')
        
        # Модульная арифметика для приватного ключа
        n = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
        child_priv_int = (I_left + parent_priv_int) % n
        child_priv = child_priv_int.to_bytes(32, 'big')
        child_chain = I[32:]
        
        return child_priv, child_chain
    
    def derive_path(self, path: str) -> Tuple[bytes, bytes]:
        """Деривация ключа по BIP32/BIP44 пути"""
        # Parse path
        parts = path.split('/')
        if parts[0] != 'm':
            raise ValueError("Path must start with 'm'")
        
        # Начинаем с мастер-ключа
        priv_key, chain_code = self.derive_master_key(self.seed)
        
        for part in parts[1:]:
            if part.endswith("'"):
                # Hardened derivation
                index = int(part[:-1]) + 0x80000000
            else:
                # Normal derivation
                index = int(part)
            
            priv_key, chain_code = self.CKDpriv(priv_key, chain_code, index)
        
        return priv_key, chain_code
    
    @staticmethod
    def private_key_to_public_key(private_key: bytes, compressed: bool = True) -> bytes:
        """Получение публичного ключа из приватного"""
        sk = ecdsa.SigningKey.from_string(private_key, curve=ecdsa.SECP256k1)
        vk = sk.get_verifying_key()
        
        if compressed:
            # Сжатый формат публичного ключа
            x = vk.to_string()[:32]
            y = vk.to_string()[32:]
            return (b'\x02' if y[-1] % 2 == 0 else b'\x03') + x
        else:
            # Несжатый формат
            return b'\x04' + vk.to_string()
    
    @staticmethod
    def public_key_to_address(public_key: bytes, version_byte: int = 0x30) -> str:
        """Конвертация публичного ключа в Litecoin-адрес (BIP84)"""
        # Hash public key (SHA256 + RIPEMD160)
        sha256 = hashlib.sha256(public_key).digest()
        ripemd160 = hashlib.new('ripemd160', sha256).digest()
        
        # Добавляем версионный байт для Litecoin mainnet (0x30)
        version_payload = version_byte.to_bytes(1, 'big') + ripemd160
        
        # Вычисляем checksum
        checksum = hashlib.sha256(hashlib.sha256(version_payload).digest()).digest()[:4]
        
        # Формируем полный payload
        full_payload = version_payload + checksum
        
        # Кодируем в base58
        return base58.b58encode(full_payload).decode('utf-8')
    
    def get_address(self, path: str = "m/84'/2'/0'/0/0") -> str:
        """Получение адреса по BIP84 пути для Litecoin"""
        priv_key, _ = self.derive_path(path)
        public_key = self.private_key_to_public_key(priv_key, compressed=True)
        return self.public_key_to_address(public_key)
    
    def get_private_key_wif(self, path: str = "m/84'/2'/0'/0/0") -> str:
        """Получение приватного ключа в WIF формате для Litecoin"""
        priv_key, _ = self.derive_path(path)
        
        # Добавляем версионный байт для Litecoin mainnet (0xB0)
        version_priv = b'\xB0' + priv_key
        
        # Добавляем флаг сжатия
        version_priv += b'\x01'  # Compressed
        
        # Вычисляем checksum
        checksum = hashlib.sha256(hashlib.sha256(version_priv).digest()).digest()[:4]
        
        # Формируем полный payload
        full_payload = version_priv + checksum
        
        # Кодируем в base58
        return base58.b58encode(full_payload).decode('utf-8')
    
    def get_xpub(self, path: str = "m/84'/2'/0'") -> str:
        """Получение расширенного публичного ключа (xpub) для заданного пути"""
        priv_key, chain_code = self.derive_path(path)
        public_key = self.private_key_to_public_key(priv_key, compressed=True)
        
        # Версия для Litecoin mainnet (0x0488B21E)
        version = 0x0488B21E
        
        # Глубина (depth)
        depth = len(path.split('/')) - 1
        
        # Отпечаток родительского ключа (parent fingerprint)
        parent_priv, _ = self.derive_master_key(self.seed)
        parent_public_key = self.private_key_to_public_key(parent_priv, compressed=True)
        parent_sha256 = hashlib.sha256(parent_public_key).digest()
        parent_ripemd160 = hashlib.new('ripemd160', parent_sha256).digest()
        fingerprint = parent_ripemd160[:4]
        
        # Номер дочернего ключа (child number)
        child_number = 0x80000000 if path.endswith("'") else 0
        
        # Формируем ключевые данные
        key_data = b'\x00' + public_key
        
        # Формируем полные данные для кодирования
        data = (
            version.to_bytes(4, 'big') +
            depth.to_bytes(1, 'big') +
            fingerprint +
            child_number.to_bytes(4, 'big') +
            chain_code +
            key_data
        )
        
        # Вычисляем checksum
        checksum = hashlib.sha256(hashlib.sha256(data).digest()).digest()[:4]
        
        # Кодируем в base58
        return base58.b58encode(data + checksum).decode('utf-8')

# Глобальный экземпляр HDWallet
# Мнемоника должна храниться в безопасном месте (env переменные/конфиг)
try:
    from config import config
    hd_wallet = HDWallet(config.BOT_MNEMONIC if hasattr(config, 'BOT_MNEMONIC') else None)
    logger.info("HDWallet initialized with config mnemonic")
except Exception as e:
    # Fallback для случаев, когда конфиг не доступен
    hd_wallet = HDWallet()
    logger.warning(f"Config not available, generated new mnemonic: {e}")

# Функции для использования в других модулях
def generate_mnemonic() -> str:
    return HDWallet.generate_mnemonic()

def get_address_from_path(path: str = "m/84'/2'/0'/0/0") -> str:
    return hd_wallet.get_address(path)

def create_ltc_address_for_user(user_id: int) -> str:
    """Создание LTC-адреса для конкретного пользователя"""
    try:
        # Используем ID пользователя для генерации уникального пути
        # Формат: m/84'/2'/0'/0/{user_id % 1000000}
        # Ограничиваем user_id модулем 1000000 чтобы избежать слишком больших чисел
        derivation_path = f"m/84'/2'/0'/0/{user_id % 1000000}"
        address = get_address_from_path(derivation_path)
        logger.info(f"Generated LTC address for user {user_id}: {address}")
        return address
    except Exception as e:
        logger.error(f"Error generating LTC address for user {user_id}: {e}")
        return None

def get_private_key_from_path(path: str = "m/84'/2'/0'/0/0") -> str:
    return hd_wallet.get_private_key_wif(path)

def get_xpub_from_path(path: str = "m/84'/2'/0'") -> str:
    return hd_wallet.get_xpub(path)
