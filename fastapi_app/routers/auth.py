from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.orm import Session
from fastapi_app.database import get_db
from fastapi_app.models.models import User
from fastapi_app.utils.jwt import create_access_token, decode_access_token
from fastapi_app.config import settings  # Import settings
from fastapi_app.utils.auth import oauth2_scheme, get_current_user
from pydantic import BaseModel
from passlib.context import CryptContext
import firebase_admin # type: ignore
from firebase_admin import auth as firebase_auth # type: ignore
from firebase_admin import credentials # type: ignore
from ..config import FIREBASE_CONFIG
from datetime import datetime
from jose import JWTError, jwt
from typing import Optional

# Use settings instead of direct imports
SECRET_KEY = settings.SECRET_KEY
ALGORITHM = settings.ALGORITHM

# Initialize Firebase Admin SDK
try:
    cred = credentials.Certificate(FIREBASE_CONFIG)
    firebase_admin.initialize_app(cred)
except Exception:
    raise RuntimeError("Failed to initialize Firebase Admin SDK")

router = APIRouter(prefix="/auth", tags=["auth"])

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class UserCreate(BaseModel):
    first_name: str
    last_name: str
    ID: str
    phone_number: str
    password: str
    email: str

class LoginRequest(BaseModel):
    identifier: str  # Can be email, phone number, or ID
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class FirebaseLoginRequest(BaseModel):
    firebase_id_token: str

class ResetPasswordRequest(BaseModel):
    firebase_id_token: str
    new_password: str

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(user: UserCreate, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(
        (User.email == user.email) |
        (User.phone_number == user.phone_number) |
        (User.ID == user.ID)
    ).first()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email, phone, or ID already exists"
        )

    new_user = User(
        first_name=user.first_name,
        last_name=user.last_name,
        ID=user.ID,
        phone_number=user.phone_number,
        password_hash=get_password_hash(user.password),
        email=user.email,
        is_active=True,
        is_verified=True
        
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # Generate and save the QR code for the new user
    new_user.generate_qr()
    db.commit()  # Commit again to save the QR code file path

    # Create an access token for the new user
    access_token = create_access_token(data={"sub": str(new_user.user_id)})  # Use new_user.user_id

    # Return the success message and the access token
    return {
        "message": f"Welcome , {user.first_name}! You Registerd Sucessflly",  # Add a comma here
        "access_token": access_token,
        "token_type": "bearer"
    }

    


@router.post("/login", response_model=Token)
async def password_login(request: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(
        (User.email == request.identifier) |
        (User.phone_number == request.identifier) |
        (User.ID == request.identifier)
    ).first()

    if not user or not verify_password(request.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # Update the last_login field to the current timestamp
    user.last_login = datetime.utcnow()
    db.commit()  # Commit the change to the database

    return {
        "message": f"Welcome back, {user.first_name}!",
        "access_token": create_access_token(data={"sub": user.user_id}),  # Store user_id as 'sub'
        "token_type": "bearer"
    }



@router.post("/firebase-login", response_model=Token)
async def firebase_login(request: FirebaseLoginRequest, db: Session = Depends(get_db)):
    try:
        decoded_token = firebase_auth.verify_id_token(request.firebase_id_token)
        firebase_uid = decoded_token.get("uid")
        phone_number = decoded_token.get("phone_number")

        if not firebase_uid or not phone_number:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid Firebase ID token: Missing UID or phone number"
            )

        user = db.query(User).filter(User.phone_number == phone_number).first()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Update the last_login field to the current timestamp
        user.last_login = datetime.utcnow()
        db.commit()  # Commit the change to the database

        return {
            "message": f"Welcome back, {user.first_name}!",
            "access_token": create_access_token(data={"sub": user.user_id}),  # Use 'sub' for compatibility
            "token_type": "bearer"
        }

    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@router.post("/reset-password")
async def reset_password(request: ResetPasswordRequest, db: Session = Depends(get_db)):
    try:
        decoded_token = firebase_auth.verify_id_token(request.firebase_id_token)
        phone_number = decoded_token.get("phone_number")

        if not phone_number:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid Firebase ID token: Missing phone number"
            )

        user = db.query(User).filter(User.phone_number == phone_number).first()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )

        user.password_hash = get_password_hash(request.new_password)
        db.commit()

        return {"message": f"Welcome back, {user.first_name}!. Your password has been reset successfully.",
                "access_token": create_access_token(data={"sub": user.user_id}),  # Use 'sub' for compatibility
                "token_type": "bearer"}

    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@router.get("/users/me")
async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """
    Get the currently authenticated user's details.
    """
    user_id = decode_access_token(token)

    user = db.query(User).filter(User.user_id == user_id).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return user

# Add this new function for WebSocket authentication
async def get_current_user_ws(token: str) -> Optional[User]:
    """
    Authenticate WebSocket connections using JWT token
    Returns None if authentication fails instead of raising an exception
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            return None
            
        # Get database session
        db = next(get_db())
        
        # Get user from database
        user = db.query(User).filter(User.user_id == int(user_id)).first()
        if user is None:
            return None
            
        return user
        
    except (JWTError, Exception):
        return None
    finally:
        # Make sure to close the database session
        if 'db' in locals():
            db.close()