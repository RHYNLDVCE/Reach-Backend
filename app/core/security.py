from datetime import datetime, timedelta, timezone
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jwt.exceptions import InvalidTokenError
import jwt
import hashlib
from app.core.config import settings

reusable_oauth2 = HTTPBearer()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password: str) -> str:
    sha256_hash = hashlib.sha256(password.encode('utf-8')).hexdigest()
    return pwd_context.hash(sha256_hash)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    sha256_hash = hashlib.sha256(plain_password.encode('utf-8')).hexdigest()
    return pwd_context.verify(sha256_hash, hashed_password)

def create_access_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {"exp": expire, "sub": str(subject)}
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

async def get_current_user(token: HTTPAuthorizationCredentials = Depends(reusable_oauth2)) -> str:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token.credentials, 
            settings.SECRET_KEY, 
            algorithms=[settings.ALGORITHM]
        )
        user_id: str = payload.get("sub") #type: ignore
        if user_id is None:
            raise credentials_exception
        return user_id
        
    except (InvalidTokenError, jwt.ExpiredSignatureError):
        raise credentials_exception