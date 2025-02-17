from fastapi import APIRouter, Depends, HTTPException, status
from pymongo import MongoClient
from bson import ObjectId
from datetime import datetime
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
import base64
import json
from ...database import get_mongo_collection, get_db
from ...models.mongo_modles import Dealer, DealerRequest  # MongoDB models
from ...models.models import User  # SQL User model
from fastapi_app.utils.jwt import decode_access_token  # JWT decoding function

router = APIRouter(prefix="/dealers_qr", tags=["dealers with qr"])

# Get the collections
dealers_collection = get_mongo_collection("dealers")
dealer_requests_collection = get_mongo_collection("dealer_requests")

# Ensure unique indexes on the collections
dealers_collection.create_index([("user_id", 1), ("owner_id", 1)], unique=True)
dealer_requests_collection.create_index([("visitor_id", 1), ("user_id", 1)], unique=True)

# Define the request body model
class ScanQRRequest(BaseModel):
    qr_code_data: str
    nickname: Optional[str] = None


@router.post("/scan_qr")
async def scan_qr(
    request: ScanQRRequest,
    user_id: str = Depends(decode_access_token),
    sql_db: Session = Depends(get_db)
):
    """Scan a visitor's QR code, add them as a dealer, and send a request."""
    try:
        # Decode QR code data
        decoded_data = json.loads(base64.urlsafe_b64decode(request.qr_code_data).decode())
        visitor_id = decoded_data.get("user_id")
        visitor_username = decoded_data.get("ID")

        if not visitor_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid QR code data: Missing user_id"
            )
        
        # First check: Prevent self-addition as dealer
        if int(visitor_id) == int(user_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You cannot add yourself as a dealer"
            )

        # Fetch visitor data from SQL
        sql_visitor = sql_db.query(User).filter(User.user_id == visitor_id).first()
        if not sql_visitor:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found in database"
            )

        # Check for existing request
        existing_request = await dealer_requests_collection.find_one(
            {"my_id": visitor_id, "sender_id": int(user_id)}
        )
        if existing_request:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Request already sent to this user"
            )

        # Check for existing dealer
        existing_dealer = await dealers_collection.find_one(
            {"user_id": visitor_id, "owner_id": int(user_id)}
        )
        if existing_dealer:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This user is already in your dealer network"
            )

        # Create and insert dealer
        dealer_id = str(ObjectId())
        dealer = Dealer(
            dealer_id=dealer_id,
            user_id=visitor_id,
            owner_id=int(user_id),
            name=f"{sql_visitor.first_name} {sql_visitor.last_name}",
            email=sql_visitor.email,
            country=sql_visitor.country,
            is_verified_id=sql_visitor.is_verified_id,
            profile_image=None,
            phone=sql_visitor.phone_number,
            address=f"{sql_visitor.address}, {sql_visitor.city}, {sql_visitor.state}.",
            ID=sql_visitor.ID,
            transactions=[],
            created_withqr=True,
            nickname=request.nickname
        )
        await dealers_collection.insert_one(dealer.dict())

        # Create and insert dealer request
        request_id = str(ObjectId())
        dealer_request = DealerRequest(
            request_id=request_id,
            my_id=visitor_id,
            sender_id=int(user_id),
            status="pending",
            timestamp=datetime.utcnow()
        )
        await dealer_requests_collection.insert_one(dealer_request.dict())

        return {
            "message": "Visitor added to your network. Request sent for approval.",
            "dealer_id": dealer_id,
            "request_id": request_id,
            "nickname": request.nickname
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid QR code: {str(e)}")


@router.get("/requests", response_model=List[DealerRequest])
async def get_pending_requests(user_id: str = Depends(decode_access_token)):
    """Fetch all pending dealer requests for the current user."""
    # Convert cursor to list asynchronously
    pending_requests = await dealer_requests_collection.find(
        {"my_id": int(user_id), "status": "pending"}
    ).to_list(length=None)
    
    # Convert ObjectId to string
    for request in pending_requests:
        request["_id"] = str(request["_id"])
    return pending_requests



@router.post("/requests/{request_id}/approve/")
async def approve_request(
    request_id: str,
    user_id: str = Depends(decode_access_token),
    sql_db: Session = Depends(get_db)
):
    """Approve a dealer request and add the requester as a dealer."""
    try:
        ObjectId(request_id)  # Validate request_id format
    except:
        raise HTTPException(status_code=400, detail="Invalid request ID format")

    request = await dealer_requests_collection.find_one({
        "request_id": request_id,
        "my_id": int(user_id),
        "status": "pending"
    })
    
    if not request:
        raise HTTPException(status_code=404, detail="Request not found or already processed")

    requester_id = request["sender_id"]
    sql_requester = sql_db.query(User).filter(User.user_id == requester_id).first()
    if not sql_requester:
        raise HTTPException(status_code=404, detail="Requester not found in database")

    if await dealers_collection.find_one({"user_id": requester_id, "owner_id": int(user_id)}):
        raise HTTPException(status_code=400, detail="Dealer already exists")

    dealer_id = str(ObjectId())
    dealer_data = {
        "_id": ObjectId(dealer_id),
        "dealer_id": dealer_id,
        "user_id": requester_id,
        "owner_id": int(user_id),
        "name": f"{sql_requester.first_name} {sql_requester.last_name}",
        "email": sql_requester.email,
        "country": sql_requester.country,
        "is_verified_id": sql_requester.is_verified_id,
        "profile_image": sql_requester.profile_image,
        "phone": sql_requester.phone_number,
        "address": f"{sql_requester.address}, {sql_requester.city}, {sql_requester.state}.",
        "ID": sql_requester.ID,
        "transactions": [],
        "created_withqr": False,
        "created_at": datetime.utcnow()
    }
    await dealers_collection.insert_one(dealer_data)

    await dealer_requests_collection.update_one(
        {"request_id": request_id, "status": "pending"},  # Ensure only pending requests are updated
        {"$set": {"status": "approved"}})

    return {"message": "Request approved successfully. Requester added to your network.", "dealer_id": dealer_id}




@router.post("/requests/{request_id}/reject/")
async def reject_request(request_id: str, user_id: str = Depends(decode_access_token)):
    """Reject a dealer request."""
    
    # Query using request_id (since it's stored as a string, not an _id)
    request = await dealer_requests_collection.find_one({
        "request_id": request_id,
        "my_id": int(user_id),
        "status": "pending"
    })

    if not request:
        raise HTTPException(status_code=404, detail="Request not found or already processed")

    # Correct update operation
    await dealer_requests_collection.update_one(
        {"request_id": request_id, "my_id": int(user_id)},  
        {"$set": {"status": "rejected"}}  
    )

    return {"message": "Request rejected successfully"}




@router.get("/update_network_withqr")
async def update_network_withqr(
    user_id: str = Depends(decode_access_token),  # Extract user_id from the token
    sql_db: Session = Depends(get_db)
):
    """Update dealers with created_withqr: True using their user_id to fetch details from SQL DB."""
    try:
        # Fetch dealers with created_withqr: True
        qr_dealers = await dealers_collection.find({"owner_id": int(user_id), "created_withqr": True}).to_list(length=None)
        updated_count = 0

        for dealer in qr_dealers:
            # Find the corresponding user in the SQL database using user_id
            sql_requester = sql_db.query(User).filter(User.user_id == dealer["user_id"]).first()

            if sql_requester:
                # Update dealer details with the user's information
                await dealers_collection.update_one(
                    {"dealer_id": dealer["dealer_id"]},
                    {"$set": {
                        "name": f"{sql_requester.first_name} {sql_requester.last_name}",
                        "email": sql_requester.email,
                        "country": sql_requester.country,
                        "is_verified_id": sql_requester.is_verified_id,
                        "profile_image": sql_requester.profile_image,
                        "phone": sql_requester.phone_number,
                        "address": f"{sql_requester.address}, {sql_requester.city}, {sql_requester.state}.",
                        "ID": sql_requester.ID,
                        "transactions": []  # Reset transactions or keep as per your logic
                    }}
                )
                updated_count += 1

        return {"message": f"Network updated. {updated_count} dealers with created_withqr: True updated."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error updating network: {str(e)}")