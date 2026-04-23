from pydantic import BaseModel, Field
from typing import Optional, List
import time

class SecureCloudMessage(BaseModel):
    message_id: str
    sender_id: str
    target_id: str
    encrypted_payload: dict[str, str]
    digital_signature: str
    timestamp: int = Field(default_factory=lambda: int(time.time() * 1000))
    hops_taken: int = 0
    is_delivered_to_target: bool = False

class MessageResponse(BaseModel):
    message_id: str
    sender_id: str
    target_id: str
    encrypted_payload: dict[str, str]
    digital_signature: str
    timestamp: int
    
class MediaMetadata(BaseModel):
    file_id: str
    owner_id: str
    file_name: str
    content_type: str
    file_size: int
    thumbnail_b64: Optional[str] = None
    
class GroupCreateRequest(BaseModel):
    group_name: str
    member_ids: List[str]  # The UUIDs of the users being added to the group
    group_avatar_url: Optional[str] = None # Support for GC avatars!
    
class GroupResponse(BaseModel):
    group_id: str
    group_name: str
    group_avatar_url: Optional[str] = None
    members: List[str]     # List of user UUIDs in this GC
    created_by: str        # The UUID of the admin who made the GC
    created_at: float
    
class BackupMessageDto(BaseModel):
    message_id: str
    thread_id: str
    sender_id: str
    encrypted_data: str
    timestamp: int