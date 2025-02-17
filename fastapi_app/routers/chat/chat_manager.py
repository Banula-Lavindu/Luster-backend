from fastapi import WebSocket
from typing import Dict, Set, Optional
from datetime import datetime
import json

class ChatManager:
    def __init__(self):
        self.active_connections: Dict[str, Dict[int, WebSocket]] = {}
        self.chat_rooms: Dict[str, Set[int]] = {}
        self.user_rooms: Dict[int, Set[str]] = {}

    async def connect(self, websocket: WebSocket, chat_id: str, user_id: int):
        await websocket.accept()
        if chat_id not in self.active_connections:
            self.active_connections[chat_id] = {}
            self.chat_rooms[chat_id] = set()
        self.active_connections[chat_id][user_id] = websocket
        self.chat_rooms[chat_id].add(user_id)
        if user_id not in self.user_rooms:
            self.user_rooms[user_id] = set()
        self.user_rooms[user_id].add(chat_id)

    def disconnect(self, chat_id: str, user_id: int):
        if chat_id in self.active_connections:
            self.active_connections[chat_id].pop(user_id, None)
            self.chat_rooms[chat_id].discard(user_id)
            if not self.active_connections[chat_id]:
                del self.active_connections[chat_id]
                del self.chat_rooms[chat_id]
        if user_id in self.user_rooms:
            self.user_rooms[user_id].discard(chat_id)
            if not self.user_rooms[user_id]:
                del self.user_rooms[user_id]

    async def broadcast(self, chat_id: str, message: dict):
        if chat_id in self.active_connections:
            for connection in self.active_connections[chat_id].values():
                await connection.send_json(message)

manager = ChatManager() 