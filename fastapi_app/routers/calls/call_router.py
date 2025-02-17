from fastapi import APIRouter, HTTPException, Depends, WebSocket
from typing import Optional, Dict
from datetime import datetime
from ...models.mongo_modles import Call, CallStatus
from ...database import get_mongo_collection
from ..auth import get_current_user
from ...models.models import User
from sqlalchemy.orm import Session
from ...database import get_db
from bson import ObjectId

router = APIRouter(prefix="/calls", tags=["calls"])

# Get MongoDB collections
calls_collection = get_mongo_collection("calls")

@router.post("/initiate")
async def initiate_call(
    receiver_id: int,
    call_type: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Initiate a new call"""
    try:
        # Verify receiver exists
        receiver = db.query(User).filter(User.user_id == receiver_id).first()
        if not receiver:
            raise HTTPException(status_code=404, detail="Receiver not found")
            
        # Check if there's an ongoing call
        ongoing_call = await calls_collection.find_one({
            "$or": [
                {"caller_id": current_user.user_id, "status": "ongoing"},
                {"receiver_id": current_user.user_id, "status": "ongoing"}
            ]
        })
        if ongoing_call:
            raise HTTPException(status_code=400, detail="You have an ongoing call")
            
        # Create new call
        call = Call(
            caller_id=current_user.user_id,
            receiver_id=receiver_id,
            call_type=call_type,
            status=CallStatus.PENDING
        )
        
        result = await calls_collection.insert_one(call.dict())
        call_id = str(result.inserted_id)
        
        return {
            "call_id": call_id,
            "message": "Call initiated successfully"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{call_id}/answer")
async def answer_call(
    call_id: str,
    current_user: User = Depends(get_current_user)
):
    """Answer an incoming call"""
    try:
        call = await calls_collection.find_one({"_id": ObjectId(call_id)})
        if not call:
            raise HTTPException(status_code=404, detail="Call not found")
            
        if call["receiver_id"] != current_user.user_id:
            raise HTTPException(status_code=403, detail="Not authorized to answer this call")
            
        if call["status"] != CallStatus.PENDING:
            raise HTTPException(status_code=400, detail="Call cannot be answered")
            
        await calls_collection.update_one(
            {"_id": ObjectId(call_id)},
            {"$set": {"status": CallStatus.ONGOING}}
        )
        
        return {"message": "Call answered successfully"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{call_id}/end")
async def end_call(
    call_id: str,
    current_user: User = Depends(get_current_user)
):
    """End an ongoing call"""
    try:
        call = await calls_collection.find_one({"_id": ObjectId(call_id)})
        if not call:
            raise HTTPException(status_code=404, detail="Call not found")
            
        if call["caller_id"] != current_user.user_id and call["receiver_id"] != current_user.user_id:
            raise HTTPException(status_code=403, detail="Not authorized to end this call")
            
        end_time = datetime.utcnow()
        duration = int((end_time - datetime.fromisoformat(call["start_time"])).total_seconds())
        
        await calls_collection.update_one(
            {"_id": ObjectId(call_id)},
            {
                "$set": {
                    "status": CallStatus.COMPLETED,
                    "end_time": end_time,
                    "duration": duration
                }
            }
        )
        
        return {
            "message": "Call ended successfully",
            "duration": duration
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{call_id}/reject")
async def reject_call(
    call_id: str,
    current_user: User = Depends(get_current_user)
):
    """Reject an incoming call"""
    try:
        call = await calls_collection.find_one({"_id": ObjectId(call_id)})
        if not call:
            raise HTTPException(status_code=404, detail="Call not found")
            
        if call["receiver_id"] != current_user.user_id:
            raise HTTPException(status_code=403, detail="Not authorized to reject this call")
            
        await calls_collection.update_one(
            {"_id": ObjectId(call_id)},
            {
                "$set": {
                    "status": CallStatus.REJECTED,
                    "end_time": datetime.utcnow()
                }
            }
        )
        
        return {"message": "Call rejected successfully"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/history")
async def get_call_history(
    current_user: User = Depends(get_current_user),
    limit: int = 50,
    skip: int = 0
):
    """Get user's call history"""
    try:
        calls = await calls_collection.find({
            "$or": [
                {"caller_id": current_user.user_id},
                {"receiver_id": current_user.user_id}
            ]
        }).sort("start_time", -1).skip(skip).limit(limit).to_list(None)
        
        return calls
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) 