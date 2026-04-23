from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
import time

class UserCreate(BaseModel):
    user_id: Optional[str] = None # <-- Add this
    username: str
    password: str
    public_key: str
    private_key: str

class UserLogin(BaseModel):
    username: str
    password: str

class Device(BaseModel):
    device_id: str
    public_key: str
    device_name: str
    is_active: bool = True

class UserInDB(BaseModel):
    user_id: str
    username: str
    hashed_password: str
    devices: List[Device] = []
    public_key: str
    private_key: str  # Save it in the database
    created_at: datetime = Field(default_factory=datetime.utcnow)
    is_online: bool = False
    last_seen: int = Field(default_factory=lambda: int(time.time() * 1000))

class UserResponse(BaseModel):
    user_id: str
    username: str
    public_key: str
    is_online: bool
    
class FCMTokenRequest(BaseModel):
    fcm_token: str