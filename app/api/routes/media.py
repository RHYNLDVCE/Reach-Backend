from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
from motor.motor_asyncio import AsyncIOMotorGridFSBucket
from bson import ObjectId
import uuid
from typing import Any, cast
from app.core.database import db_instance
from app.core.security import get_current_user
from app.api.dependencies import verify_api_key

router = APIRouter()

MAX_FILE_SIZE = 50 * 1024 * 1024 # 50 Megabytes

@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    current_user_id: str = Depends(get_current_user),
    api_key: str = Depends(verify_api_key)
):
    fs = AsyncIOMotorGridFSBucket(cast(Any, db_instance))
    
    original_name = file.filename if file.filename else "unnamed_file"
    file_ext = original_name.split(".")[-1] if "." in original_name else "bin"
    unique_name = f"{uuid.uuid4()}.{file_ext}"

    try:
        grid_in = fs.open_upload_stream(
            unique_name,
            metadata={
                "owner_id": current_user_id, 
                "content_type": file.content_type or "application/octet-stream"
            }
        )
        
        # --- SECURITY FIX: CHUNKED READING & SIZE LIMIT ---
        total_size = 0
        chunk_size = 1024 * 1024 # Read 1 Megabyte at a time
        
        while chunk := await file.read(chunk_size):
            total_size += len(chunk)
            if total_size > MAX_FILE_SIZE:
                await grid_in.abort() # Delete the partial file from MongoDB
                raise HTTPException(status_code=413, detail="File too large. Maximum size is 50MB.")
                
            await grid_in.write(chunk)
            
        await grid_in.close()
        # --------------------------------------------------

        return {
            "file_id": str(grid_in._id),
            "file_name": original_name,
            "url": f"/api/media/download/{grid_in._id}"
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"Upload error: {e}")
        raise HTTPException(status_code=500, detail="Could not save file")
    
    
@router.get("/download/{file_id}")
async def download_file(
    file_id: str,
    current_user_id: str = Depends(get_current_user),
    api_key: str = Depends(verify_api_key)
):
    fs = AsyncIOMotorGridFSBucket(cast(Any, db_instance))
    
    try:
        obj_id = ObjectId(file_id)
        grid_out = await fs.open_download_stream(obj_id)
        
        # --- SECURITY FIX: AUTHORIZATION CHECK ---
        metadata = grid_out.metadata or {}
        owner_id = metadata.get("owner_id")
        
        # Prevent IDOR (Insecure Direct Object Reference)
        # If the file belongs to someone else, block the download.
        if owner_id and owner_id != current_user_id:
            raise HTTPException(status_code=403, detail="Not authorized to access this media")
        # -----------------------------------------

        media_type = metadata.get("content_type", "application/octet-stream")

        return StreamingResponse(grid_out, media_type=media_type)
        
    except HTTPException:
        # Re-raise our 403 Forbidden error so it doesn't get masked as a 404
        raise
    except Exception:
        raise HTTPException(status_code=404, detail="File not found")