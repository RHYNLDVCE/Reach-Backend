from fastapi import WebSocket
from typing import Dict
from app.core.database import db_instance
import time

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, user_id: str, websocket: WebSocket):
            await websocket.accept()
            self.active_connections[user_id] = websocket
            await db_instance.users.update_one({"user_id": user_id},{"$set": {"is_online": True, "last_seen": int(time.time() * 1000)}}) # type: ignore

    async def disconnect(self, user_id: str):
        if user_id in self.active_connections:
            del self.active_connections[user_id]
            await db_instance.users.update_one({"user_id": user_id}, {"$set": {"is_online": False, "last_seen": int(time.time() * 1000)}}) # type: ignore

    async def send_personal_message(self, message: dict, user_id: str):
        if user_id in self.active_connections:
            await self.active_connections[user_id].send_json(message)

manager = ConnectionManager()