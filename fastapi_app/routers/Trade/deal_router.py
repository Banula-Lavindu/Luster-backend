from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, List
from datetime import datetime
from fastapi_app.models.models import User, Gem
from fastapi_app.database import get_db
from sqlalchemy.orm import Session
from fastapi_app.routers.auth import get_current_user
from pydantic import BaseModel, Field
from .deal_service import DealService
from enum import Enum

router = APIRouter(prefix="/deals", tags=["Deals"])

class RequestType(str, Enum):
    BUY = "buy"
    SELL = "sell"
    ALL = "all"

class DealRequest(BaseModel):
    gem_id: int
    counterparty_id: int  # seller_id for buy requests, buyer_id for sell requests
    price: float = Field(..., gt=0)
    payment_method: str
    fulfillment_date: datetime
    notes: Optional[str] = None

class NegotiateRequest(BaseModel):
    price: float = Field(..., gt=0)
    payment_method: str
    fulfillment_date: datetime
    notes: Optional[str] = None

class UpdateSellPriceRequest(BaseModel):
    sell_price: float = Field(..., gt=0)

class DealResponse(BaseModel):
    message: str
    request_id: str
    request_type: str
    gem_details: Optional[dict] = None
    transaction_details: Optional[dict] = None

deal_service = DealService()

@router.post("/create/{request_type}", response_model=DealResponse)
async def create_deal_request(
    request_type: RequestType,
    request: DealRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new buy or sell request"""
    try:
        if request_type == RequestType.ALL:
            raise HTTPException(status_code=400, detail="Invalid request type")

        # Get gem details for response
        gem = db.query(Gem).filter(Gem.gem_id == request.gem_id).first()
        if not gem:
            raise HTTPException(status_code=404, detail="Gem not found")

        request_id = await deal_service.create_request(request, current_user, db, request_type)
        
        return DealResponse(
            message=f"{request_type.capitalize()} request created successfully",
            request_id=request_id,
            request_type=request_type,
            gem_details={
                "name": gem.name,
                "category": gem.category,
                "images": gem.images
            }
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{request_id}/negotiate")
async def negotiate_deal(
    request_id: str,
    request: NegotiateRequest,
    request_type: RequestType = Query(..., description="Type of request (buy/sell)"),
    current_user: User = Depends(get_current_user)
):
    """Counter-offer or negotiate a deal"""
    try:
        if request_type == RequestType.ALL:
            raise HTTPException(status_code=400, detail="Invalid request type")

        await deal_service.negotiate_request(request_id, request, current_user, request_type)
        return {
            "message": "Counter offer sent successfully",
            "request_id": request_id,
            "new_price": request.price,
            "payment_method": request.payment_method,
            "fulfillment_date": request.fulfillment_date
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{request_id}/accept")
async def accept_deal(
    request_id: str,
    request_type: RequestType = Query(..., description="Type of request (buy/sell)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Accept a deal and update gem ownership"""
    try:
        if request_type == RequestType.ALL:
            raise HTTPException(status_code=400, detail="Invalid request type")

        gem_id, transaction = await deal_service.accept_request(request_id, current_user, db, request_type)
        
        # Get updated gem details
        gem = db.query(Gem).filter(Gem.gem_id == gem_id).first()
        
        return {
            "message": f"{request_type.capitalize()} request accepted successfully",
            "request_id": request_id,
            "gem_id": gem_id,
            "new_owner_id": gem.user_id,
            "transaction_status": "completed",
            "transaction_details": {
                "transaction_id": transaction.transaction_id,
                "amount": transaction.amount,
                "payment_type": transaction.payment_type,
                "fulfillment_date": transaction.fulfillment_date
            },
            "gem_details": {
                "name": gem.name,
                "category": gem.category,
                "images": gem.images
            }
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{request_id}/reject")
async def reject_deal(
    request_id: str,
    request_type: RequestType = Query(..., description="Type of request (buy/sell)"),
    current_user: User = Depends(get_current_user)
):
    """Reject a deal"""
    try:
        if request_type == RequestType.ALL:
            raise HTTPException(status_code=400, detail="Invalid request type")

        await deal_service.reject_request(request_id, current_user, request_type)
        return {
            "message": f"{request_type.capitalize()} request rejected successfully",
            "request_id": request_id
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/my-requests", response_model=List[dict])
async def get_my_requests(
    request_type: RequestType = Query(RequestType.ALL, description="Type of requests to fetch"),
    status: Optional[str] = Query(None, description="Filter by status"),
    current_user: User = Depends(get_current_user)
):
    """Get all requests for the current user"""
    try:
        requests = await deal_service.get_user_requests(current_user.user_id, request_type)
        
        # Filter by status if provided
        if status:
            requests = [r for r in requests if r.get("status") == status]
            
        return requests
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/gems/{gem_id}/sell-price")
async def update_sell_price(
    gem_id: int,
    request: UpdateSellPriceRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update the selling price of a gem"""
    try:
        gem = db.query(Gem).filter(
            Gem.gem_id == gem_id,
            Gem.user_id == current_user.user_id
        ).first()
        
        if not gem:
            raise HTTPException(
                status_code=404,
                detail="Gem not found or not owned by you"
            )

        gem.sell_price = request.sell_price
        db.commit()

        return {
            "message": "Selling price updated successfully",
            "gem_id": gem_id,
            "new_price": request.sell_price
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/statistics")
async def get_deal_statistics(
    current_user: User = Depends(get_current_user)
):
    """Get statistics about user's deals"""
    try:
        stats = await deal_service.get_user_deal_statistics(current_user.user_id)
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) 
