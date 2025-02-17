from typing import Dict, Set
from fastapi import WebSocket
import json
from datetime import datetime

class CallManager:
    def __init__(self):
        self.active_connections: Dict[int, WebSocket] = {}
        self.ongoing_calls: Dict[str, Dict] = {}
        
    async def connect(self, user_id: int, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[user_id] = websocket
        
    def disconnect(self, user_id: int):
        if user_id in self.active_connections:
            del self.active_connections[user_id]
            
    async def send_signal(self, user_id: int, message: dict):
        if user_id in self.active_connections:
            await self.active_connections[user_id].send_json(message)
            
    async def broadcast_to_call(self, call_id: str, message: dict, exclude_user: int = None):
        if call_id in self.ongoing_calls:
            participants = self.ongoing_calls[call_id]["participants"]
            for user_id in participants:
                if user_id != exclude_user and user_id in self.active_connections:
                    await self.send_signal(user_id, message)

call_manager = CallManager() 