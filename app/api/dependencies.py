from fastapi import Depends, HTTPException, Security
from fastapi.security.api_key import APIKeyHeader
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from app.core.config import settings


api_key_header = APIKeyHeader(name="X-API-KEY")
security_bearer = HTTPBearer()


async def verify_api_key(api_key: str = Security(api_key_header)):
    if api_key != settings.API_KEY:
        raise HTTPException(status_code=403, detail="Invalid API Key. Access Denied")
    return api_key

async def verify_jwt(credentials: HTTPAuthorizationCredentials = Depends(security_bearer)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub", "")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token payload")
        return user_id
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")