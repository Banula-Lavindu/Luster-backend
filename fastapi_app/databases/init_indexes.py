from pymongo import MongoClient, ASCENDING
from pymongo.errors import DuplicateKeyError, OperationFailure
import logging

logger = logging.getLogger(__name__)

def setup_indexes(mongo_uri: str):
    """Setup all required database indexes"""
    try:
        client = MongoClient(mongo_uri)
        db = client.luster  # Your database name
        
        # First, drop the problematic index
        try:
            db.dealer_requests.drop_index("visitor_id_1_user_id_1")
            logger.info("Dropped existing visitor_id_user_id index")
        except OperationFailure:
            logger.info("No existing visitor_id_user_id index to drop")

        # Create new sparse index for dealer_requests
        try:
            db.dealer_requests.create_index(
                [("visitor_id", ASCENDING), ("user_id", ASCENDING)],
                sparse=True,
                name="visitor_id_user_id_sparse"
            )
            logger.info("Created new sparse index for dealer_requests")
        except DuplicateKeyError as e:
            logger.error(f"Error creating dealer_requests index: {e}")

        # Setup other necessary indexes
        try:
            # Chats collection indexes
            db.chats.create_index([("participants.id", ASCENDING)])
            db.chats.create_index([("chat_type", ASCENDING)])
            db.chats.create_index([("created_at", ASCENDING)])
            
            # Messages collection indexes
            db.messages.create_index([("chat_id", ASCENDING)])
            db.messages.create_index([("sender_id", ASCENDING)])
            db.messages.create_index([("timestamp", ASCENDING)])
            
            logger.info("Successfully created all other indexes")
        except Exception as e:
            logger.error(f"Error setting up other indexes: {e}")

        client.close()
        logger.info("Database indexes setup completed")
        
    except Exception as e:
        logger.error(f"Failed to setup database indexes: {e}")
        raise 