from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings
from typing import Optional, Any
import logging

logger = logging.getLogger(__name__)

class Database:
    client: Optional[AsyncIOMotorClient] = None
    db: Optional[Any] = None
    
    users: Optional[Any] = None
    messages: Optional[Any] = None
    groups: Optional[Any] = None
    
db_instance = Database()

async def connect_mongo():
    logger.info("Connecting to MongoDB")
    try:
        db_instance.client = AsyncIOMotorClient(settings.MONGODB_URI)
        db_instance.db = db_instance.client[settings.MONGO_DB_NAME]
        
        db_instance.users = db_instance.db["users"]
        db_instance.messages = db_instance.db["messages"]
        db_instance.groups = db_instance.db["groups"]
        logger.info("Successfully connected to mongoDb")
    except Exception as e:
        logger.error(f"Could not connect to mongodb - Error: {e}")
        raise e
    
async def close_mongo_connection():
    if db_instance.client:
        logger.info("Closing MongoDB connection...")
        db_instance.client.close()
        logger.info("MongoDB connection closed.")