from fastapi import APIRouter, Depends, HTTPException, status, WebSocket, WebSocketDisconnect
from typing import List
from app.models.message import SecureCloudMessage, BackupMessageDto
from app.core.database import db_instance
from app.api.dependencies import verify_api_key
from app.core.security import get_current_user
from app.core.config import settings
from app.api.ws_manager import manager
from pymongo import UpdateOne
from firebase_admin import messaging
import jwt
import logging
import time

logger = logging.getLogger(__name__)
router = APIRouter()

async def send_offline_notification(target_id: str, sender_username: str, thread_id: str, encrypted_data: str):
    target_user = await db_instance.users.find_one({"user_id": target_id}) # type: ignore
    
    if target_user and target_user.get("fcm_token"):
        try:
            push_msg = messaging.Message(
                data={
                    "type": "NEW_MESSAGE",
                    "title": sender_username,
                    "body": encrypted_data,
                    "thread_id": str(thread_id)
                }, 
                token=target_user["fcm_token"]
            )
            response = messaging.send(push_msg)
            print(f"Push sent to {target_id}! Response: {response}")
        except Exception as e:
            print(f"Failed to send push notification: {e}")

@router.post("/sync-mesh-queue", status_code=status.HTTP_201_CREATED)
async def sync_mesh_messages(
    messages: List[SecureCloudMessage],
    api_key: str = Depends(verify_api_key),
    current_user: str = Depends(get_current_user)
):
    if not messages:
        return {"message": "Empty queue", "synced_count": 0}
    operations = [UpdateOne({"message_id": msg.message_id}, {"$set": msg.model_dump()}, upsert=True) for msg in messages] #type: ignore

    try:
        await db_instance.messages.bulk_write(operations) # type: ignore
        return {"message": "Sync complete", "count": len(messages)}
    except Exception as e:
        raise HTTPException(status_code=500, detail="Bulk sync failed")
    
    
@router.websocket("/ws/{token}")
async def websocket_endpoint(websocket: WebSocket, token: str):
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            raise ValueError("Invalid token payload")
    except Exception as e:
        print(f"WebSocket Auth Error: {e}")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
        
    await manager.connect(user_id, websocket) #type: ignore
    
    user_doc = await db_instance.users.find_one({"user_id": user_id}) # type: ignore
    current_username = user_doc.get("username", "Unknown") if user_doc else "Unknown"
    
    try:
        while True:
            data = await websocket.receive_json()
            
            if data.get("type") == "ACK":
                msg_id = data.get("message_id")
                await db_instance.messages.update_one({"message_id": msg_id},{"$set": {"is_delivered_to_target": True}}) # type: ignore
                original_sender = data.get("original_sender_id")
                await manager.send_personal_message(data, original_sender)
                continue
            
            claimed_sender = data.get("sender_id", user_id)
            claimed_username = data.get("sender_username", current_username)
            
            data["sender_id"] = claimed_sender
            data["sender_username"] = claimed_username
            
            if "is_delivered_to_target" not in data:
                data["is_delivered_to_target"] = False
                
            if "timestamp" not in data:
                data["timestamp"] = int(time.time() * 1000)

            # --- Save Message to Database ---
            target_id = data.get("target_id")
            await db_instance.messages.update_one({"message_id": data.get("message_id")},{"$set": data},upsert=True) # type: ignore

            # Send a confirmation echo back to the uploading node
            if user_id in manager.active_connections:
                await manager.send_personal_message(data, user_id)

            # --- 4. Route to Target (1-on-1 OR Group Chat) ---
            # FIX: Check if the target is a group first!
            group = await db_instance.groups.find_one({"group_id": target_id}) # type: ignore
            
            if group:
                # It's a Group Chat! Fan-out to all members.
                for member_id in group.get("members", []):
                    if member_id != claimed_sender:
                        if member_id in manager.active_connections:
                            # User is online, send via WebSocket
                            await manager.send_personal_message(data, member_id)
                        else:
                            # User is offline, send via Firebase Push
                            await send_offline_notification(
                                target_id=member_id, 
                                sender_username=claimed_username, 
                                thread_id=target_id, 
                                encrypted_data=data.get("encrypted_payload", {}).get("data", "")
                            )
            else:
                # It's a 1-on-1 Direct Message
                if target_id in manager.active_connections:
                    await manager.send_personal_message(data, target_id)
                elif target_id != claimed_sender:
                    await send_offline_notification(
                        target_id=target_id, 
                        sender_username=claimed_username, 
                        thread_id=claimed_sender, 
                        encrypted_data=data.get("encrypted_payload", {}).get("data", "")
                    )

    except Exception as e:
        print(f"WebSocket Disconnected for user {user_id}: {e}")
    finally:
        await manager.disconnect(user_id) #type: ignore
        
