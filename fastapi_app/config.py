import os
from pathlib import Path
from pydantic_settings import BaseSettings
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file
env_path = Path(__file__).resolve().parent / ".env"
if env_path.exists():
    load_dotenv(env_path)
else:
    raise FileNotFoundError(f"Could not find .env file at {env_path}")

class Settings(BaseSettings):
    # API Settings
    BASE_URL: str = "http://localhost:8000"
    
    # JWT Settings
    SECRET_KEY: str = "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 43200  # 30 days
    
    # Firebase Settings
    FIREBASE_TYPE: str
    FIREBASE_PROJECT_ID: str
    FIREBASE_PRIVATE_KEY_ID: str
    FIREBASE_PRIVATE_KEY: str
    FIREBASE_CLIENT_EMAIL: str
    FIREBASE_CLIENT_ID: str
    FIREBASE_AUTH_URI: str
    FIREBASE_TOKEN_URI: str
    FIREBASE_AUTH_PROVIDER_CERT_URL: str
    FIREBASE_CLIENT_CERT_URL: str
    FIREBASE_AUTH_PROVIDER_X509_CERT_URL: str
    FIREBASE_CLIENT_X509_CERT_URL: str

    # Database Settings
    MYSQL_USER: str
    MYSQL_PASSWORD: str
    MYSQL_HOST: str
    MYSQL_PORT: str
    MYSQL_DATABASE: str
    MONGODB_URL: str

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "allow"

settings = Settings()

# Firebase Configuration
FIREBASE_CONFIG = {
    "type": settings.FIREBASE_TYPE,
    "project_id": settings.FIREBASE_PROJECT_ID,
    "private_key_id": settings.FIREBASE_PRIVATE_KEY_ID,
    "private_key": settings.FIREBASE_PRIVATE_KEY,
    "client_email": settings.FIREBASE_CLIENT_EMAIL,
    "client_id": settings.FIREBASE_CLIENT_ID,
    "auth_uri": settings.FIREBASE_AUTH_URI,
    "token_uri": settings.FIREBASE_TOKEN_URI,
    "auth_provider_x509_cert_url": settings.FIREBASE_AUTH_PROVIDER_CERT_URL,
    "client_x509_cert_url": settings.FIREBASE_CLIENT_CERT_URL
}

# Database URLs
MYSQL_DATABASE_URL = (
    f"mysql+pymysql://{settings.MYSQL_USER}:{settings.MYSQL_PASSWORD}@"
    f"{settings.MYSQL_HOST}:{settings.MYSQL_PORT}/{settings.MYSQL_DATABASE}"
)

MONGODB_URL = settings.MONGODB_URL
