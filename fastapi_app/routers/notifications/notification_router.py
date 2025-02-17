from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
from datetime import datetime
from fastapi_app.models.models import User
from fastapi_app.routers.auth import get_current_user
from pydantic import BaseModel
from bson import ObjectId
from fastapi_app.database import get_mongo_collection

router = APIRouter(prefix="/notifications", tags=["Notifications"])

# MongoDB collections
notifications_collection = get_mongo_collection("notifications")

class NotificationUpdate(BaseModel):
    is_read: bool = False

class NotificationResponse(BaseModel):
    notification_id: str
    user_id: int
    type: str
    content: str
    deal_id: Optional[str] = None
    request_type: Optional[str] = None
    gem_name: Optional[str] = None
    gem_image: Optional[str] = None
    is_read: bool = False
    created_at: datetime
    read_at: Optional[datetime] = None

@router.get("/", response_model=List[NotificationResponse])
async def get_notifications(
    current_user: User = Depends(get_current_user),
    unread_only: bool = Query(False, description="Get only unread notifications"),
    limit: int = Query(50, gt=0, le=100),
    offset: int = Query(0, ge=0)
):
    """Get user notifications"""
    try:
        # Build query
        query = {"user_id": current_user.user_id}
        if unread_only:
            query["is_read"] = False

        # Get notifications with pagination
        cursor = notifications_collection.find(query)\
            .sort("created_at", -1)\
            .skip(offset)\
            .limit(limit)
        
        notifications = await cursor.to_list(length=None)
        
        # Format notifications
        formatted_notifications = []
        for notif in notifications:
            notif["notification_id"] = str(notif.pop("_id"))
            formatted_notifications.append(notif)

        return formatted_notifications

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching notifications: {str(e)}"
        )

@router.get("/unread-count")
async def get_unread_count(current_user: User = Depends(get_current_user)):
    """Get count of unread notifications"""
    try:
        count = await notifications_collection.count_documents({
            "user_id": current_user.user_id,
            "is_read": False
        })
        return {"unread_count": count}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error counting unread notifications: {str(e)}"
        )

@router.put("/{notification_id}/mark-read")
async def mark_notification_read(
    notification_id: str,
    current_user: User = Depends(get_current_user)
):
    """Mark a notification as read"""
    try:
        result = await notifications_collection.update_one(
            {
                "_id": ObjectId(notification_id),
                "user_id": current_user.user_id
            },
            {
                "$set": {
                    "is_read": True,
                    "read_at": datetime.utcnow()
                }
            }
        )
        
        if result.modified_count == 0:
            raise HTTPException(
                status_code=404,
                detail="Notification not found or already read"
            )

        return {"message": "Notification marked as read"}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error updating notification: {str(e)}"
        )

@router.put("/mark-all-read")
async def mark_all_read(current_user: User = Depends(get_current_user)):
    """Mark all notifications as read"""
    try:
        result = await notifications_collection.update_many(
            {
                "user_id": current_user.user_id,
                "is_read": False
            },
            {
                "$set": {
                    "is_read": True,
                    "read_at": datetime.utcnow()
                }
            }
        )
        
        return {
            "message": "All notifications marked as read",
            "updated_count": result.modified_count
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error updating notifications: {str(e)}"
        )

@router.delete("/{notification_id}")
async def delete_notification(
    notification_id: str,
    current_user: User = Depends(get_current_user)
):
    """Delete a notification"""
    try:
        result = await notifications_collection.delete_one({
            "_id": ObjectId(notification_id),
            "user_id": current_user.user_id
        })
        
        if result.deleted_count == 0:
            raise HTTPException(
                status_code=404,
                detail="Notification not found"
            )

        return {"message": "Notification deleted successfully"}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error deleting notification: {str(e)}"
        )

@router.delete("/clear-all")
async def clear_all_notifications(
    current_user: User = Depends(get_current_user),
    read_only: bool = Query(False, description="Delete only read notifications")
):
    """Clear all notifications"""
    try:
        query = {"user_id": current_user.user_id}
        if read_only:
            query["is_read"] = True

        result = await notifications_collection.delete_many(query)
        
        return {
            "message": "Notifications cleared successfully",
            "deleted_count": result.deleted_count
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error clearing notifications: {str(e)}"
        )

@router.get("/types")
async def get_notification_types():
    """Get all available notification types"""
    return {
        "types": [
            "new_buy_request",
            "new_sell_request",
            "counter_offer",
            "accepted",
            "rejected",
            "completed",
            "cancelled",
            "reminder",
            "system"
        ]
    }