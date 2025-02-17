from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from fastapi_app.database import get_db
from fastapi_app.routers.auth import get_current_user
from fastapi_app.routers.Trade.external_trade_service import (
    process_buy_request,
    process_sell_request,
    get_pending_transactions,
    complete_transaction
)
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

router = APIRouter(prefix="/external-trade", tags=["External Trade"])

class GemData(BaseModel):
    name: str
    category: str
    sub_category: Optional[str] = None
    cost: float
    sell_price: Optional[float] = None
    description: Optional[str] = None
    images: List[str] = []

@router.post("/buy-request")
async def handle_buy_request(
    dealer_id: int,
    gem_data: GemData,
    transaction_type: str,
    fulfillment_date: datetime,
    db: Session = Depends(get_db),
    current_user: int = Depends(get_current_user)
):
    try:
        gem_id = await process_buy_request(dealer_id, gem_data.dict(), transaction_type, fulfillment_date, db, current_user)
        return {"message": "Buy request processed successfully", "gem_id": gem_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="An error occurred while processing the buy request")

@router.post("/sell")
async def handle_sell_request(
    gem_id: int,
    dealer_id: int,
    sell_price: float,
    fulfillment_date: datetime,
    db: Session = Depends(get_db),
    current_user: int = Depends(get_current_user)
):
    try:
        result = await process_sell_request(gem_id, dealer_id, sell_price, fulfillment_date, db, current_user)
        return {"message": "Sell request processed successfully", "result": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="An error occurred while processing the sell request")

@router.get("/pending-transactions")
async def get_pending_transactions_route(
    db: Session = Depends(get_db),
    current_user: int = Depends(get_current_user)
):
    try:
        transactions = await get_pending_transactions(db, current_user)
        return {"pending_transactions": transactions}
    except Exception as e:
        raise HTTPException(status_code=500, detail="An error occurred while retrieving pending transactions")

@router.post("/complete-transaction/{transaction_id}")
async def complete_transaction_route(
    transaction_id: int,
    db: Session = Depends(get_db),
    current_user: int = Depends(get_current_user)
):
    try:
        result = await complete_transaction(transaction_id, db, current_user)
        return {"message": "Transaction completed successfully", "result": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="An error occurred while completing the transaction")
