from fastapi import APIRouter, Depends, HTTPException, status, WebSocket, WebSocketDisconnect
from typing import List
from app.models.message import SecureCloudMessage
from app.core.database import db_instance
from app.api.dependencies import verify_api_key
from app.core.security import get_current_user
from app.core.config import settings
from app.api.ws_manager import manager
from pymongo import UpdateOne
from firebase_admin import messaging
import jwt

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
    client_api_key = websocket.headers.get("X-API-KEY")
    if client_api_key != settings.API_KEY:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            raise ValueError("Invalid token payload")
    except:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
        
    await manager.connect(user_id, websocket) #type: ignore
    
    try:
        while True:
            data = await websocket.receive_json()
            
            # --- 1. Handle ACKs ---
            if data.get("type") == "ACK":
                msg_id = data.get("message_id")
                await db_instance.messages.update_one({"message_id": msg_id},{"$set": {"is_delivered_to_target": True}}) #type: ignore
                sender_id = data.get("original_sender_id")
                await manager.send_personal_message(data, sender_id)
                continue
            
            # --- 2. Save Message to Database ---
            target_id = data.get("target_id")
            sender_id = data.get("sender_id")
            await db_instance.messages.update_one({"message_id": data.get("message_id")},{"$set": data},upsert=True) #type: ignore

            # --- 3. Echo to Sender ---
            if sender_id in manager.active_connections:
                await manager.send_personal_message(data, sender_id)

            # --- 4. Route to Target (1-on-1 OR Group Chat) ---
            if target_id in manager.active_connections:
                # It's a 1-on-1 message and the user is online
                await manager.send_personal_message(data, target_id)
            else:
                # It might be a Group Chat! Let's check the database.
                group = await db_instance.groups.find_one({"group_id": target_id}) # type: ignore
                
                # Safely extract the username and encrypted text from the incoming WebSocket JSON
                sender_name = data.get("sender_username", "Someone")
                encrypted_text = data.get("encrypted_payload", {}).get("data", "")

                if group:
                    # Broadcast to all members (except the sender)
                    for member_id in group.get("members", []):
                        if member_id != sender_id:
                            if member_id in manager.active_connections:
                                # Member is online!
                                await manager.send_personal_message(data, member_id)
                            else:
                                # UPDATED: Group member offline
                                await send_offline_notification(
                                    target_id=member_id, 
                                    sender_username=sender_name, 
                                    thread_id=target_id, # The thread is the Group ID
                                    encrypted_data=encrypted_text
                                )
                else:
                    # UPDATED: 1-on-1 message offline
                    await send_offline_notification(
                        target_id=target_id, 
                        sender_username=sender_name, 
                        thread_id=sender_id, # The thread is the Sender's ID
                        encrypted_data=encrypted_text
                    )

    except WebSocketDisconnect:
        await manager.disconnect(user_id) #type: ignore