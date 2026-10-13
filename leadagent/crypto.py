from cryptography.fernet import Fernet

from leadagent.settings import get_settings


def encrypt(plain: str) -> str:
    return Fernet(get_settings().fernet_key).encrypt(plain.encode()).decode()


def decrypt(token: str) -> str:
    return Fernet(get_settings().fernet_key).decrypt(token.encode()).decode()
