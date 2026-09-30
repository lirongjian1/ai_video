import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings
from app.models.workflow import AiModelConfig


def _fernet() -> Fernet:
    digest = hashlib.sha256(settings.secret_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("模型 Key 解密失败，请重新保存该模型配置") from exc


def model_api_key(config: AiModelConfig) -> str | None:
    if config.api_key_encrypted:
        return decrypt_secret(config.api_key_encrypted)
    if config.api_key_env:
        return os.getenv(config.api_key_env)
    return None
