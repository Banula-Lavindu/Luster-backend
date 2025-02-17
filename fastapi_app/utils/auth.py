from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from .jwt import decode_access_token

# OAuth2 scheme for extracting the token from Authorization header
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

async def get_current_user(token: str = Depends(oauth2_scheme)):
    """Get current user from token"""
    try:
        user_id = decode_access_token(token)
        return {"user_id": user_id}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) 