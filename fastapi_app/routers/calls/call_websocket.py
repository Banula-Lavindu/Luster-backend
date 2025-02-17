from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi_app.utils.call_manager import call_manager
from fastapi_app.utils.jwt import decode_access_token
from fastapi_app.utils.websocket_manager import ConnectionManager
from ...models.mongo_modles import Call, CallStatus
from ...database import get_mongo_collection
from datetime import datetime
from bson import ObjectId
import json

router = APIRouter(prefix="/ws/calls", tags=["calls"])
calls_collection = get_mongo_collection("calls")
manager = ConnectionManager()

@router.websocket("/signal/{token}")
async def websocket_call_endpoint(websocket: WebSocket, token: str):
    try:
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
            
            await manager.connect(websocket, connection_id)
            
            while True:
                try:
                    message = await websocket.receive_json()
                    
                    if message["type"] == "offer":
                        # Handle call offer
                        call = await calls_collection.find_one({"_id": ObjectId(message["call_id"])})
                        if call and call["status"] == CallStatus.PENDING:
                            await call_manager.send_signal(
                                call["receiver_id"],
                                {
                                    "type": "offer",
                                    "call_id": message["call_id"],
                                    "sdp": message["sdp"],
                                    "caller_id": user_id
                                }
                            )
                        
                    elif message["type"] == "answer":
                        # Handle call answer
                        call = await calls_collection.find_one({"_id": ObjectId(message["call_id"])})
                        if call and call["status"] == CallStatus.ONGOING:
                            await call_manager.send_signal(
                                call["caller_id"],
                                {
                                    "type": "answer",
                                    "call_id": message["call_id"],
                                    "sdp": message["sdp"]
                                }
                            )
                        
                    elif message["type"] == "ice-candidate":
                        # Handle ICE candidates
                        call = await calls_collection.find_one({"_id": ObjectId(message["call_id"])})
                        if call:
                            recipient_id = call["caller_id"] if user_id == call["receiver_id"] else call["receiver_id"]
                            await call_manager.send_signal(
                                recipient_id,
                                {
                                    "type": "ice-candidate",
                                    "call_id": message["call_id"],
                                    "candidate": message["candidate"]
                                }
                            )
                        
                    elif message["type"] == "end-call":
                        # Handle call ending
                        call = await calls_collection.find_one({"_id": ObjectId(message["call_id"])})
                        if call:
                            recipient_id = call["caller_id"] if user_id == call["receiver_id"] else call["receiver_id"]
                            await call_manager.send_signal(
                                recipient_id,
                                {
                                    "type": "end-call",
                                    "call_id": message["call_id"]
                                }
                            )
                            
                            # Update call status in database
                            await calls_collection.update_one(
                                {"_id": ObjectId(message["call_id"])},
                                {
                                    "$set": {
                                        "status": CallStatus.COMPLETED,
                                        "end_time": datetime.utcnow()
                                    }
                                }
                            )
                        
                except json.JSONDecodeError:
                    await websocket.close(code=4000, reason="Invalid message format")
                    break
                
        except Exception as e:
            print(f"Authentication error: {str(e)}")
            await websocket.close(code=1008)
            return
        
    except WebSocketDisconnect:
        call_manager.disconnect(user_id)
        # Handle any ongoing calls for this user
        active_call = await calls_collection.find_one({
            "$or": [
                {"caller_id": user_id, "status": CallStatus.ONGOING},
                {"receiver_id": user_id, "status": CallStatus.ONGOING}
            ]
        })
        if active_call:
            # Update call status and notify other participant
            other_user_id = active_call["caller_id"] if active_call["caller_id"] != user_id else active_call["receiver_id"]
            await call_manager.send_signal(other_user_id, {
                "type": "end-call",
                "call_id": str(active_call["_id"]),
                "reason": "disconnected"
            })
            
            await calls_collection.update_one(
                {"_id": active_call["_id"]},
                {
                    "$set": {
                        "status": CallStatus.COMPLETED,
                        "end_time": datetime.utcnow()
                    }
                }
            ) 