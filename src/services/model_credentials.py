"""Encryption and decryption are kept server-side and never feed response DTOs."""
import base64
import hashlib

from cryptography.fernet import Fernet

from src.config import settings


def _fernet() -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.model_credential_encryption_secret.encode()).digest())
    return Fernet(key)


def encrypt_credential(credential: str) -> str:
    return _fernet().encrypt(credential.encode()).decode()


def decrypt_credential(ciphertext: str) -> str:
    return _fernet().decrypt(ciphertext.encode()).decode()
