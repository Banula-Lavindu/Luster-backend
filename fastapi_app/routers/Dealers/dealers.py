from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File,Body
from ...database import get_mongo_collection, get_db
from ...models.mongo_modles import Dealer, DealerRequest  # MongoDB models
from ...models.models import User  # SQL User model
from fastapi_app.utils.jwt import decode_access_token 
from typing import List, Optional,Dict
from bson import ObjectId
from sqlalchemy.orm import Session
from datetime import datetime
from fuzzywuzzy import fuzz  # type: ignore # For name matching
from pydantic import BaseModel,EmailStr
import logging
import os
from fastapi_app.utils.profile_img_upload import save_uploaded_file
import asyncio


router = APIRouter(prefix="/dealers", tags=["dealers"])

class SystemAddRequest(BaseModel):
    user_id: str
    nickname: Optional[str] = None

class CustomResponse(BaseModel):
    message: str
    dealer_id: str
    request_id: str
    nickname: Optional[str] = None


# Pydantic model for dealer request
class ManualAddRequest(BaseModel):
    name: str
    email: Optional[str] = None
    country: Optional[str] = None
    phone: str
    address: Optional[str] = None
    ID: Optional[str] = None
    nickname: Optional[str] = None

# Pydantic model for API response
class ManualAddResponse(BaseModel):
    message: str
    dealer_id: str
    nickname: Optional[str] = None
    profile_image: Optional[str] = None


class DealerRequest(BaseModel):
    request_id: str  # Auto-generated MongoDB ObjectId
    my_id: int  # The user being added as dealer
    sender_id: int  # The user adding the dealer
    status: str = "pending"  # "pending", "approved", "rejected"
    timestamp: datetime  # Time request was created




UPLOAD_FOLDER = "uploads/dealer_images"


# Get the "dealers" collection
dealers_collection = get_mongo_collection("dealers")
dealer_requests_collection = get_mongo_collection("dealer_requests")

# Ensure unique indexes on the collections
dealers_collection.create_index([("user_id", 1), ("owner_id", 1)], unique=True)
dealer_requests_collection.create_index([("visitor_id", 1), ("user_id", 1)], unique=True)


@router.get("/check_user", response_model=dict)
async def check_user(
    phone_number: str,
    id_card_number: str,
    sql_db: Session = Depends(get_db)
):
    """
    Check if a user exists in the SQL database using their phone number or ID card number.
    Returns "available" if the user exists, otherwise "unavailable".
    """
    try:
        sql_user = sql_db.query(User).filter(
            (User.phone_number == phone_number) | (User.ID == id_card_number)
        ).first()

        if sql_user:
            return {"status": "available", "user_id": sql_user.user_id}
        else:
            return {"status": "unavailable"}

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error checking user: {str(e)}")
    


@router.post("/manual_add", response_model=ManualAddResponse)
async def manual_add_dealer(
    name: str,
    email: str,
    country: str,
    phone: str,
    address: str,
    ID: str,
    nickname: str,
    profile_image: Optional[UploadFile] = File(None),
    user_id: str = Depends(decode_access_token)
):
    """
    Manually add a dealer with optional profile image upload.
    """
    logging.info(f"Received manual add request: dealer_phone={phone}, owner_id={user_id}")

    try:
        # Convert user ID to integer
        owner_id = int(user_id)

        # Check if dealer already exists (phone + owner_id as unique key)
        existing_dealer = await dealers_collection.find_one({"phone": phone, "owner_id": owner_id})
        
        # Add debug logging
        logging.debug(f"Existing dealer check result: {existing_dealer}")
        
        if existing_dealer:
            logging.warning(f"Duplicate dealer found: phone={phone}, owner_id={owner_id}")
            raise HTTPException(status_code=400, detail="Dealer already exists")

        # Generate a unique dealer ID
        dealer_id = str(ObjectId())

        # Handle profile image upload
        image_filename = None
        if profile_image:
            # Save the uploaded file using the utility function
            file_path = await save_uploaded_file(
                file=profile_image,
                destination_folder=UPLOAD_FOLDER,
                user_id=dealer_id,  # Pass the user_id to include it in the filename
                file_naming_format="timestamp_userid",  # Use the new naming format
                max_width=500,
                max_height=500
            )
            image_filename = file_path

        # Create a new dealer document
        dealer = {
            "dealer_id": dealer_id,
            "user_id": ID,  # No linked SQL user
            "owner_id": owner_id,
            "name": name,
            "email": email,
            "country": country,
            "is_verified_id": False,
            "profile_image": image_filename,  # Set the profile image filename
            "phone": phone,
            "address": address,
            "ID": ID,
            "transactions": [],
            "created_withqr": False,
            "nickname": nickname,
        }

        # Insert into MongoDB
        dealers_collection.insert_one(dealer)

        logging.info(f"Dealer manually added successfully: dealer_id={dealer_id}, owner_id={owner_id}")

        return ManualAddResponse(
            message="Visitor added to your network. Request sent for approval.",
            dealer_id=dealer_id,
            nickname=nickname,
            profile_image=image_filename
        )

    except ValueError:
        logging.error(f"Invalid user ID format: user_id={user_id}")
        raise HTTPException(status_code=400, detail="Invalid user ID format. Must be an integer.")

    except HTTPException as e:
        logging.warning(f"HTTP Exception: {e.detail}")
        raise

    except Exception as e:
        logging.error(f"Unexpected error in manual_add_dealer: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")





