import json
import time
import logging
import urllib.request
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.db.session import get_session
from app.models.user import User

logger = logging.getLogger(__name__)

reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/login/access-token"
)

_jwks_cache: dict | None = None
_jwks_cache_time: float = 0
_JWKS_TTL = 3600

def _get_jwks() -> dict:
    global _jwks_cache, _jwks_cache_time
    now = time.time()
    if _jwks_cache is not None and now - _jwks_cache_time < _JWKS_TTL:
        return _jwks_cache

    url = f"https://{settings.AUTH0_DOMAIN}/.well-known/jwks.json"
    with urllib.request.urlopen(url, timeout=10) as resp:
        _jwks_cache = json.loads(resp.read())
    _jwks_cache_time = now
    return _jwks_cache


def _find_rsa_key(token: str) -> dict:
    unverified_header = jwt.get_unverified_header(token)
    kid = unverified_header.get("kid")
    for key in _get_jwks().get("keys", []):
        if key.get("kid") == kid:
            return key
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Unable to find appropriate signing key",
    )


async def get_current_user(
    session: AsyncSession = Depends(get_session),
    token: str = Depends(reusable_oauth2),
) -> User:
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
    )

    try:
        rsa_key = _find_rsa_key(token)
        payload = jwt.decode(
            token,
            rsa_key,
            algorithms=["RS256"],
            audience=settings.AUTH0_AUDIENCE,
            issuer=f"https://{settings.AUTH0_DOMAIN}/",
        )
    except JWTError as e:
        logger.error("JWT validation failed: %s", e)
        raise credentials_exc

    # Try email from custom claims (set by Post Login Action)
    email: str | None = (
        payload.get(f"{settings.AUTH0_AUDIENCE}/email")
        or payload.get("email")
    )

    if email:
        query = select(User).where(User.email == email)
        result = await session.execute(query)
        user = result.scalars().first()
        if user:
            return user

    # Fallback: extract user ID from Auth0 sub claim (e.g. "auth0|3" → 3)
    sub: str | None = payload.get("sub")
    if sub and "|" in sub:
        try:
            user_id = int(sub.split("|", 1)[1])
            query = select(User).where(User.id == user_id)
            result = await session.execute(query)
            user = result.scalars().first()
            if user:
                return user
        except (ValueError, TypeError):
            pass

    logger.error("No user found for token claims: sub=%s, email=%s", sub, email)
    raise HTTPException(status_code=404, detail="User not found")


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    if not current_user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return current_user