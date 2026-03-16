from datetime import datetime, timedelta
from typing import Any, Union, Optional
from jose import jwt
import hashlib
import bcrypt
from app.core.config import settings

def create_access_token(subject: Union[str, Any], expires_delta: timedelta = None) -> str:
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode = {"exp": expire, "sub": str(subject)}
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def _sha256_hexdigest_bytes(password: str) -> bytes:
    # Pre-hash to prevent 72-byte limit crashes
    return hashlib.sha256(password.encode('utf-8')).hexdigest().encode('ascii')

def get_password_hash(password: str) -> str:
    prehashed = _sha256_hexdigest_bytes(password)
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(prehashed, salt)
    return hashed.decode('ascii')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        hp_bytes = hashed_password.encode('ascii')
        prehashed = _sha256_hexdigest_bytes(plain_password)
        return bcrypt.checkpw(prehashed, hp_bytes)
    except Exception:
        return False