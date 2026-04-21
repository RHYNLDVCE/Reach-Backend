from fastapi import APIRouter, Depends, HTTPException, status
from app.models.message import GroupCreateRequest, GroupResponse # Update import path if you put these in models/user.py
from app.core.database import db_instance
from app.api.dependencies import verify_api_key
from app.core.security import get_current_user
import uuid
import time

router = APIRouter()

@router.post("/create", response_model=GroupResponse, status_code=status.HTTP_201_CREATED)
async def create_group(
    request: GroupCreateRequest,
    current_user_id: str = Depends(get_current_user),
    api_key: str = Depends(verify_api_key)
):
    # 1. Ensure the creator is always included in the members list
    members = set(request.member_ids)
    members.add(current_user_id)

    # 2. Build the group document
    new_group = {
        "group_id": str(uuid.uuid4()),
        "group_name": request.group_name,
        "group_avatar_url": request.group_avatar_url,
        "members": list(members),
        "created_by": current_user_id,
        "created_at": int(time.time() * 1000)
    }

    # 3. Save to MongoDB
    await db_instance.groups.insert_one(new_group) # type: ignore

    return GroupResponse(**new_group)