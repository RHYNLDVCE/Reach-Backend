from fastapi import FastAPI
from contextlib import asynccontextmanager
from app.core.database import connect_mongo, close_mongo_connection, db_instance
from app.core.config import settings
from app.api.routes import auth, messages, media, groups
import firebase_admin
from firebase_admin import credentials
import logging
import os
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ReachAPI")

def initialize_firebase():
    if not firebase_admin._apps:
        try:
            # 1. List of potential paths where Vercel mounts "Secret Files"
            # Vercel usually places them in /etc/secrets/ or the root.
            potential_paths = [
                "/etc/secrets/firebase-credentials.json",
                os.path.join(os.getcwd(), "firebase-credentials.json"),
                os.path.join(os.path.dirname(os.path.abspath(__file__)), "firebase-credentials.json")
            ]

            cert_path = None
            for path in potential_paths:
                if os.path.exists(path):
                    cert_path = path
                    break

            if cert_path:
                cred = credentials.Certificate(cert_path)
                firebase_admin.initialize_app(cred)
                logger.info(f"Firebase initialized via Secret File at: {cert_path}")
                return

            # 2. Fallback: Check for the Environment Variable (as a backup)
            firebase_json_env = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
            if firebase_json_env:
                cert_dict = json.loads(firebase_json_env)
                cred = credentials.Certificate(cert_dict)
                firebase_admin.initialize_app(cred)
                logger.info("Firebase initialized via Environment Variable!")
                return

            logger.warning("No Firebase credentials found in Secret Files or Environment Variables.")

        except Exception as e:
            logger.error(f"Failed to initialize Firebase: {e}")

initialize_firebase()

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