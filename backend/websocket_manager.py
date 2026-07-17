from fastapi import WebSocket
from typing import Dict, List
import json

class ConnectionManager:
    def __init__(self):
        # room_id: list of connections
        self.active_connections: Dict[int, List[WebSocket]] = {}
        # user_id: room_id
        self.user_rooms: Dict[int, int] = {}
        # user_id: WebSocket connection
        self.user_connections: Dict[int, WebSocket] = {}
        # user_id: username
        self.user_usernames: Dict[int, str] = {}
    
    async def connect(self, websocket: WebSocket, room_id: int, user_id: int, username: str):
        await websocket.accept()
        
        if room_id not in self.active_connections:
            self.active_connections[room_id] = []
        
        self.active_connections[room_id].append(websocket)
        self.user_rooms[user_id] = room_id
        self.user_connections[user_id] = websocket
        self.user_usernames[user_id] = username
        
        # Send the list of online users in this room to the newly connected user
        online_users = [
            {"user_id": uid, "username": self.user_usernames[uid]}
            for uid, rid in self.user_rooms.items() if rid == room_id
        ]
        await websocket.send_text(json.dumps({
            "type": "room_users",
            "users": online_users
        }))
        
        # Notify others that user joined
        await self.broadcast_to_room(room_id, {
            "type": "user_joined",
            "user_id": user_id,
            "username": username,
            "message": f"User {username} joined the room"
        })
    
    def disconnect(self, websocket: WebSocket, room_id: int, user_id: int):
        if room_id in self.active_connections:
            if websocket in self.active_connections[room_id]:
                self.active_connections[room_id].remove(websocket)
            if len(self.active_connections[room_id]) == 0:
                del self.active_connections[room_id]
        
        if user_id in self.user_rooms:
            del self.user_rooms[user_id]
        if user_id in self.user_connections:
            del self.user_connections[user_id]
        if user_id in self.user_usernames:
            del self.user_usernames[user_id]
    
    async def send_to_user(self, user_id: int, message: dict):
        websocket = self.user_connections.get(user_id)
        if websocket:
            try:
                await websocket.send_text(json.dumps(message))
            except Exception:
                pass
                
    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)
    
    async def broadcast_to_room(self, room_id: int, message: dict):
        if room_id in self.active_connections:
            disconnected = []
            for connection in self.active_connections[room_id]:
                try:
                    await connection.send_text(json.dumps(message))
                except Exception:
                    disconnected.append(connection)
            
            # Remove disconnected clients
            for connection in disconnected:
                if connection in self.active_connections[room_id]:
                    self.active_connections[room_id].remove(connection)

# Global manager instance
manager = ConnectionManager()
