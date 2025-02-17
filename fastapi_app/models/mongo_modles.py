from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List, Dict, Any
import uuid
from bson import ObjectId
from enum import Enum


class DealerRequest(BaseModel):
    request_id: str  # Auto-generated MongoDB ObjectId
    my_id: int  # QR owner (User 1)
    sender_id: int  # Scanning User (User 2)
    status: str = "pending"  # "pending", "approved", "rejected"
    timestamp: datetime  # Time request was created

class Dealer(BaseModel):
    """Model for managing approved dealers"""
    dealer_id: str  # Auto-generated
    user_id: int  # Linked to RDBMS User
    owner_id: int  # Linked to RDBMS User currunt user id
    name: str
    email: Optional[str] = None
    country: Optional[str] = None
    is_verified_id: bool = False
    profile_image: Optional[str] = None
    phone: str 
    address: Optional[str] = None
    ID: str
    transactions: list = []
    created_withqr: bool = True
    nickname: Optional[str] = None  # New field for nickname






# Notification Model
class Notification(BaseModel):
    notification_id: int
    user_id: int  # Linked to RDBMS User
    content: str
    is_read: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)


# Gem Lifetime Trace Model
class GemLifetimeTrace(BaseModel):
    gem_id: int
    user_id: int  # Use dealer_id as user_id
    name: str
    category: str
    sub_category: Optional[str] = None
    cost: float
    sell_price: Optional[float] = None
    description: Optional[str] = None
    images: List[str] = []
    transactions: List[int] = []
    expenses: List[int] = []
    ownership_history: List[Dict] = Field(default_factory=list)
    qr_history: List[Dict] = Field(default_factory=list)


    class Config:
        json_encoders = {
            ObjectId: str,
            datetime: lambda v: v.isoformat()
        }


# Task Model
class Task(BaseModel):
    task_id: str = Field(default_factory=lambda: str(ObjectId()))
    user_id: int
    title: str
    description: Optional[str] = None
    type: str
    priority: str
    category: str
    related_transaction_id: Optional[int] = None
    due_date: Optional[datetime] = None
    is_completed: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ChatMessage(BaseModel):
    user_id: int
    content: str
    message_type: str
    timestamp: datetime
    read_by: List[Dict] = []

class ChatRoom(BaseModel):
    transaction_id: str
    participants: List[int]
    messages: List[ChatMessage] = []
    created_at: datetime = datetime.utcnow()
    last_activity: datetime = datetime.utcnow()

# Deal Models
class DealStatus(str, Enum):
    PENDING = "pending"
    NEGOTIATING = "negotiating"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    COMPLETED = "completed"

class DealRequest(BaseModel):
    deal_id: str = Field(default_factory=lambda: str(ObjectId()))
    gem_id: int  # Reference to SQL Gem model
    seller_id: int  # Current user ID
    buyer_id: int  # Selected dealer's user_id
    initial_price: float
    current_price: float
    payment_method: str
    fulfillment_date: datetime
    status: DealStatus = DealStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_action_by: int  # User ID of who made the last action
    negotiation_history: List[Dict] = Field(default_factory=list)  # [{price, payment_method, date, proposed_by, timestamp}]
    notes: Optional[str] = None

    class Config:
        json_encoders = {
            ObjectId: str,
            datetime: lambda v: v.isoformat()
        }

class DealNotification(BaseModel):
    notification_id: str = Field(default_factory=lambda: str(ObjectId()))
    deal_id: str
    user_id: int  # Recipient
    type: str  # "new_deal", "counter_offer", "accepted", "rejected"
    content: str
    is_read: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    request_type: str  # "sell" or "buy"
    gem_name: Optional[str] = None
    gem_image: Optional[str] = None

    class Config:
        json_encoders = {
            ObjectId: str,
            datetime: lambda v: v.isoformat()
        }

# Non-User Gem Model
class NonUserGem(BaseModel):
    gem_id: int
    dealer_id: int
    name: str
    category: str
    sub_category: Optional[str] = None
    cost: float
    sell_price: Optional[float] = None
    description: Optional[str] = None
    images: List[str] = []
    sold_at: datetime = Field(default_factory=datetime.utcnow)

# Add after existing models

class CallStatus(str, Enum):
    PENDING = "pending"
    ONGOING = "ongoing"
    COMPLETED = "completed"
    MISSED = "missed"
    REJECTED = "rejected"

class Call(BaseModel):
    call_id: str = Field(default_factory=lambda: str(ObjectId()))
    caller_id: int
    receiver_id: int
    call_type: str  # "audio" or "video"
    status: CallStatus = CallStatus.PENDING
    start_time: datetime = Field(default_factory=datetime.utcnow)
    end_time: Optional[datetime] = None
    duration: Optional[int] = None  # in seconds
    is_dealer_call: bool = False
    call_quality: Optional[Dict] = None  # For storing call quality metrics
    
    class Config:
        json_encoders = {
            ObjectId: str,
            datetime: lambda v: v.isoformat()
        }