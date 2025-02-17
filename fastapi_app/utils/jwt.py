from jose import jwt, JWTError
from datetime import datetime, timedelta
from fastapi import HTTPException, status
from fastapi_app.config import settings
import logging

def create_access_token(data: dict):
    """Create a JWT access token"""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    to_encode['sub'] = str(data['sub'])
    
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

def decode_access_token(token: str) -> str:
    """Decode and validate JWT token"""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = str(payload.get("sub"))
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        return user_id
    except JWTError as e:
        logging.error(f"Error decoding token: {e}")
        raise HTTPException(status_code=401, detail="Could not validate credentials")




