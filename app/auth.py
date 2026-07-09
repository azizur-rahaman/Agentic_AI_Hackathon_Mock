import os
import uuid
import threading
from datetime import datetime, timedelta, timezone
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from . import models
from .database import get_db
from .errors import InvalidCredentialsException

SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production-co-work-secret-key-123456789")
ALGORITHM = "HS256"

# Token expirations
ACCESS_TOKEN_EXPIRE_SECONDS = 900
REFRESH_TOKEN_EXPIRE_DAYS = 7

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security_scheme = HTTPBearer()

# In-memory token management for blacklisting and rotation
blacklisted_tokens = set()
used_refresh_tokens = set()
token_lock = threading.Lock()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def create_token_pair(user: models.User) -> dict:
    now = datetime.now(timezone.utc)
    
    # Access token
    access_jti = str(uuid.uuid4())
    access_expire = now + timedelta(seconds=ACCESS_TOKEN_EXPIRE_SECONDS)
    access_payload = {
        "sub": str(user.id),
        "org": user.org_id,
        "role": user.role,
        "jti": access_jti,
        "iat": int(now.timestamp()),
        "exp": int(access_expire.timestamp()),
        "type": "access"
    }
    access_token = jwt.encode(access_payload, SECRET_KEY, algorithm=ALGORITHM)

    # Refresh token
    refresh_jti = str(uuid.uuid4())
    refresh_expire = now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    refresh_payload = {
        "sub": str(user.id),
        "org": user.org_id,
        "role": user.role,
        "jti": refresh_jti,
        "iat": int(now.timestamp()),
        "exp": int(refresh_expire.timestamp()),
        "type": "refresh"
    }
    refresh_token = jwt.encode(refresh_payload, SECRET_KEY, algorithm=ALGORITHM)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }


def blacklist_access_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        jti = payload.get("jti")
        if jti:
            with token_lock:
                blacklisted_tokens.add(jti)
    except JWTError:
        pass


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    db: Session = Depends(get_db)
) -> models.User:
    token = credentials.credentials
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        token_type = payload.get("type")
        if token_type != "access":
            raise credentials_exception
            
        jti = payload.get("jti")
        with token_lock:
            if jti in blacklisted_tokens:
                raise credentials_exception
                
        user_id: str = payload.get("sub")
        org_id: int = payload.get("org")
        if user_id is None or org_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(models.User).filter(models.User.id == int(user_id), models.User.org_id == org_id).first()
    if user is None:
        raise credentials_exception
    return user


def get_current_admin(
    current_user: models.User = Depends(get_current_user)
) -> models.User:
    if current_user.role != "admin":
        from .errors import ForbiddenException
        raise ForbiddenException("Only admins can perform this action")
    return current_user