@router.post("/system_add", response_model=CustomResponse)
async def system_add_dealer(
    request: SystemAddRequest,
    user_id_from_token: str = Depends(decode_access_token),
    sql_db: Session = Depends(get_db)
):
    """
    Adds a dealer automatically when the user exists in the SQL database.
    Prevents duplicate requests and ensures valid user IDs.
    """
    logging.info(f"Received system add request: user_id={request.user_id}, requester_id={user_id_from_token}")

    try:
        # Convert user IDs to integers
        user_id = int(request.user_id)
        requester_id = int(user_id_from_token)

        # First check: Prevent self-addition as dealer
        if requester_id == user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You cannot add yourself as a dealer"
            )

        # Check if dealer already exists
        existing_dealer = await dealers_collection.find_one({
            "user_id": user_id, 
            "owner_id": requester_id
        })
        
        if existing_dealer:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This user is already in your dealer network"
            )

        # Fetch user data from SQL
        sql_user = sql_db.query(User).filter(User.user_id == user_id).first()
        if not sql_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found in database"
            )

        # Generate IDs
        dealer_id = str(ObjectId())
        request_id = str(ObjectId())

        # Create dealer record
        new_dealer = {
            "dealer_id": dealer_id,
            "user_id": user_id,
            "owner_id": requester_id,
            "name": f"{sql_user.first_name} {sql_user.last_name}",
            "email": sql_user.email,
            "country": sql_user.country,
            "is_verified_id": sql_user.is_verified_id,
            "profile_image": sql_user.profile_image,
            "phone": sql_user.phone_number,
            "address": f"{sql_user.address}, {sql_user.city}, {sql_user.state}",
            "ID": sql_user.ID,
            "transactions": [],
            "created_withqr": True,
            "nickname": request.nickname,
            "created_at": datetime.utcnow()
        }

        # Insert dealer into MongoDB
        dealers_collection.insert_one(new_dealer)

        # Create and insert dealer request
        request_id = str(ObjectId())
        dealer_request = DealerRequest(
            request_id=request_id,
            my_id=int(user_id),
            sender_id=int(requester_id),
            status="pending",
            timestamp=datetime.utcnow()
        )
        await dealer_requests_collection.insert_one(dealer_request.dict())


        logging.info(f"Dealer added successfully: dealer_id={dealer_id}, request_id={request_id}")

        # Return the custom response
        return CustomResponse(
            message="Visitor added to your network. Request sent for approval.",
            dealer_id=dealer_id,
            request_id=request_id,
            nickname=request.nickname
        )

    except ValueError:
        logging.error(f"Invalid user ID format: user_id={request.user_id}, requester_id={user_id_from_token}")
        raise HTTPException(status_code=400, detail="Invalid user ID format. Must be an integer.")

    except HTTPException as e:
        logging.warning(f"HTTP Exception: {e.detail}")
        raise

    except Exception as e:
        logging.error(f"Unexpected error in system_add_dealer: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")
    


@router.get("/refresh_network")
async def refresh_network(
    user_id: str = Depends(decode_access_token),
    sql_db: Session = Depends(get_db)
):
    """Check manually added dealers and update details if a match is found in SQL DB.
    If a dealer is newly matched (user_id updated), send a request to add them to the network."""
    try:
        # Fetch manual dealers (created_withqr: False)
        manual_dealers = await dealers_collection.find(
            {"owner_id": int(user_id), "created_withqr": False}
        ).to_list(length=None)  # Convert cursor to list
        
        logging.debug(f"Found {len(manual_dealers)} manual dealers to check")
        
        updated_count = 0
        newly_matched_dealers = []  # Track dealers whose user_id was updated

        for dealer in manual_dealers:
            # Find a matching user in the SQL database by phone number or ID
            sql_user = sql_db.query(User).filter(
                (User.phone_number == dealer["phone"]) | (User.ID == dealer["ID"])
            ).first()

            if sql_user:
                # Calculate name match score
                name_match_score = fuzz.ratio(
                    dealer["name"].lower(),
                    f"{sql_user.first_name} {sql_user.last_name}".lower()
                )

                # If name match score is above 60, update dealer details
                if name_match_score > 60:
                    # Check if the user_id is being updated (i.e., it's a new match)
                    if dealer.get("user_id") != sql_user.user_id:
                        await dealers_collection.update_one(
                            {"dealer_id": dealer["dealer_id"]},
                            {"$set": {
                                "user_id": sql_user.user_id,
                                "name": f"{sql_user.first_name} {sql_user.last_name}",
                                "email": sql_user.email,
                                "country": sql_user.country,
                                "created_withqr": True,  # Set created_withqr to True
                                "is_verified_id": sql_user.is_verified_id,
                                "profile_image": sql_user.profile_image,
                                "phone": sql_user.phone_number,
                                "address": f"{sql_user.address}, {sql_user.city}, {sql_user.state}.",
                                "ID": sql_user.ID,
                                "transactions": []
                            }}
                        )
                        updated_count += 1
                        newly_matched_dealers.append(dealer["dealer_id"])

                        # Check if request already exists
                        existing_request = await dealer_requests_collection.find_one({
                            "my_id": sql_user.user_id,
                            "sender_id": int(user_id)
                        })

                        if not existing_request:
                            # Create and insert dealer request for newly matched dealer
                            request_id = str(ObjectId())
                            dealer_request = {
                                "request_id": request_id,
                                "my_id": sql_user.user_id,
                                "sender_id": int(user_id),
                                "status": "pending",
                                "timestamp": datetime.utcnow()
                            }
                            try:
                                await dealer_requests_collection.insert_one(dealer_request)
                                logging.info(f"Created dealer request for newly matched dealer: {dealer['dealer_id']}")
                            except Exception as e:
                                logging.error(f"Error creating dealer request: {str(e)}")
                                # Continue processing other dealers even if one request fails
                                continue

        return {
            "message": f"Network refreshed. {updated_count} dealers updated.",
            "newly_matched_dealers": newly_matched_dealers
        }

    except Exception as e:
        logging.error(f"Error in refresh_network: {str(e)}", exc_info=True)
        raise HTTPException(status_code=400, detail=f"Error refreshing network: {str(e)}")
    





