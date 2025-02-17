from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status, Form
from sqlalchemy.orm import Session
from typing import List, Optional
from fastapi_app.database import get_db
from fastapi_app.models.models import Gem, User, Expense
import os
import uuid
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
import logging

router = APIRouter(prefix="/Gem_Management", tags=["Gem_Management"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Directory for saving uploaded images
UPLOAD_DIRECTORY = os.getenv("UPLOAD_DIRECTORY", "uploads/gem_images")
os.makedirs(UPLOAD_DIRECTORY, exist_ok=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class GemCreate(BaseModel):
    name: str
    category: str
    sub_category: Optional[str] = "Natural"
    cost: float = 0.0
    sell_price: float = 0.0
    description: str = ""

class GemResponse(BaseModel):
    gem_id: int
    name: str
    category: str
    sub_category: Optional[str]
    cost: float
    sell_price: float
    description: str
    images: List[str]
    total_expenses: float
    full_cost: float

def get_current_user(token: str = Depends(oauth2_scheme)):
    # Implement your authentication logic here
    # For now, we'll just return a dummy user ID
    return 1  # Replace with actual user ID from token


#------ Add new Gem --------------#

@router.post("/gems/add", response_model=GemResponse)
def add_gem(
    name: str = Form(...),
    category: str = Form(...),
    sub_category: str = Form("Natural"),
    cost: float = Form(0.0),
    sell_price: float = Form(0.0),
    description: str = Form(""),
    images: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user),
):
    valid_categories = ["Rough", "Geuda", "Cut and Polished", "Lot"]
    if category not in valid_categories:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid category. Must be one of {valid_categories}"
        )

    image_urls = []
    for image in images:
        if image.content_type not in ["image/jpeg", "image/png"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only JPEG and PNG images are allowed."
            )

        filename = f"{uuid.uuid4().hex}_{image.filename}"
        filepath = os.path.join(UPLOAD_DIRECTORY, filename)
        try:
            with open(filepath, "wb") as f:
                f.write(image.file.read())
            image_urls.append(filepath)
        except Exception as e:
            logger.error(f"Failed to save image: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to save image."
            )

    user = db.query(User).filter(User.user_id == current_user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found."
        )

    new_gem = Gem(
        user_id=current_user_id,
        name=name,
        category=category,
        sub_category=sub_category if category == "Geuda" else None,
        cost=cost,
        sell_price=sell_price,
        description=description,
        images=image_urls,
    )
    db.add(new_gem)
    db.commit()
    db.refresh(new_gem)

    return GemResponse(
        gem_id=new_gem.gem_id,
        name=new_gem.name,
        category=new_gem.category,
        sub_category=new_gem.sub_category,
        cost=new_gem.cost,
        sell_price=new_gem.sell_price,
        description=new_gem.description,
        images=new_gem.images,
        total_expenses=0.0,
        full_cost=new_gem.cost,
    )

#------ Get gem all details --------------#

@router.get("/gems/{gem_id}/details", response_model=GemResponse)
def get_gem_details(gem_id: int, db: Session = Depends(get_db)):
    gem = db.query(Gem).filter(Gem.gem_id == gem_id).first()
    if not gem:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Gem not found."
        )

    # Calculate total expenses
    expenses = db.query(Expense).filter(Expense.gem_id == gem_id).all()
    total_expenses = sum(expense.amount for expense in expenses)
    full_cost = gem.cost + total_expenses

    return GemResponse(
        gem_id=gem.gem_id,
        name=gem.name,
        category=gem.category,
        sub_category=gem.sub_category,
        cost=gem.cost,
        sell_price=gem.sell_price,
        description=gem.description,
        images=gem.images,
        total_expenses=total_expenses,
        full_cost=full_cost,
    )


#------ edit gem details --------------#

@router.put("/gems/{gem_id}/edit", response_model=dict)
def edit_gem(
    gem_id: int,
    name: str = Form(...),
    category: str = Form(...),
    sub_category: str = Form("Natural"),
    cost: float = Form(0.0),
    sell_price: float = Form(0.0),
    description: str = Form(""),
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user),
):
    gem_to_update = db.query(Gem).filter(Gem.gem_id == gem_id, Gem.user_id == current_user_id).first()
    if not gem_to_update:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Gem not found."
        )

    gem_to_update.name = name
    gem_to_update.category = category
    gem_to_update.sub_category = sub_category
    gem_to_update.cost = cost
    gem_to_update.sell_price = sell_price
    gem_to_update.description = description

    db.commit()
    db.refresh(gem_to_update)

    return {
        "message": "Gem updated successfully!",
        "gem_id": gem_to_update.gem_id,
    }



#------ edit gem images --------------#

@router.put("/gems/{gem_id}/images", response_model=dict)
def edit_gem_images(
    gem_id: int,
    images: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user),
):
    gem = db.query(Gem).filter(Gem.gem_id == gem_id, Gem.user_id == current_user_id).first()
    if not gem:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Gem not found."
        )

    # Delete old images
    for old_image_path in gem.images:
        if os.path.exists(old_image_path):
            try:
                os.remove(old_image_path)
            except Exception as e:
                logger.error(f"Failed to delete old image: {e}")

    # Save new images
    new_image_urls = []
    for image in images:
        if image.content_type not in ["image/jpeg", "image/png"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only JPEG and PNG images are allowed."
            )

        filename = f"{uuid.uuid4().hex}_{image.filename}"
        filepath = os.path.join(UPLOAD_DIRECTORY, filename)
        try:
            with open(filepath, "wb") as f:
                f.write(image.file.read())
            new_image_urls.append(filepath)
        except Exception as e:
            logger.error(f"Failed to save image: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to save image."
            )

    gem.images = new_image_urls
    db.commit()
    db.refresh(gem)

    return {"message": "Gem images updated successfully!", "images": new_image_urls}


#------ get user all gems --------------#
@router.get("/gems/my-gems", response_model=List[GemResponse])
def get_my_gems(
    db: Session = Depends(get_db),
    current_user_id: int = Depends(get_current_user),
):
    """
    Retrieve all gems belonging to the currently logged-in user.
    """
    # Query the database for gems belonging to the current user
    gems = db.query(Gem).filter(Gem.user_id == current_user_id).all()

    if not gems:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No gems found for the current user.",
        )

    # Convert the SQLAlchemy models to Pydantic models (GemResponse)
    gem_responses = []
    for gem in gems:
        expenses = db.query(Expense).filter(Expense.gem_id == gem.gem_id).all()
        total_expenses = sum(expense.amount for expense in expenses)
        full_cost = gem.cost + total_expenses

        gem_responses.append(
            GemResponse(
                gem_id=gem.gem_id,
                name=gem.name,
                category=gem.category,
                sub_category=gem.sub_category,
                cost=gem.cost,
                sell_price=gem.sell_price,
                description=gem.description,
                images=gem.images,
                total_expenses=total_expenses,
                full_cost=full_cost,
            )
        )

    return gem_responses