@router.post("/backup", status_code=status.HTTP_200_OK)
async def backup_messages_batch(
    payloads: List[BackupMessageDto],
    current_user_id: str = Depends(get_current_user), 
    api_key: str = Depends(verify_api_key)
):
    if not payloads:
        return {"status": "success", "backed_up_count": 0}

    try:
        bulk_operations = []
        for dto in payloads:
            doc = dto.model_dump()
            doc["_id"] = doc.pop("message_id") 

            bulk_operations.append(
                UpdateOne(
                    {"_id": doc["_id"]},
                    {"$set": doc},
                    upsert=True
                )
            )

        result = await db_instance.messages.bulk_write(bulk_operations) # type: ignore
        
        logger.info(f"Backup batch processed for user {current_user_id}: {result.upserted_count} new, {result.modified_count} updated.")
        
        return {
            "status": "success", 
            "upserted_count": result.upserted_count,
            "modified_count": result.modified_count
        }
        
    except Exception as e:
        logger.error(f"Failed to process MongoDB backup batch: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process backup batch"
        )


@router.delete("/backup/{thread_id}", status_code=status.HTTP_200_OK)
async def delete_thread_backups(
    thread_id: str,
    current_user_id: str = Depends(get_current_user), 
    api_key: str = Depends(verify_api_key)
):
    try:
        result = await db_instance.messages.delete_many({ # type: ignore
            "thread_id": thread_id,
            "sender_id": current_user_id 
        })
        
        logger.info(f"Purged {result.deleted_count} messages for thread {thread_id}")
        
        return {"status": "success", "purged_count": result.deleted_count}
        
    except Exception as e:
        logger.error(f"Failed to purge thread backups from MongoDB: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to purge thread backups"
        )
        
        
@router.get("/sync-inbox", status_code=status.HTTP_200_OK)
async def sync_missed_messages(
    current_user_id: str = Depends(get_current_user),
    api_key: str = Depends(verify_api_key)
):
    try:
        user_groups = await db_instance.groups.find({"members": current_user_id}).to_list(length=None) # type: ignore
        group_ids = [g["group_id"] for g in user_groups]

        cursor = db_instance.messages.find({ # type: ignore
            "$or": [
                {"target_id": current_user_id},
                {"target_id": {"$in": group_ids}}
            ],
            "is_delivered_to_target": {"$ne": True}, 
            "sender_id": {"$ne": current_user_id} 
        })
        missed_messages = await cursor.to_list(length=None)

        if not missed_messages:
            return {"status": "success", "messages": []}

        msg_ids = [m["message_id"] for m in missed_messages]
        await db_instance.messages.update_many( # type: ignore
            {"message_id": {"$in": msg_ids}},
            {"$set": {"is_delivered_to_target": True}}
        )

        for m in missed_messages:
            if "_id" in m:
                del m["_id"]

        logger.info(f"User {current_user_id} pulled {len(missed_messages)} missed messages.")
        return {"status": "success", "messages": missed_messages}

    except Exception as e:
        logger.error(f"Inbox sync failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to sync inbox")
    
    
@router.get("/restore-history", status_code=status.HTTP_200_OK)
async def restore_message_history(
    current_user_id: str = Depends(get_current_user),
    api_key: str = Depends(verify_api_key)
):
    try:
        # 1. Fetch all groups the user is a member of
        user_groups = await db_instance.groups.find({"members": current_user_id}).to_list(length=None)  # type: ignore
        group_ids = [g["group_id"] for g in user_groups]

        # 2. Find every message where the user is involved (sender, target, or in the group)
        cursor = db_instance.messages.find({    # type: ignore
            "$or": [
                {"sender_id": current_user_id},
                {"target_id": current_user_id},
                {"thread_id": current_user_id},
                {"target_id": {"$in": group_ids}},
                {"thread_id": {"$in": group_ids}}
            ]
        }).sort("timestamp", 1)  # Sort chronologically

        history = await cursor.to_list(length=None)

        # 3. Format the data to match what the Android app expects
        formatted_messages = []
        for msg in history:
            formatted_messages.append({
                "message_id": msg.get("message_id") or str(msg.get("_id", "")),
                "thread_id": msg.get("thread_id") or msg.get("target_id", ""),
                "sender_id": msg.get("sender_id", ""),
                "target_id": msg.get("target_id", msg.get("thread_id", "")),
                "sender_username": msg.get("sender_username", "Unknown"),
                "target_payload": msg.get("target_payload", ""),
                "self_payload": msg.get("self_payload", ""),
                "timestamp": msg.get("timestamp", 0)
            })

        logger.info(f"User {current_user_id} restored {len(formatted_messages)} historical messages.")
        return {"status": "success", "messages": formatted_messages}

    except Exception as e:
        logger.error(f"History restore failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to restore message history")