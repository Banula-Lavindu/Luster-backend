import os
from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool
from motor.motor_asyncio import AsyncIOMotorClient
import logging
from dotenv import load_dotenv
from pathlib import Path
import time

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables from .env file
env_path = Path(__file__).resolve().parent / ".env"
if (env_path.exists()):
    load_dotenv(env_path)
else:
    raise FileNotFoundError(f"Could not find .env file at {env_path}")

# Validate required environment variables
required_vars = [
    'MYSQL_USER', 'MYSQL_PASSWORD', 'MYSQL_HOST', 
    'MYSQL_PORT', 'MYSQL_DATABASE', 'MONGODB_URL'
]

missing_vars = [var for var in required_vars if not os.getenv(var)]
if missing_vars:
    raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")

# --- MySQL Configuration ---
try:
    MYSQL_DATABASE_URL = (
        f"mysql+pymysql://{os.getenv('MYSQL_USER')}:{os.getenv('MYSQL_PASSWORD')}@"
        f"{os.getenv('MYSQL_HOST')}:{os.getenv('MYSQL_PORT')}/{os.getenv('MYSQL_DATABASE')}"
    )
    
    # Add engine configuration with optimized pool settings
    engine = create_engine(
        MYSQL_DATABASE_URL,
        poolclass=QueuePool,
        pool_size=5,  # Reduce from default
        max_overflow=10,
        pool_timeout=30,
        pool_recycle=1800,  # Recycle connections after 30 minutes
        pool_pre_ping=True  # Enable connection health checks
    )
    
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base = declarative_base()
    
    # Add connection cleanup event
    @event.listens_for(engine, "connect")
    def connect(dbapi_connection, connection_record):
        connection_record.info['pid'] = os.getpid()

    @event.listens_for(engine, "checkout")
    def checkout(dbapi_connection, connection_record, connection_proxy):
        pid = os.getpid()
        if connection_record.info['pid'] != pid:
            connection_record.connection = None
            raise exc.DisconnectionError(
                "Connection record belongs to pid %s, "
                "attempting to check out in pid %s" %
                (connection_record.info['pid'], pid)
            )
    
except Exception as e:
    logger.error(f"Failed to configure MySQL: {str(e)}")
    raise

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- MongoDB Configuration ---
MAX_RETRY_ATTEMPTS = 3
RETRY_DELAY = 1  # seconds

def create_mongo_client():
    mongo_url = os.getenv('MONGODB_URL')
    if not mongo_url:
        raise ValueError("MONGODB_URL environment variable is not set")
    
    for attempt in range(MAX_RETRY_ATTEMPTS):
        try:
            client = AsyncIOMotorClient(
                mongo_url,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=5000,
                maxPoolSize=10,
                minPoolSize=1,
                maxIdleTimeMS=30000,
                retryWrites=True,
                retryReads=True
            )
            # Test the connection
            client.admin.command('ping')
            logger.info("Successfully connected to MongoDB")
            return client
            
        except Exception as e:
            if attempt == MAX_RETRY_ATTEMPTS - 1:
                logger.error(f"Failed to connect to MongoDB after {MAX_RETRY_ATTEMPTS} attempts: {str(e)}")
                raise
            logger.warning(f"MongoDB connection attempt {attempt + 1} failed, retrying...")
            time.sleep(RETRY_DELAY)

try:
    mongo_client = create_mongo_client()
    mongo_db = mongo_client.get_database('luster')
except Exception as e:
    logger.error(f"Failed to initialize MongoDB connection: {str(e)}")
    raise

async def verify_mongo_connection():
    try:
        await mongo_db.command('ping')
        return True
    except Exception as e:
        logger.error(f"MongoDB connection verification failed: {str(e)}")
        return False

def get_mongo_collection(collection_name: str):
    return mongo_db[collection_name]


