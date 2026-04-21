from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
ENV_FILE_PATH = ROOT_DIR / ".env"

class Settings(BaseSettings):
    PROJECT_NAME: str = "Reach"
    
    MONGODB_URI: str
    MONGO_DB_NAME: str
    
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 10080
    API_KEY: str

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE_PATH), 
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings() # type: ignore