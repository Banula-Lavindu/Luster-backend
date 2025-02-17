from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
from datetime import datetime
from fastapi_app.models.models import User, Gem, Expense
from fastapi_app.database import get_db
from sqlalchemy.orm import Session
from fastapi_app.routers.auth import get_current_user
from pydantic import BaseModel, Field
from bson import ObjectId

router = APIRouter(prefix="/expenses", tags=["Expenses"])

class ExpenseCreate(BaseModel):
    reason: str
    amount: float = Field(..., gt=0)

class ExpenseResponse(BaseModel):
    expense_id: int
    gem_id: int
    reason: str
    amount: float
    date_added: datetime

@router.post("/{gem_id}/add", response_model=ExpenseResponse)
async def add_expense(
    gem_id: int,
    expense: ExpenseCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Add an expense for a gem"""
    try:
        # Verify gem ownership
        gem = db.query(Gem).filter(
            Gem.gem_id == gem_id,
            Gem.user_id == current_user.user_id
        ).first()
        
        if not gem:
            raise HTTPException(
                status_code=404,
                detail="Gem not found or not owned by you"
            )

        # Create new expense
        new_expense = Expense(
            gem_id=gem_id,
            reason=expense.reason,
            amount=expense.amount
        )
        
        db.add(new_expense)
        db.commit()
        db.refresh(new_expense)

        return ExpenseResponse(
            expense_id=new_expense.expense_id,
            gem_id=new_expense.gem_id,
            reason=new_expense.reason,
            amount=new_expense.amount,
            date_added=new_expense.date_added
        )

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{gem_id}/list", response_model=List[ExpenseResponse])
async def list_expenses(
    gem_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List all expenses for a gem"""
    try:
        # Verify gem ownership
        gem = db.query(Gem).filter(Gem.gem_id == gem_id).first()
        if not gem:
            raise HTTPException(status_code=404, detail="Gem not found")

        if gem.user_id != current_user.user_id:
            raise HTTPException(
                status_code=403,
                detail="Not authorized to view expenses for this gem"
            )

        expenses = db.query(Expense).filter(Expense.gem_id == gem_id).all()
        return [ExpenseResponse(
            expense_id=expense.expense_id,
            gem_id=expense.gem_id,
            reason=expense.reason,
            amount=expense.amount,
            date_added=expense.date_added
        ) for expense in expenses]

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{gem_id}/summary")
async def get_expense_summary(
    gem_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get expense summary for a gem"""
    try:
        # Verify gem ownership
        gem = db.query(Gem).filter(Gem.gem_id == gem_id).first()
        if not gem:
            raise HTTPException(status_code=404, detail="Gem not found")

        if gem.user_id != current_user.user_id:
            raise HTTPException(
                status_code=403,
                detail="Not authorized to view expenses for this gem"
            )

        # Get all expenses
        expenses = db.query(Expense).filter(Expense.gem_id == gem_id).all()
        
        # Calculate totals
        total_expenses = sum(expense.amount for expense in expenses)
        full_cost = gem.cost + total_expenses

        return {
            "gem_id": gem_id,
            "base_cost": gem.cost,
            "total_expenses": total_expenses,
            "full_cost": full_cost,
            "sell_price": gem.sell_price,
            "potential_profit": gem.sell_price - full_cost if gem.sell_price else None,
            "expense_count": len(expenses)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{expense_id}")
async def delete_expense(
    expense_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete an expense"""
    try:
        # Get the expense and verify ownership through gem
        expense = db.query(Expense).join(Gem).filter(
            Expense.expense_id == expense_id,
            Gem.user_id == current_user.user_id
        ).first()

        if not expense:
            raise HTTPException(
                status_code=404,
                detail="Expense not found or not authorized to delete"
            )

        db.delete(expense)
        db.commit()

        return {"message": "Expense deleted successfully"}

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/{expense_id}")
async def update_expense(
    expense_id: int,
    expense_update: ExpenseCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update an expense"""
    try:
        # Get the expense and verify ownership through gem
        expense = db.query(Expense).join(Gem).filter(
            Expense.expense_id == expense_id,
            Gem.user_id == current_user.user_id
        ).first()

        if not expense:
            raise HTTPException(
                status_code=404,
                detail="Expense not found or not authorized to update"
            )

        # Update expense fields
        expense.reason = expense_update.reason
        expense.amount = expense_update.amount

        db.commit()
        db.refresh(expense)

        return ExpenseResponse(
            expense_id=expense.expense_id,
            gem_id=expense.gem_id,
            reason=expense.reason,
            amount=expense.amount,
            date_added=expense.date_added
        )

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e)) 