# Get all dealers linked to the current user
@router.get("/my_dealers/")
async def get_user_dealers(user_id: str = Depends(decode_access_token)):
    """Get all dealers linked to the current user."""
    try:
        dealers = await dealers_collection.find(
            {"owner_id": int(user_id)}
        ).to_list(length=None)
        
        logging.debug(f"Found {len(dealers) if dealers else 0} dealers for user {user_id}")
        
        if not dealers:
            return {"message": "No dealers found"}
            
        for dealer in dealers:
            dealer["_id"] = str(dealer["_id"])
        return {"dealers": dealers}
        
    except Exception as e:
        logging.error(f"Error in get_user_dealers: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")







# Update Dealer
@router.put("/update/{dealer_id}", response_model=Dealer)
async def update_dealer(
    dealer_id: str,
    name: Optional[str] = None,
    email: Optional[str] = None,
    country: Optional[str] = None,
    phone: Optional[str] = None,
    address: Optional[str] = None,
    ID: Optional[str] = None,
    nickname: Optional[str] = None,
    profile_image: Optional[UploadFile] = File(None),
    user_id: str = Depends(decode_access_token)
):
    """
    Update a dealer's details. Only dealers with created_withqr=False can be updated.
    All fields are optional so you can update only the fields you need.
    """
    try:
        # Fetch the existing dealer
        existing_dealer = await dealers_collection.find_one(
            {"dealer_id": dealer_id, "owner_id": int(user_id)}
        )
        if not existing_dealer:
            raise HTTPException(status_code=404, detail="Dealer not found")
        
        # Only allow update if dealer was not created with a QR code
        if existing_dealer.get("created_withqr", True):
            raise HTTPException(status_code=403, detail="Cannot update dealer created with QR code")
        
        # Build the update data from provided form fields
        update_data = {}
        if name is not None:
            update_data["name"] = name
        if email is not None:
            update_data["email"] = email
        if country is not None:
            update_data["country"] = country
        if phone is not None:
            update_data["phone"] = phone
        if address is not None:
            update_data["address"] = address
        if ID is not None:
            update_data["ID"] = ID
        if nickname is not None:
            update_data["nickname"] = nickname

        if profile_image:
            # Save the uploaded file using the utility function
            file_path = await save_uploaded_file(
                file=profile_image,
                destination_folder=UPLOAD_FOLDER,
                user_id=dealer_id,  # Pass the user_id to include it in the filename
                file_naming_format="timestamp_userid",  # Use the new naming format
                max_width=500,
                max_height=500
            )
            update_data["profile_image"] = file_path

        # Update the dealer
        await dealers_collection.update_one(
            {"dealer_id": dealer_id},
            {"$set": update_data}
        )

        # Fetch and return updated dealer
        updated_dealer = await dealers_collection.find_one({"dealer_id": dealer_id})
        return updated_dealer

    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error updating dealer: {str(e)}")




# Delete Dealer
@router.delete("/{dealer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_dealer(
    dealer_id: str,
    user_id: str = Depends(decode_access_token)
):
    """Delete a dealer."""
    try:
        existing_dealer = dealers_collection.find_one({"dealer_id": dealer_id, "owner_id": int(user_id)})
        if not existing_dealer:
            raise HTTPException(status_code=404, detail="Dealer not found")

        dealers_collection.delete_one({"dealer_id": dealer_id})
        return {"message": "Dealer deleted successfully"}
    
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error deleting dealer: {str(e)}")

    

