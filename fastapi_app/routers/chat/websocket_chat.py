from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from fastapi_app.utils.websocket_manager import ConnectionManager
from fastapi_app.routers.chat.chat_service import ChatService
from fastapi_app.utils.jwt import decode_access_token
from fastapi_app.models.chat_models import ChatMessage
from datetime import datetime
import json
import re
from fastapi_app.config import settings
from bson import ObjectId
from fastapi.encoders import jsonable_encoder  # Add this import

router = APIRouter(prefix="/ws", tags=["WebSocket"])
manager = ConnectionManager()
chat_service = ChatService()
active_connections = {}  # Store active connections by user_id

class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, ObjectId):
            return str(obj)
        return super().default(obj)

@router.websocket("/chat/{token}")
async def chat_websocket(websocket: WebSocket, token: str):
    """WebSocket endpoint for real-time chat functionality"""
    connection_id = None
    user_id = None
    
    try:
        # Accept connection first
        await websocket.accept()
        
        try:
            # Use common token validation
            user_id = decode_access_token(token)
            if not user_id:
                print(f"Token validation failed: {token}")
                await websocket.close(code=1008)
                return

            connection_id = f"user_{user_id}"
            print(f"Valid connection for user {user_id}")
            
            # Store new connection without accepting again
            active_connections[user_id] = websocket
            
            # Send connection confirmation
            await websocket.send_json({
                "type": "connection_established",
                "user_id": user_id
            })
            
            print(f"WebSocket connected for user {user_id}")
            
            # Handle messages
            while True:
                try:
                    message = await websocket.receive_text()
                    print(f"Received message from user {user_id}: {message}")
                    data = json.loads(message)
                    await handle_websocket_message(data, user_id, websocket, manager)
                except WebSocketDisconnect:
                    print(f"WebSocket disconnected for user {user_id}")
                    break
                except json.JSONDecodeError:
                    print(f"Invalid JSON received: {message}")
                    continue
                except Exception as e:
                    print(f"Error handling message: {str(e)}")
                    await websocket.send_json({
                        "type": "error",
                        "message": str(e)
                    })
                    continue
                    
        except Exception as e:
            print(f"Authentication error: {str(e)}")
            await websocket.close(code=1008)
            return
            
    finally:
        if connection_id and user_id:
            if user_id in active_connections:
                del active_connections[user_id]
            await chat_service.update_user_last_seen(user_id, datetime.utcnow())
            print(f"Cleaned up connection for user {user_id}")

async def handle_websocket_message(data: dict, user_id: str, websocket: WebSocket, manager: ConnectionManager):
    """Handle different types of WebSocket messages"""
    try:
        message_type = data.get("type")
        chat_id = data.get("chat_id")
        
        if not chat_id:
            await websocket.send_json({
                "type": "error",
                "message": "chat_id is required"
            })
            return
            
        if message_type == "message":
            content = data.get("content")
            if not content:
                await websocket.send_json({
                    "type": "error",
                    "message": "Message content is required"
                })
                return

            try:
                # Create message object
                message = ChatMessage(
                    chat_id=str(chat_id),
                    sender_id=str(user_id),
                    sender_type="user",
                    content=content,
                    message_type=data.get("message_type", "text"),
                    timestamp=datetime.utcnow(),
                    read_by=[{
                        "user_id": str(user_id),
                        "user_type": "user",
                        "timestamp": datetime.utcnow().isoformat()
                    }]
                )
                
                # Save message
                saved_message = await chat_service.add_message(message)
                
                # Convert to JSON-safe format
                response_message = {
                    "type": "message_sent",
                    "message": {
                        "message_id": saved_message["message_id"],
                        "chat_id": saved_message["chat_id"],
                        "sender_id": saved_message["sender_id"],
                        "sender_type": saved_message["sender_type"],
                        "content": saved_message["content"],
                        "message_type": saved_message["message_type"],
                        "timestamp": saved_message["timestamp"],
                        "read_by": saved_message["read_by"],
                        "delivered_to": saved_message["delivered_to"]
                    }
                }
                
                # Broadcast to other participants
                await manager.broadcast_to_chat(
                    chat_id,
                    {
                        "type": "new_message",
                        "message": response_message["message"]
                    },
                    exclude_connection=f"user_{user_id}"
                )
                
                # Send confirmation to sender
                await websocket.send_json(response_message)
                
                # Increment unread count for other participants
                await chat_service.increment_unread_count(chat_id, str(user_id), "user")
                
            except Exception as e:
                error_msg = f"Failed to process message: {str(e)}"
                print(error_msg)
                await websocket.send_json({
                    "type": "error",
                    "message": error_msg
                })
                return

        elif message_type == "join_chat":
            connection_id = f"user_{user_id}"
            await manager.join_chat(chat_id, connection_id)
            await chat_service.mark_messages_as_delivered(
                chat_id=chat_id,
                user_id=user_id,
                user_type="user"
            )
            print(f"User {user_id} joined chat {chat_id}")
            
            # Send confirmation
            await websocket.send_json({
                "type": "joined_chat",
                "chat_id": chat_id
            })
        elif message_type == "mark_read":
            message_id = data.get("message_id")
            await chat_service.mark_messages_as_read(
                chat_id=chat_id,
                user_id=user_id,
                user_type="user",
                message_id=message_id
            )
            print(f"Marked message {message_id} as read in chat {chat_id}")
            
        # Other message types...

    except Exception as e:
        print(f"Error handling websocket message: {str(e)}")
        await websocket.send_json({
            "type": "error",
            "message": f"Error handling message: {str(e)}"
        })