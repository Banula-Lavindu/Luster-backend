from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from ..database import get_db
from ..models.models import User
from ..routers.auth import get_current_user
import shutil
import os
from typing import Optional
from datetime import datetime,date
from fastapi_app.utils.profile_img_upload import save_uploaded_file



router = APIRouter(prefix="/profile", tags=["Profile"])

# Pydantic models for input/output validation
class ProfileResponse(BaseModel):
    user_id: int
    first_name: str
    last_name: str
    ID: str
    email: EmailStr
    phone_number: str
    country: Optional[str] = None
    state: Optional[str] = None
    city: Optional[str] = None
    address: Optional[str] = None
    is_verified_id: bool
    last_login: Optional[datetime] = None
    date_joined: Optional[datetime] = None
    profile_image: Optional[str] = None
    dob: Optional[date] = None
    cover_image: Optional[str] = None

    class Config:
        from_attributes = True  # Enables ORM mode for Pydantic

class ProfileUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone_number: Optional[str] = None
    country: Optional[str] = None
    state: Optional[str] = None
    city: Optional[str] = None
    address: Optional[str] = None
    dob: Optional[str] = None

class BaseProfile(BaseModel):
    first_name: str | None
    last_name: str | None
    profile_image :str | None


#----------------- Endpoint to get the user's profile Base details--------------------------#
@router.get("/base", response_model=BaseProfile)
def get_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Retrieve the profile of the currently authenticated user.
    """
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User profile not found"
        )
    
    # Returning the profile details
    return BaseProfile(
        first_name=current_user.first_name,
        last_name=current_user.last_name,
        profile_image=current_user.profile_image,
    )


#----------------- Endpoint to get the user's profile Full details--------------------------#


@router.get("/detailed", response_model=ProfileResponse)
def get_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Retrieve the profile of the currently authenticated user.
    """
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User profile not found"
        )
    
    # Format date_joined, last_login, and dob as strings
    date_joined_str = current_user.date_joined.strftime("%Y-%m-%d %H:%M:%S") if current_user.date_joined else None
    last_login_str = current_user.last_login.strftime("%Y-%m-%d %H:%M:%S") if current_user.last_login else None
    dob_str = current_user.dob.strftime("%Y-%m-%d") if current_user.dob else None

    # Return the profile details
    return ProfileResponse(
        user_id=current_user.user_id,
        first_name=current_user.first_name,
        last_name=current_user.last_name,
        ID=current_user.ID,
        email=current_user.email,
        phone_number=current_user.phone_number,
        country=current_user.country,
        state=current_user.state,
        city=current_user.city,
        address=current_user.address,
        is_verified_id=current_user.is_verified,
        last_login=last_login_str,
        date_joined=date_joined_str,
        dob=dob_str,
        profile_image=current_user.profile_image,
        cover_image=current_user.cover_image,
    )



#----------------- Endpoint to update the user's profile--------------------------#

from datetime import datetime

@router.put("/update", response_model=ProfileResponse)
def update_profile(
    profile_data: ProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update the profile of the currently authenticated user."""
    user = db.query(User).filter(User.user_id == current_user.user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    # Convert 'dob' to a datetime.date object
    update_data = profile_data.dict(exclude_unset=True)
    
    if "dob" in update_data and update_data["dob"]:
        try:
            update_data["dob"] = datetime.strptime(update_data["dob"], "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD.")

    # Update fields dynamically
    for field, value in update_data.items():
        setattr(user, field, value)

    db.commit()
    db.refresh(user)

    # Convert date fields to strings
    return ProfileResponse(
        user_id=user.user_id,
        first_name=user.first_name,
        last_name=user.last_name,
        ID=user.ID,
        email=user.email,
        phone_number=user.phone_number,
        country=user.country,
        state=user.state,
        city=user.city,
        address=user.address,
        is_verified_id=user.is_verified_id,
        last_login=user.last_login.isoformat() if user.last_login else None,
        date_joined=user.date_joined.isoformat() if user.date_joined else None,
        profile_image=user.profile_image,
        dob=user.dob.isoformat() if user.dob else None,
        cover_image=user.cover_image,
    )




#----------------- Endpoint to update the user's profile image--------------------------#



# Endpoint to update the user's profile image
@router.put("/profile-image", response_model=ProfileResponse)
async def update_profile_image(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update the profile image of the currently authenticated user."""
    user = db.query(User).filter(User.user_id == current_user.user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    
    

    file_path = await save_uploaded_file(
        file=file,
        destination_folder="uploads/profile_images",  # Ensure this matches the function's parameter name
        user_id=str(current_user.user_id),  # Ensure user_id is passed as a string
        file_naming_format="timestamp_userid",  # Use the defined naming format
        max_width=500,
        max_height=500
        )

    # Update the user's profile image path in the database
    user.profile_image = file_path
    db.commit()
    db.refresh(user)

    return user



#----------------- Endpoint to update the user's cover image--------------------------#

@router.put("/cover-image", response_model=ProfileResponse)
async def update_cover_image(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update the cover image of the currently authenticated user."""
    user = db.query(User).filter(User.user_id == current_user.user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )

    file_path = await save_uploaded_file(
        file=file,
        destination_folder="uploads/cover_images",  # Ensure this matches the function's parameter name
        user_id=str(current_user.user_id),  # Ensure user_id is passed as a string
        file_naming_format="timestamp_userid",  # Use the defined naming format
        max_width=1000,
        max_height=500
        )

    # Update the user's cover image path in the database
    user.cover_image = file_path
    db.commit()
    db.refresh(user)

    return user
