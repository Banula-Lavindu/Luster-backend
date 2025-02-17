from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from fastapi_app.database import get_db
from fastapi_app.models.models import User, Gem
from fastapi_app.routers.auth import get_current_user
from fastapi_app.routers.chat.chat_service import ChatService
from pydantic import BaseModel

router = APIRouter(prefix="/gem-share", tags=["Gem Sharing"])
chat_service = ChatService()

class GemShareRequest(BaseModel):
    chat_id: str
    gem_id: int
    message: Optional[str] = None

@router.post("/share")
async def share_gem(
    request: GemShareRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Share a gem in a chat"""
    try:
        # Verify gem ownership
        gem = db.query(Gem).filter(
            Gem.gem_id == request.gem_id,
            Gem.user_id == current_user.user_id
        ).first()
        
        if not gem:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Gem not found or not owned by you"
            )

        # Check if user is participant in chat
        is_participant = await chat_service.is_chat_participant(
            request.chat_id,
            current_user.user_id
        )
        
        if not is_participant:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not a participant in this chat"
            )

        # Share the gem
        message_id = await chat_service.share_gem_in_chat(
            chat_id=request.chat_id,
            gem_id=request.gem_id,
            sender_id=current_user.user_id,
            db=db
        )

        return {
            "message": "Gem shared successfully",
            "message_id": message_id,
            "chat_id": request.chat_id,
            "gem_details": {
                "gem_id": gem.gem_id,
                "name": gem.name,
                "category": gem.category,
                "price": gem.sell_price,
                "image": gem.images,
                "description ": gem.description
            }
        }

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error sharing gem: {str(e)}"
        )

@router.get("/shared-gems/{chat_id}")
async def get_shared_gems(
    chat_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all gems shared in a specific chat"""
    try:
        # Verify chat participation
        is_participant = await chat_service.is_chat_participant(
            chat_id,
            current_user.user_id
        )
        
        if not is_participant:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not a participant in this chat"
            )

        # Get shared gems from chat messages
        shared_gems = await chat_service.get_shared_gems_in_chat(chat_id)
        
        # Enrich with current gem details
        enriched_gems = []
        for shared_gem in shared_gems:
            gem = db.query(Gem).filter(Gem.gem_id == shared_gem["gem_id"]).first()
            if gem:
                total_expenses = sum(expense.amount for expense in gem.expenses)
                enriched_gems.append({
                    "message_id": shared_gem["message_id"],
                    "shared_at": shared_gem["created_at"],
                    "shared_by": shared_gem["sender_id"],
                    "gem_details": {
                        "gem_id": gem.gem_id,
                        "name": gem.name,
                        "category": gem.category,
                        "sub_category": gem.sub_category,
                        "cost": gem.cost,
                        "sell_price": gem.sell_price,
                        "description": gem.description,
                        "images": gem.images,
                        "total_expenses": total_expenses,
                        "full_cost": gem.cost + total_expenses
                    }
                })

        return enriched_gems

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving shared gems: {str(e)}"
        )

@router.delete("/shared-gems/{chat_id}/{message_id}")
async def delete_shared_gem(
    chat_id: str,
    message_id: str,
    current_user: User = Depends(get_current_user)
):
    """Delete a shared gem message"""
    try:
        # Verify ownership of the message
        message = await chat_service.get_message(message_id)
        if not message or message["sender_id"] != current_user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Message not found or not owned by you"
            )

        # Delete the message
        await chat_service.delete_message(chat_id, message_id)

        return {"message": "Shared gem message deleted successfully"}

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error deleting shared gem message: {str(e)}"
        ) 