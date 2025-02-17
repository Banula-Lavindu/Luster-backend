#-------------Chat_modle.py----------------#
from bson import ObjectId
from ..database import mongo_db  # Import the `mongo_db` object from db.py
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List, Dict, Union, Any


# Chat Models
class ChatMessage(BaseModel):
    """Model for individual chat messages"""
    message_id: str = Field(default_factory=lambda: str(ObjectId()))
    chat_id: str
    sender_id: Union[int, str]  # Can be user_id or dealer_id
    sender_type: str  # "user" or "dealer"
    content: str
    message_type: str = "text"  # "text", "image", "file", "gem_share", "status", "deleted"
    gem_id: Optional[int] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    read_by: List[Dict[str, Any]] = []  # List of {id: int/str, type: str, timestamp: datetime}
    delivered_to: List[Dict[str, Any]] = []  # List of {id: int/str, type: str, timestamp: datetime}
    attachment: Optional[Dict] = None
    is_deleted: bool = False
    deleted_for: List[Dict[str, Any]] = []  # List of users who cleared this message
    deleted_at: Optional[datetime] = None
    deleted_by: Optional[Dict] = None  # {id: int/str, type: str}
    reply_to: Optional[Dict] = None  # {message_id: str, content: str, sender_id: int}
    reactions: Dict[str, List[Dict]] = Field(default_factory=dict)  # {emoji: [{user_id: int, timestamp: datetime}]}
    is_edited: bool = False
    last_edited_at: Optional[datetime] = None
    edit_history: List[Dict] = Field(default_factory=list)  # [{previous_content, edited_at, reason}]

    class Config:
        arbitrary_types_allowed = True
        json_encoders = {
            ObjectId: str,
            datetime: lambda v: v.isoformat()
        }

    def dict(self, *args, **kwargs):
        d = super().dict(*args, **kwargs)
        # Convert ObjectId to string if present
        if isinstance(d.get('chat_id'), ObjectId):
            d['chat_id'] = str(d['chat_id'])
        return d

class ChatRoom(BaseModel):
    """Model for chat rooms/conversations"""
    chat_id: str = Field(default_factory=lambda: str(ObjectId()))
    chat_type: str  # "private_chat", "dealer_chat", "group_chat"
    creator_id: Union[int, str]
    creator_type: str  # "user" or "dealer"
    participants: List[Dict[str, Any]] = []  # List of {id: int/str, type: str, role: str}
    dealer_id: Optional[str] = None  # For dealer chats
    title: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_message: Optional[Dict] = None
    last_activity: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = True
    unread_counts: Dict[str, int] = Field(default_factory=dict)  # Track unread messages per user
    settings: Dict = Field(default_factory=lambda: {
        "muted_by": [],
        "pinned_by": [],
        "allow_gem_sharing": True,
        "allow_status_updates": True,
        "group_admins": [],  # List of {id: int, type: str}
        "allow_member_invites": False,  # Can members create invites
        "allow_member_adds": False,  # Can members add others
        "only_admins_message": False,  # Only admins can send messages
        "clear_history": {}  # Track when each user cleared their chat
    })
    group_image: Optional[str] = None

class ChatParticipant(BaseModel):
    """Model for managing chat participants"""
    user_id: int  # Linked to RDBMS User
    chat_id: str  # Reference to ChatRoom
    role: str = "member"  # "admin", "member"
    joined_at: datetime = Field(default_factory=datetime.utcnow)
    nickname: Optional[str] = None
    last_read_at: Optional[datetime] = None
    is_muted: bool = False
    muted_until: Optional[datetime] = None
    notification_settings: Dict = Field(default_factory=lambda: {
        "mute_notifications": False,
        "show_previews": True
    })

class ChatStatus(BaseModel):
    """Model for status updates"""
    status_id: str = Field(default_factory=lambda: str(ObjectId()))
    creator_id: Union[int, str]
    creator_type: str
    content: str
    media_url: Optional[str] = None
    media_type: str = "image"
    visible_to: List[Dict] = []  # List of {id: int, type: str}
    viewed_by: List[Dict] = []  # List of {id: int, type: str, timestamp: datetime}
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime
    is_active: bool = True

class ChatAttachment(BaseModel):
    """Model for chat attachments/files"""
    chat_id: str
    message_id: Optional[str] = None
    uploader_id: Union[int, str]
    uploader_type: str = "user"  # Default to user
    file_name: str
    file_type: str = "file"  # Default to file
    file_path: Optional[str] = None
    file_size: int = 0
    mime_type: str
    file_url: Optional[str] = None
    content_type: str
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)
    status: str = "pending"  # pending, uploading, completed, failed
