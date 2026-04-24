from fastapi import WebSocket
from typing import Dict, List
from app.core.database import db_instance
import time
import logging

logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        # Change to store a list of WebSockets for each user to support multi-device
        self.active_connections: Dict[str, List[WebSocket]] = {}

    async def connect(self, user_id: str, websocket: WebSocket):
        await websocket.accept()
        
        # Initialize the list if this is the user's first device
        if user_id not in self.active_connections:
            self.active_connections[user_id] = []
            
        self.active_connections[user_id].append(websocket)
        
        # Mark as online in DB
        await db_instance.users.update_one( # type: ignore
            {"user_id": user_id},
            {"$set": {"is_online": True, "last_seen": int(time.time() * 1000)}} 
        ) 

    async def disconnect(self, user_id: str, websocket: WebSocket):
        if user_id in self.active_connections:
            # Remove this specific device's connection
            if websocket in self.active_connections[user_id]:
                self.active_connections[user_id].remove(websocket)
                
            # If the user has no more active devices, mark them as offline
            if len(self.active_connections[user_id]) == 0:
                del self.active_connections[user_id]
                await db_instance.users.update_one( # type: ignore
                    {"user_id": user_id}, 
                    {"$set": {"is_online": False, "last_seen": int(time.time() * 1000)}}
                ) 

    async def send_personal_message(self, message: dict, user_id: str):
        if user_id in self.active_connections:
            # Broadcast the message to EVERY device the user has open
            for connection in self.active_connections[user_id]:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.warning(f"Failed to send to one of user {user_id}'s devices: {e}")
            
    async def route_message(self, message: dict, target_id: str):
        group = await db_instance.groups.find_one({"group_id": target_id}) # type: ignore
        
        if group:
            for member_id in group.get("members", []):
                if member_id in self.active_connections:
                    for connection in self.active_connections[member_id]:
                        try:
                            await connection.send_json(message)
                        except Exception:
                            pass
        else:
            if target_id in self.active_connections:
                for connection in self.active_connections[target_id]:
                    try:
                        await connection.send_json(message)
                    except Exception:
                        pass

manager = ConnectionManager()