from typing import Dict, Set, Optional
from fastapi import WebSocket
from datetime import datetime

class ConnectionManager:
    def __init__(self):
        # Store active connections
        self.active_connections: Dict[str, WebSocket] = {}
        # Store chat room participants
        self.chat_rooms: Dict[str, Set[str]] = {}

    async def connect(self, websocket: WebSocket, connection_id: str):
        """Connect a client"""
        await websocket.accept()
        self.active_connections[connection_id] = websocket

    async def disconnect(self, connection_id: str):
        """Disconnect a client"""
        if connection_id in self.active_connections:
            del self.active_connections[connection_id]
            # Remove from all chat rooms
            for room in self.chat_rooms.values():
                room.discard(connection_id)

    async def join_chat(self, chat_id: str, connection_id: str):
        """Add a connection to a chat room"""
        if chat_id not in self.chat_rooms:
            self.chat_rooms[chat_id] = set()
        self.chat_rooms[chat_id].add(connection_id)

    async def leave_chat(self, chat_id: str, connection_id: str):
        """Remove a connection from a chat room"""
        if chat_id in self.chat_rooms:
            self.chat_rooms[chat_id].discard(connection_id)

    def get_chat_participants(self, chat_id: str) -> Set[str]:
        """Get all participants in a chat room"""
        return self.chat_rooms.get(chat_id, set())

    async def broadcast_to_chat(
        self,
        chat_id: str,
        message: dict,
        exclude_connection: Optional[str] = None
    ):
        """Broadcast a message to all participants in a chat room"""
        if chat_id in self.chat_rooms:
            for connection_id in self.chat_rooms[chat_id]:
                if connection_id != exclude_connection:
                    websocket = self.active_connections.get(connection_id)
                    if websocket:
                        try:
                            await websocket.send_json(message)
                        except Exception as e:
                            print(f"Error sending message to {connection_id}: {str(e)}")
                            await self.disconnect(connection_id)

    async def send_personal_message(self, message: dict, connection_id: str):
        """Send a message to a specific connection"""
        if connection_id in self.active_connections:
            websocket = self.active_connections[connection_id]
            try:
                await websocket.send_json(message)
            except Exception as e:
                print(f"Error sending personal message to {connection_id}: {str(e)}")
                await self.disconnect(connection_id)

    async def broadcast_status(self, connection_id: str, is_online: bool):
        """Broadcast user status to all connected clients"""
        status_message = {
            "type": "status_update",
            "user_id": connection_id.split('_')[1],
            "user_type": connection_id.split('_')[0],
            "is_online": is_online,
            "last_seen": self.user_status[connection_id]["last_seen"].isoformat() 
                if connection_id in self.user_status else None
        }
        
        for cid in self.active_connections:
            if cid != connection_id:
                await self.send_personal_message(status_message, cid)

    async def set_current_chat(self, connection_id: str, chat_id: Optional[str] = None):
        """Update user's current active chat"""
        if connection_id in self.user_status:
            self.user_status[connection_id]["current_chat"] = chat_id 
        