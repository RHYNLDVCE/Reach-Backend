from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.core.database import connect_mongo, close_mongo_connection, db_instance
from app.core.config import settings
from app.api.routes import auth, messages, media, groups
import firebase_admin
from firebase_admin import credentials
import logging

logging.basicConfig(level=logging.INFO)

try:
    cred = credentials.Certificate("firebase-credentials.json")
    firebase_admin.initialize_app(cred)
    print("Firebase Admin SDK initialized successfully!")
except Exception as e:
    print(f"Failed to initialize Firebase: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_mongo()
    if db_instance.users is not None:
        await db_instance.users.update_many({}, {"$set": {"is_online": False}})
    yield
    await close_mongo_connection()

app = FastAPI(
    title=settings.PROJECT_NAME,
    lifespan=lifespan
)

app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(messages.router, prefix="/api/mesh", tags=["Mesh Networking"])
app.include_router(media.router, prefix="/api/media", tags=["Media Bridge"])
app.include_router(groups.router, prefix="/api/groups", tags=["Groups"])

@app.get("/")
async def root():
    return {"message": "Reach - An Offline first messaging app"}