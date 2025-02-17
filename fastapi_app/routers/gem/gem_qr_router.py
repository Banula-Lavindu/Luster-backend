from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from fastapi_app.database import get_db
from fastapi_app.models.models import User, Gem, Transaction
from fastapi_app.routers.auth import get_current_user
from fastapi_app.routers.Trade.deal_service import DealService
from pydantic import BaseModel, Field
import qrcode
import json
import base64
import os
from uuid import uuid4

router = APIRouter(prefix="/gem-qr", tags=["Gem QR"])
deal_service = DealService()

class QRSaleRequest(BaseModel):
    gem_id: int
    sell_price: float = Field(..., gt=0)
    payment_method: str
    fulfillment_date: datetime
    expiry_minutes: int = Field(default=60, ge=5, le=1440)

class QRScanResponse(BaseModel):
    gem_id: int
    seller_id: int
    sell_price: float
    payment_method: str
    fulfillment_date: datetime
    qr_valid_until: datetime

UPLOAD_DIRECTORY = "uploads/gem_qr"
os.makedirs(UPLOAD_DIRECTORY, exist_ok=True)

@router.post("/generate")
async def generate_sale_qr(
    request: QRSaleRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Generate a QR code for instant gem sale"""
    try:
        # Verify gem ownership
        gem = db.query(Gem).filter(
            Gem.gem_id == request.gem_id,
            Gem.user_id == current_user.user_id
        ).first()
        
        if not gem:
            raise HTTPException(
                status_code=404,
                detail="Gem not found or not owned by you"
            )

        # Create QR data with expiry
        expiry_time = datetime.utcnow() + timedelta(minutes=request.expiry_minutes)
        qr_data = {
            "type": "gem_sale",
            "gem_id": gem.gem_id,
            "seller_id": current_user.user_id,
            "sell_price": request.sell_price,
            "payment_method": request.payment_method,
            "fulfillment_date": request.fulfillment_date.isoformat(),
            "expiry": expiry_time.isoformat(),
            "token": str(uuid4())  # Unique token for verification
        }

        # Generate and save QR code
        encoded_data = base64.urlsafe_b64encode(json.dumps(qr_data).encode()).decode()
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(encoded_data)
        qr.make(fit=True)
        qr_image = qr.make_image(fill_color="black", back_color="white")

        # Save QR code
        os.makedirs("uploads/gem_qr", exist_ok=True)
        file_path = f"uploads/gem_qr/gem_{gem.gem_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.png"
        qr_image.save(file_path)

        # Update gem trace with QR history
        await deal_service.update_gem_qr_history(
            gem.gem_id,
            current_user.user_id,
            request.sell_price,
            request.payment_method,
            expiry_time
        )

        return {
            "message": "QR code generated successfully",
            "qr_path": file_path,
            "expires_at": expiry_time,
            "gem_details": {
                "name": gem.name,
                "category": gem.category,
                "sell_price": request.sell_price
            }
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error generating QR code: {str(e)}"
        )

@router.post("/scan")
async def scan_sale_qr(
    encrypted_data: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Process a scanned gem sale QR code"""
    try:
        # Decode QR data
        qr_data = json.loads(base64.urlsafe_b64decode(encrypted_data).decode())
        
        # Validate QR type and expiry
        if qr_data["type"] != "gem_sale":
            raise HTTPException(status_code=400, detail="Invalid QR code type")
        
        expiry = datetime.fromisoformat(qr_data["expiry"])
        if expiry < datetime.utcnow():
            raise HTTPException(status_code=400, detail="QR code has expired")

        # Prevent self-purchase
        if current_user.user_id == qr_data["seller_id"]:
            raise HTTPException(status_code=400, detail="Cannot purchase your own gem")

        # Get gem and verify availability
        gem = db.query(Gem).filter(
            Gem.gem_id == qr_data["gem_id"],
            Gem.user_id == qr_data["seller_id"]
        ).first()
        
        if not gem:
            raise HTTPException(status_code=404, detail="Gem not found or no longer available")

        # Create transaction
        transaction = Transaction(
            seller_id=qr_data["seller_id"],
            buyer_id=current_user.user_id,
            gem_id=gem.gem_id,
            amount=qr_data["sell_price"],
            payment_type=qr_data["payment_method"],
            fulfillment_date=datetime.fromisoformat(qr_data["fulfillment_date"]),
            transaction_status="completed",
            transaction_type="qr_sale"
        )
        
        db.add(transaction)

        # Update gem ownership
        gem.user_id = current_user.user_id
        gem.cost = qr_data["sell_price"]
        gem.sell_price = None
        
        db.commit()
        db.refresh(transaction)

        # Update gem lifetime trace
        await deal_service.update_gem_lifetime_trace(
            gem_id=gem.gem_id,
            transaction=transaction,
            gem=gem,
            db=db
        )

        return {
            "message": "Purchase completed successfully",
            "transaction_id": transaction.transaction_id,
            "gem_details": {
                "gem_id": gem.gem_id,
                "name": gem.name,
                "user_id": qr_data["seller_id"],
                "category": gem.category,
                "price": transaction.amount,
                "payment_method": transaction.payment_type,
                "fulfillment_date": transaction.fulfillment_date
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error processing QR code: {str(e)}"
        )

@router.get("/active/{gem_id}")
async def get_active_qr(
    gem_id: int,
    current_user: User = Depends(get_current_user)
):
    """Get active QR code for a gem if exists"""
    try:
        # List QR codes in directory
        qr_files = [f for f in os.listdir(UPLOAD_DIRECTORY) 
                   if f.startswith(f"gem_{gem_id}_")]
        
        if not qr_files:
            return {"message": "No active QR code found for this gem"}

        # Get most recent QR
        latest_qr = sorted(qr_files)[-1]
        qr_path = os.path.join(UPLOAD_DIRECTORY, latest_qr)

        return {
            "message": "Active QR code found",
            "qr_path": qr_path
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving QR code: {str(e)}"
        )