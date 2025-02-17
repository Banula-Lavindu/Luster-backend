from fastapi import APIRouter, HTTPException, status, Depends, UploadFile, File, Query, Header
from pydantic import BaseModel
from typing import List, Optional, Dict, Union
from datetime import datetime, timedelta
from fastapi_app.models.chat_models import ChatMessage, ChatRoom, ChatStatus, ChatAttachment
from fastapi_app.routers.auth import get_current_user
from fastapi_app.routers.chat.chat_service import ChatService
from fastapi_app.utils.file_handler import FileHandler
from fastapi_app.models.models import User
from fastapi_app.config import settings as app_settings
from fastapi.encoders import jsonable_encoder
from bson import ObjectId
from fastapi_app.utils.websocket_manager import ConnectionManager
from fastapi_app.database import get_db
from fastapi_app.config import settings  # Update import
import pymongo
import pymongo.errors
from fastapi.middleware.cors import CORSMiddleware
from starlette.websockets import WebSocketDisconnect
from fastapi_app.utils.token_handler import create_access_token


router = APIRouter(prefix="/chats", tags=["Chats"])
chat_service = ChatService()
file_handler = FileHandler()
manager = ConnectionManager()  # Create instance of ConnectionManager

# Add dependency function
def get_chat_service():
    return ChatService()

# Pydantic models
class MessageRequest(BaseModel):
    content: str
    message_type: str = "text"  # "text", "gem", "attachment"
    attachment: Optional[Dict] = None
    gem_id: Optional[int] = None
    gem_details: Optional[Dict] = None  # For sharing gem information

class ChatResponse(BaseModel):
    chat_id: str
    chat_type: str
    participants: List[Dict]
    last_message: Optional[Dict]
    unread_count: int
    created_at: datetime
    last_activity: datetime
    title: Optional[str] = None
    group_image: Optional[str] = None
    other_user: Optional[Dict] = None  # Added for dealer chats

class ChatDetailResponse(BaseModel):
    chat_id: str
    chat_type: str
    participants: List[Dict]
    last_message: Optional[Dict] = None
    created_at: datetime
    last_activity: datetime
    title: Optional[str] = None
    group_image: Optional[str] = None
    dealer_id: Optional[str] = None

class MessageResponse(BaseModel):
    message_id: str
    chat_id: str
    sender_id: Union[int, str]
    sender_type: str
    content: str
    message_type: str
    timestamp: datetime
    read_by: List[Dict] = []
    attachment: Optional[Dict] = None
    is_deleted: bool = False
    gem_id: Optional[int] = None

class UserChatResponse(BaseModel):
    chat_id: str
    chat_type: str
    participants: List[Dict]
    last_message: Optional[Dict] = None
    unread_count: int = 0
    created_at: datetime
    last_activity: datetime
    title: Optional[str] = None
    group_image: Optional[str] = None

class CreateGroupRequest(BaseModel):
    title: str
    participant_ids: List[int]
    group_image: Optional[str] = None

class StatusCreateRequest(BaseModel):
    content: str
    media_url: Optional[str] = None
    media_type: Optional[str] = "image"
    duration: int = 24

class UpdateGroupAdminsRequest(BaseModel):
    admin_ids: List[int]

class GroupInviteRequest(BaseModel):
    expires_in_hours: Optional[int] = 24

class JoinGroupRequest(BaseModel):
    invite_code: str

class UpdateGroupSettingsRequest(BaseModel):
    allow_member_invites: Optional[bool] = None
    allow_member_adds: Optional[bool] = None
    only_admins_message: Optional[bool] = None
    allow_admin_invites: Optional[bool] = True
    allow_user_invites: Optional[bool] = False

class ChatListResponse(BaseModel):
    chat_id: str
    chat_type: str
    title: str
    last_message: Optional[dict]
    unread_count: int
    last_activity: datetime
    group_image: Optional[str]
    participants: List[dict]
    is_pinned: bool = False
    is_muted: bool = False

class AddMembersRequest(BaseModel):
    member_ids: List[int]

class ReplyMessageRequest(BaseModel):
    content: str
    message_type: str = "text"
    reply_to_message_id: str
    attachment: Optional[Dict] = None
    gem_id: Optional[int] = None

class MessageReactionRequest(BaseModel):
    emoji: str

# Add new request models
class RemoveMemberRequest(BaseModel):
    user_id: int
    reason: Optional[str] = None

class LeaveGroupRequest(BaseModel):
    reason: Optional[str] = None

class BlockUserRequest(BaseModel):
    user_id: int
    reason: Optional[str] = None

class ReportUserRequest(BaseModel):
    user_id: int
    reason: str
    report_type: str  # "spam", "abuse", "inappropriate", "other"
    description: Optional[str] = None

class EditMessageRequest(BaseModel):
    content: str
    edited_reason: Optional[str] = None

# Add new request model
class UnblockUserRequest(BaseModel):
    reason: Optional[str] = None


class GemShareDetails(BaseModel):
    gem_id: int
    name: str
    category: str
    cost: float
    sell_price: float
    total_expenses: float
    full_cost: float
    images: List[str]
    description: Optional[str] = None


#======================================== Chat creation and management =====================================================================

#=================== dealer chat =================working =================
@router.post("/create/dealer/{dealer_id}")
async def create_dealer_chat(
    dealer_id: str, 
    current_user: User = Depends(get_current_user)
):
    """Create or get existing dealer chat"""
    try:
        # Check if dealer exists
        dealer = await chat_service.get_dealer_info(dealer_id)
        if not dealer:
            raise HTTPException(status_code=404, detail="Dealer not found")

        # Check if dealer is in user's network
        is_dealer_in_network = await chat_service.is_dealer_in_user_network(dealer_id, current_user.user_id)
        if not is_dealer_in_network:
            raise HTTPException(status_code=403, detail="Dealer not in your network")

        # Debug prints
        print(f"Current user ID: {current_user.user_id}")
        print(f"Dealer user ID: {dealer['user_id']}")

        # Check for existing chat
        existing_chat_id = await chat_service.get_existing_dealer_chat(
            user_id=current_user.user_id,
            dealer_id=dealer["user_id"]
        )

        if existing_chat_id:
            print(f"Found existing chat: {existing_chat_id}")  # Debug print
            return {
                "chat_id": existing_chat_id,
                "message": "Existing chat found",
                "is_new": False
            }

        print("No existing chat found, creating new chat")  # Debug print

        # Create new chat if none exists
        chat = ChatRoom(
            chat_type="dealer_chat",
            creator_id=current_user.user_id,
            creator_type="user",
            participants=[
                {"id": current_user.user_id, "type": "user"},
                {"id": dealer["user_id"], "type": "user"}
            ],
            dealer_id=dealer_id,
            title=f"Chat with {dealer.get('name', 'Dealer')}",
            is_active=True
        )
        chat_id = await chat_service.create_chat(chat)
        
        return {
            "chat_id": chat_id,
            "message": "New chat created successfully",
            "is_new": True
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"Error creating dealer chat: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error creating dealer chat: {str(e)}"
        )

# ============================ Group chat ============================Working

@router.post("/create/group")
async def create_group_chat(request: CreateGroupRequest, current_user: User = Depends(get_current_user)):
    """Create a new group chat"""
    try:
        # Add creator as admin with full permissions
        participants = [{
            "id": current_user.user_id,
            "type": "user",
            "role": "admin",
            "joined_at": datetime.utcnow(),
            "permissions": ["invite", "add_members", "manage_settings", "remove_members"]
        }]
        
        # Add other participants as regular members
        for user_id in request.participant_ids:
            is_dealer = await chat_service.is_user_in_dealer_network(current_user.user_id, user_id)
            if not is_dealer:
                raise HTTPException(status_code=400, detail=f"User {user_id} not in your dealer network")
            participants.append({
                "id": user_id,
                "type": "dealer",
                "role": "member",
                "joined_at": datetime.utcnow(),
                "permissions": []  # Regular members have no special permissions
            })

        # Set default group image if none provided
        group_image = request.group_image or "/uploads/group_images/default_group.png"

        # Create chat with default settings
        chat = ChatRoom(
            chat_type="group_chat",
            creator_id=current_user.user_id,
            creator_type="user",
            participants=participants,
            title=request.title,
            group_image=group_image,
            settings={
                "muted_by": [],
                "pinned_by": [],
                "allow_gem_sharing": True,
                "allow_status_updates": True,
                "allow_member_invites": False,
                "allow_member_adds": False,
                "only_admins_message": False,
                "allow_admin_invites": True,
                "allow_user_invites": False,
                "group_admins": [{
                    "id": current_user.user_id,
                    "type": "user",
                    "role": "admin",
                    "permissions": [
                        "invite",
                        "add_members", 
                        "remove_members",
                        "manage_settings",
                        "manage_admins"
                    ]
                }]
            }
        )
        
        chat_id = await chat_service.create_chat(chat)
        return {
            "chat_id": chat_id,
            "message": "Group created successfully",
            "settings": chat.settings,
            "creator_permissions": {
                "is_admin": True,
                "can_invite": True,
                "can_add_members": True,
                "can_manage_settings": True,
                "can_remove_members": True
            }
        }
        
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error creating group: {str(e)}"
        )





# ============================================================ Message handling ============================================================


## ====================================== Message send =====================================Work
@router.post("/{chat_id}/messages")
async def send_message(
    chat_id: str,
    request: MessageRequest,
    current_user: User = Depends(get_current_user)
):
    """Send a new message"""
    try:
        sender_type = await chat_service.get_participant_type(chat_id, current_user.user_id)
        
        message = ChatMessage(
            chat_id=chat_id,
            sender_id=current_user.user_id,
            sender_type=sender_type,
            content=request.content,
            message_type=request.message_type,
            gem_id=request.gem_id,
            attachment=request.attachment
        )
        
        result = await chat_service.add_message(message)
        
        # Increment unread count for other participants
        await chat_service.increment_unread_count(
            chat_id=chat_id,
            sender_id=current_user.user_id,
            sender_type=sender_type
        )
        
        # Notify via WebSocket
        await manager.broadcast_to_chat(
            chat_id,
            {
                "type": "new_message",
                "message": jsonable_encoder(result)
            },
            exclude_connection=f"user_{current_user.user_id}"
        )
        
        return jsonable_encoder(result)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error sending message: {str(e)}"
        )


# ======================================= Message delete ======================================Work
@router.delete("/messages/{message_id}")
async def delete_message(
    message_id: str,
    delete_for_everyone: bool = False,
    current_user: User = Depends(get_current_user)
):
    """Delete a message"""
    try:
        # First try to get message
        message = await chat_service.get_message(message_id)
        if not message:
            raise HTTPException(status_code=404, detail="Message not found")

        # Get chat details
        chat = await chat_service.get_chat_details(message["chat_id"])
        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found")

        # Check if user is a participant
        is_participant = any(
            str(p["id"]) == str(current_user.user_id)
            for p in chat.get("participants", [])
        )
        if not is_participant:
            raise HTTPException(
                status_code=403,
                detail="You are not a participant in this chat"
            )

        # Check if the message is from the current user
        is_sender = str(message.get("sender_id")) == str(current_user.user_id)

        # Handle delete permissions based on chat type
        if chat["chat_type"] == "dealer_chat":
            if delete_for_everyone and not is_sender:
                raise HTTPException(
                    status_code=403,
                    detail="Only the sender can delete messages for everyone in dealer chats"
                )
        else:  # For group chats or other types
            if delete_for_everyone and not is_sender:
                raise HTTPException(
                    status_code=403,
                    detail="Only the sender can delete messages for everyone"
                )

        # Get user's role
        user_type = await chat_service.get_participant_type(
            message["chat_id"],
            current_user.user_id
        )

        # Perform deletion
        success = await chat_service.delete_message(
            message_id=message["message_id"],  # Use message_id from found message
            user_id=current_user.user_id,
            user_type=user_type,
            delete_for_everyone=delete_for_everyone
        )

        if not success:
            raise HTTPException(
                status_code=400,
                detail="Failed to delete message"
            )

        # Get updated message for WebSocket notification
        updated_message = await chat_service.get_message(message["message_id"])

        # Notify via WebSocket
        await manager.broadcast_to_chat(
            message["chat_id"],
            {
                "type": "message_deleted",
                "message_id": message["message_id"],
                "chat_id": message["chat_id"],
                "deleted_for_everyone": delete_for_everyone,
                "deleted_by": {
                    "user_id": current_user.user_id,
                    "user_type": user_type
                },
                "updated_message": jsonable_encoder(updated_message)
            },
            exclude_connection=f"user_{current_user.user_id}"
        )

        return {
            "message": "Message deleted successfully",
            "deleted_for_everyone": delete_for_everyone
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"Error deleting message: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error deleting message: {str(e)}"
        )



# ========================================= Mark all messages in a chat as read =====================================Work
@router.post("/{chat_id}/read")
async def mark_chat_as_read(
    chat_id: str,
    current_user: User = Depends(get_current_user)
):
    """Mark all messages in a chat as read"""
    try:
        user_type = await chat_service.get_participant_type(chat_id, current_user.user_id)
        
        # Mark messages as read
        await chat_service.mark_as_read(
            chat_id=chat_id,
            user_id=current_user.user_id,
            user_type=user_type
        )
        
        # Reset unread count for this user
        participant_id = f"{user_type}_{current_user.user_id}"
        await chat_service.chat_collection.update_one(
            {"$or": [
                {"_id": ObjectId(chat_id)},
                {"chat_id": chat_id}
            ]},
            {
                "$set": {
                    f"unread_counts.{participant_id}": 0
                }
            }
        )
        
        return {"message": "Messages marked as read"}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error marking messages as read: {str(e)}"
        )



# =============================================== Message attachment ====================================work
@router.post("/{chat_id}/attachment")
async def upload_attachment(
    chat_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user)
):
    """Upload a file attachment"""
    try:
        # Check if user is participant in chat
        chat = await chat_service.get_chat_details(chat_id)
        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found")
        
        is_participant = any(
            str(p["id"]) == str(current_user.user_id)
            for p in chat.get("participants", [])
        )
        if not is_participant:
            raise HTTPException(
                status_code=403,
                detail="You are not a participant in this chat"
            )

        # Create attachment record
        attachment = ChatAttachment(
            chat_id=chat_id,
            uploader_id=current_user.user_id,
            file_name=file.filename,
            mime_type=file.content_type,
            content_type=file.content_type,
            file_size=0  # Will be updated after save
        )
        
        # Save attachment and get details
        attachment_details = await chat_service.add_attachment(attachment, file)
        
        if not attachment_details:
            raise HTTPException(
                status_code=500,
                detail="Failed to upload attachment"
            )

        # Create message with attachment
        sender_type = await chat_service.get_participant_type(chat_id, current_user.user_id)
        message = ChatMessage(
            chat_id=chat_id,
            sender_id=current_user.user_id,
            sender_type=sender_type,
            content=f"Sent an attachment: {file.filename}",
            message_type="file",
            attachment=attachment_details
        )
        
        result = await chat_service.add_message(message)
        
        # Notify via WebSocket
        await manager.broadcast_to_chat(
            chat_id,
            {
                "type": "new_message",
                "message": jsonable_encoder(result)
            },
            exclude_connection=f"user_{current_user.user_id}"
        )
        
        return jsonable_encoder(result)

    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"Error uploading attachment: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error uploading attachment: {str(e)}"
        )






# =================================================== chat access and details =================================================================

# ============================== chat list ==========================================Work

@router.get("/list", response_model=List[ChatResponse])
async def get_chats(current_user: User = Depends(get_current_user)):
    """Get all chats for the current user"""
    try:
        print(f"Getting chats for user: {current_user.user_id}")
        
        # Get database session
        db = next(get_db())
        
        try:
            chats = await chat_service.get_user_chats(
                user_id=current_user.user_id,
                user_type="user",
                db=db  # Pass the db session
            )
            
            print(f"Found {len(chats)} chats")
            
            # Verify other_user data
            for chat in chats:
                if chat.get("other_user") is None:
                    print(f"Warning: other_user is None for chat {chat['chat_id']}")
            
            return chats
            
        finally:
            db.close()
        
    except Exception as e:
        print(f"Error in get_chats endpoint: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error getting chats: {str(e)}"
        )


# ============================================ Chat room details =====================================Work
@router.get("/{chat_id}", response_model=ChatResponse)
async def get_chat_details(
    chat_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get details of a specific chat"""
    try:
        db = next(get_db())
        try:
            chat = await chat_service.get_chat(chat_id)
            if not chat:
                raise HTTPException(status_code=404, detail="Chat not found")
            
            # Get other participant's details
            other_participant = next(
                (p for p in chat["participants"] 
                 if str(p["id"]) != str(current_user.user_id)),
                None
            )
            
            if other_participant:
                other_user = db.query(User).filter(
                    User.user_id == int(other_participant["id"])
                ).first()
                
                if other_user:
                    chat["other_user"] = {
                        "name": f"{other_user.first_name} {other_user.last_name}",
                        "profile_image": other_user.profile_image or "uploads/profile_images/man.png",
                        "user_id": other_user.user_id,
                        "email": other_user.email,
                        "phone": other_user.phone_number
                    }
                    chat["title"] = f"Chat with {other_user.first_name} {other_user.last_name}"
            
            # Calculate unread count
            unread_count = await chat_service.get_unread_count(
                chat_id=chat_id,
                user_id=current_user.user_id
            )
            chat["unread_count"] = unread_count
            
            return chat
            
        finally:
            db.close()
            
    except Exception as e:
        print(f"Error getting chat details: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error getting chat details: {str(e)}"
        )

#================================= messeges of chat =====================================Working
@router.get("/{chat_id}/messages")
async def get_chat_messages(
    chat_id: str,
    limit: int = Query(50, le=100),
    before_id: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """Get messages for a chat"""
    try:
        # Debug print
        print(f"Fetching messages for chat_id: {chat_id}")
        
        # Verify chat exists and user is participant
        chat = await chat_service.get_chat(chat_id)
        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found")
            
        # Debug print
        print(f"Found chat: {chat}")
            
        is_participant = any(
            str(p["id"]) == str(current_user.user_id) 
            for p in chat.get("participants", [])
        )
        if not is_participant:
            raise HTTPException(
                status_code=403,
                detail="You are not a participant in this chat"
            )

        # Get participant type
        participant_type = await chat_service.get_participant_type(
            chat_id,
            current_user.user_id
        )
        
        # Debug print
        print(f"User type: {participant_type}")

        # Get messages
        messages = await chat_service.get_chat_messages(
            chat_id=chat_id,
            user_id=current_user.user_id,
            user_type=participant_type,
            limit=limit,
            before_id=before_id
        )
        
        # Debug print
        print(f"Retrieved {len(messages)} messages")

        # Mark messages as delivered
        await chat_service.mark_messages_as_delivered(
            chat_id=chat_id,
            user_id=current_user.user_id,
            user_type=participant_type
        )
        
        return jsonable_encoder(messages)
        
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"Error getting messages: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Error getting messages: {str(e)}"
        )

#=============================== Get user chats =============================working
@router.get("/user/chats", response_model=List[UserChatResponse])
async def get_user_chats(current_user: User = Depends(get_current_user), limit: int = Query(20, ge=1, le=50), skip: int = Query(0, ge=0)):
    try:
        chats = await chat_service.get_user_chats_paginated(user_id=current_user.user_id, user_type="user", limit=limit, skip=skip)
        return [
            UserChatResponse(
                chat_id=chat["_id"],
                chat_type=chat["chat_type"],
                participants=chat["participants"],
                last_message=chat.get("last_message"),
                unread_count=chat.get("unread_count", 0),
                created_at=chat["created_at"],
                last_activity=chat["last_activity"],
                title=chat.get("title"),
                group_image=chat.get("group_image")
            ) for chat in chats
        ]
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to fetch user chats: {str(e)}")








#========================================================= Group management ========================================================

#=========================== chat admins ============================Works
@router.put("/group/{chat_id}/admins")
async def update_group_admins(
    chat_id: str, 
    request: UpdateGroupAdminsRequest, 
    current_user: User = Depends(get_current_user)
):
    """Add new admins to the group while preserving existing admins"""
    try:
        # Check if chat exists first
        chat = await chat_service.get_chat(chat_id)
        if not chat:
            raise HTTPException(
                status_code=404,
                detail="Chat not found"
            )

        # Verify it's a group chat
        if chat.get("chat_type") != "group_chat":
            raise HTTPException(
                status_code=400,
                detail="This operation is only valid for group chats"
            )

        # Check if user is admin
        is_admin = await chat_service.is_group_admin(chat_id, current_user.user_id)
        if not is_admin:
            raise HTTPException(
                status_code=403,
                detail="Only group admins can update admin list"
            )

        # Validate admin_ids
        if not request.admin_ids:
            raise HTTPException(
                status_code=400,
                detail="Admin IDs list cannot be empty"
            )

        # Validate that all admin_ids exist in the participants list
        participants = {str(p["id"]) for p in chat.get("participants", [])}
        invalid_admins = [
            admin_id for admin_id in request.admin_ids 
            if str(admin_id) not in participants
        ]
        if invalid_admins:
            raise HTTPException(
                status_code=400,
                detail=f"Users {invalid_admins} are not participants in this chat"
            )

        # Ensure current user remains an admin
        if current_user.user_id not in request.admin_ids:
            request.admin_ids.append(current_user.user_id)

        try:
            # Update admins while preserving existing ones
            result = await chat_service.update_group_admins(
                chat_id=chat_id,
                admin_ids=list(set(request.admin_ids)),  # Remove duplicates
                current_user_id=current_user.user_id
            )

            if not result:
                raise HTTPException(
                    status_code=500,
                    detail="Failed to update group admins"
                )

            # Notify all participants about admin changes via WebSocket
            await manager.broadcast_to_chat(
                chat_id,
                {
                    "type": "admins_updated",
                    "chat_id": chat_id,
                    "total_admins": result["total_admins"],
                    "newly_added": result["newly_added"],
                    "admin_ids": result["admin_ids"],
                    "updated_by": current_user.user_id
                }
            )

            return {
                "message": "Group admins updated successfully",
                "total_admins": result["total_admins"],
                "newly_added": result["newly_added"],
                "admin_ids": result["admin_ids"]
            }

        except pymongo.errors.DuplicateKeyError as dke:
            print(f"Duplicate key error while updating admins: {str(dke)}")
            raise HTTPException(
                status_code=409,
                detail="Conflict while updating admins. Please try again."
            )
        except pymongo.errors.OperationFailure as of:
            print(f"MongoDB operation failed: {str(of)}")
            raise HTTPException(
                status_code=500,
                detail="Database operation failed. Please try again later."
            )
        except Exception as e:
            print(f"Error updating group admins: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail="Failed to update group admins. Please try again later."
            )

    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"Unexpected error in update_group_admins: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred while updating group admins"
        )

#================== create group invite ============================Works
@router.post("/group/{chat_id}/invite")
async def create_group_invite(
    chat_id: str, 
    request: GroupInviteRequest, 
    current_user: User = Depends(get_current_user)
):
    """Create a group invite link"""
    # Get chat settings and user role
    chat = await chat_service.get_chat(chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    chat_settings = chat.get("settings", {})
    is_admin = await chat_service.is_group_admin(chat_id, current_user.user_id)
    
    # Check permissions
    can_invite = (
        (is_admin and chat_settings.get("allow_admin_invites", True)) or
        (not is_admin and chat_settings.get("allow_user_invites", False))
    )
    
    if not can_invite:
        raise HTTPException(status_code=403, detail="You don't have permission to create invites")
    
    invite_code = await chat_service.create_group_invite(
        chat_id, 
        current_user.user_id, 
        request.expires_in_hours
    )
    
    # Use BASE_URL from config
    invite_link = f"{BASE_URL}/chats/join/{invite_code}"
    
    return {
        "invite_link": invite_link,
        "invite_code": invite_code,
        "expires_in": request.expires_in_hours
    }

#============================ join with invites ============================Works
@router.post("/join/{invite_code}")
async def join_group_via_invite(
    invite_code: str, 
    current_user: User = Depends(get_current_user)
):
    """Join a group using an invite code"""
    try:
        # Verify invite exists and is valid
        invite = await chat_service.get_invite(invite_code)
        if not invite:
            raise HTTPException(status_code=404, detail="Invite not found or expired")
        
        # Check if invite is expired
        if datetime.utcnow() > invite["expires_at"]:
            raise HTTPException(status_code=400, detail="Invite has expired")
            
        # Get chat details
        chat = await chat_service.get_chat(invite["chat_id"])
        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found")
            
        # Check if user is already a participant
        is_participant = any(
            str(p["id"]) == str(current_user.user_id) 
            for p in chat.get("participants", [])
        )
        if is_participant:
            # Return chat info instead of error if user is already a member
            return {
                "chat_id": invite["chat_id"],
                "message": "You are already a member of this group",
                "status": "already_member",
                "chat_info": {
                    "title": chat.get("title"),
                    "group_image": chat.get("group_image"),
                    "member_count": len(chat.get("participants", [])),
                    "created_at": chat.get("created_at")
                }
            }
            
        # Add user to group
        await chat_service.add_chat_participant(
            chat_id=invite["chat_id"],
            user_id=current_user.user_id,
            user_type="user",
            role="member"
        )
        
        # Mark invite as used
        await chat_service.mark_invite_used(
            invite_code=invite_code,
            used_by=current_user.user_id
        )
        
        return {
            "chat_id": invite["chat_id"],
            "message": "Successfully joined group",
            "status": "joined",
            "chat_info": {
                "title": chat.get("title"),
                "group_image": chat.get("group_image"),
                "member_count": len(chat.get("participants", [])) + 1,  # Include new member
                "created_at": chat.get("created_at")
            }
        }
        
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error joining group: {str(e)}"
        )

#======================= group settings ============================Works
@router.put("/group/{chat_id}/settings")
async def update_group_settings(
    chat_id: str, 
    request: UpdateGroupSettingsRequest, 
    current_user: User = Depends(get_current_user)
):
    """Update group chat settings"""
    is_admin = await chat_service.is_group_admin(chat_id, current_user.user_id)
    if not is_admin:
        raise HTTPException(status_code=403, detail="Only group admins can update settings")
    
    settings = {
        "allow_member_invites": request.allow_member_invites,
        "allow_member_adds": request.allow_member_adds,
        "only_admins_message": request.only_admins_message,
        "allow_admin_invites": request.allow_admin_invites,
        "allow_user_invites": request.allow_user_invites
    }
    
    # Remove None values
    settings = {k: v for k, v in settings.items() if v is not None}
    
    await chat_service.update_group_settings(chat_id, settings)
    return {"message": "Group settings updated successfully"}


#=========================== add group members ============================Works
@router.post("/group/{chat_id}/add-members")
async def add_group_members(
    chat_id: str, 
    request: AddMembersRequest, 
    current_user: User = Depends(get_current_user)
):
    """Add new members to a group chat"""
    try:
        # Check if chat exists
        chat = await chat_service.get_chat(chat_id)
        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found")
            
        # Check if user is admin first
        is_admin = await chat_service.is_group_admin(chat_id, current_user.user_id)
        print(f"User {current_user.user_id} is admin: {is_admin}")
        
        # Check general add members permission
        can_add = await chat_service.can_add_members(chat_id, current_user.user_id)
        print(f"User {current_user.user_id} can add members: {can_add}")
        
        if not can_add:
            if is_admin:
                # This shouldn't happen - admins should always be able to add
                print("WARNING: Admin without add permission")
                # Force allow for admins
                can_add = True
            else:
                raise HTTPException(
                    status_code=403, 
                    detail="You don't have permission to add members"
                )
        
        # Add members
        added_members = await chat_service.add_group_members(
            chat_id=chat_id,
            member_ids=request.member_ids,
            added_by=current_user.user_id
        )
        
        return {
            "message": "Members added successfully",
            "added_members": added_members
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error adding members: {str(e)}"
        )






# =========================================================== Status updates =========================================================

#================ create status ============================Works
@router.post("/status/create")
async def create_status(request: StatusCreateRequest, current_user: User = Depends(get_current_user)):
    dealer_network = await chat_service.get_dealer_network(current_user.user_id)
    status = ChatStatus(
        creator_id=current_user.user_id,
        creator_type="user",
        content=request.content,
        media_url=request.media_url,
        media_type=request.media_type,
        visible_to=[{"id": dealer["user_id"], "type": "dealer"} for dealer in dealer_network],
        expires_at=datetime.utcnow() + timedelta(hours=request.duration)
    )
    status_id = await chat_service.create_status(status)
    return {"status_id": status_id, "message": "Status created successfully"}

#================= get status ============================Works
@router.get("/status/list")
async def get_visible_statuses(current_user: User = Depends(get_current_user)):
    """Get all visible statuses including dealer network and creator info"""
    try:
        # Get statuses with creator info
        statuses = await chat_service.get_visible_statuses(
            user_id=current_user.user_id,
            user_type="user"
        )
        
        # Get database session
        db = next(get_db())
        
        # Enhance each status with creator and viewer details
        enhanced_statuses = []
        for status in statuses:
            # Get creator info if it's a user
            if status["creator_type"] == "user":
                creator = db.query(User).filter(
                    User.user_id == status["creator_id"]
                ).first()
                if creator:
                    status["creator_info"] = {
                        "name": f"{creator.first_name} {creator.last_name}",
                        "profile_image": creator.profile_image,
                        "ID": creator.ID,
                        "user_id": creator.user_id
                    }
            
            # Get viewer details
            viewers_info = []
            for viewer in status.get("viewed_by", []):
                if viewer["type"] == "user":
                    user = db.query(User).filter(
                        User.user_id == viewer["id"]
                    ).first()
                    if user:
                        viewers_info.append({
                            "id": viewer["id"],
                            "type": viewer["type"],
                            "timestamp": viewer["timestamp"],
                            "name": f"{user.first_name} {user.last_name}",
                            "profile_image": user.profile_image,
                            "ID": user.ID
                        })
            
            status["viewed_by"] = viewers_info
            enhanced_statuses.append(status)
        
        db.close()
        return enhanced_statuses
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error getting statuses: {str(e)}"
        )


#========================= Mark status viewed ============================Works
@router.post("/status/{status_id}/view")
async def mark_status_viewed(status_id: str, current_user: User = Depends(get_current_user)):
    await chat_service.record_status_view(status_id=status_id, viewer_id=current_user.user_id, viewer_type="user")
    return {"message": "Status marked as viewed"}






# ============================================= Chat access =================================================Works

@router.post("/{chat_id}/access")
async def access_chat(
    chat_id: str,
    current_user: User = Depends(get_current_user),
    chat_service: ChatService = Depends(get_chat_service)
):
    """Access a chat and get its details"""
    try:
        # Get chat details
        chat = await chat_service.get_chat_details(chat_id)
        if not chat:
            raise HTTPException(status_code=404, detail="Chat not found")

        # Get messages with unread status
        messages = await chat_service.get_chat_messages(
            chat_id=chat_id,
            user_id=current_user.user_id,
            user_type="user"
        )

        # Mark messages as delivered
        await chat_service.mark_messages_as_delivered(
            chat_id=chat_id,
            user_id=current_user.user_id,
            user_type="user"
        )

        # Get participants info
        participants = await chat_service.get_chat_participants_info(chat["participants"])

        # Get websocket info
        websocket_info = {
            "token": create_access_token({"sub": str(current_user.user_id)}),
            "user_id": current_user.user_id,
            "user_type": "user"
        }

        # Get permissions
        permissions = {
            "can_send_messages": True,
            "can_add_members": chat.get("chat_type") == "group",
            "is_admin": await chat_service.is_group_admin(chat_id, current_user.user_id)
        }

        return {
            "chat_details": chat,
            "participants": participants,
            "messages": messages,
            "websocket_info": websocket_info,
            "permissions": permissions
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))




# ================================ Chat Clear =============================================Works


@router.post("/{chat_id}/clear")
async def clear_chat_history(
    chat_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Clear chat history for the current user (only affects their view).
    
    - **chat_id**: The ID of the chat to clear history for.
    - **current_user**: The authenticated user (automatically injected via dependency).
    
    Returns:
    - A success message if the chat history is cleared.
    - Raises an HTTPException if the chat is not found or the user is not a participant.
    """
    # Verify chat exists
    chat = await chat_service.get_chat(chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    # Check if the user is a participant in the chat
    is_participant = any(
        p["id"] == current_user.user_id 
        for p in chat.get("participants", [])
    )
    if not is_participant:
        raise HTTPException(
            status_code=403, 
            detail="You are not a participant in this chat"
        )
    
    # Clear chat history for the current user
    await chat_service.clear_chat(
        chat_id=chat_id,
        user_id=current_user.user_id,
        user_type="user"
    )
    
    return {"message": "Chat history cleared successfully"}




# ================================ Reply to message =============================================

@router.post("/{chat_id}/messages/{message_id}/reply")
async def reply_to_message(
    chat_id: str,
    message_id: str,
    request: ReplyMessageRequest,
    current_user: User = Depends(get_current_user)
):
    """Reply to a specific message"""
    try:
        # Get original message
        original_message = await chat_service.get_message(message_id)
        if not original_message:
            raise HTTPException(status_code=404, detail="Original message not found")

        sender_type = await chat_service.get_participant_type(chat_id, current_user.user_id)
        
        # Create reply message
        message = ChatMessage(
            chat_id=chat_id,
            sender_id=current_user.user_id,
            sender_type=sender_type,
            content=request.content,
            message_type=request.message_type,
            reply_to={
                "message_id": message_id,
                "content": original_message["content"],
                "sender_id": original_message["sender_id"]
            },
            gem_id=request.gem_id,
            attachment=request.attachment
        )
        
        result = await chat_service.add_message(message)
        
        # Notify via WebSocket
        await manager.broadcast_to_chat(
            chat_id,
            {
                "type": "new_reply",
                "message": jsonable_encoder(result)
            }
        )
        
        return jsonable_encoder(result)
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error replying to message: {str(e)}"
        )


# ================================ Toggle message reaction =============================
@router.post("/{chat_id}/messages/{message_id}/react")
async def react_to_message(
    chat_id: str,
    message_id: str,
    request: MessageReactionRequest,
    current_user: User = Depends(get_current_user)
):
    """Add/remove reaction to a message"""
    try:
        result = await chat_service.toggle_message_reaction(
            message_id=message_id,
            user_id=current_user.user_id,
            emoji=request.emoji
        )
        
        # Notify via WebSocket
        await manager.broadcast_to_chat(
            chat_id,
            {
                "type": "reaction_updated",
                "message_id": message_id,
                "reactions": result["reactions"]
            }
        )
        
        return result
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error updating reaction: {str(e)}"
        )

# ================================ Remove group memeber =============================
@router.post("/group/{chat_id}/remove-member")
async def remove_group_member(
    chat_id: str,
    request: RemoveMemberRequest,
    current_user: User = Depends(get_current_user)
):
    """Remove a member from group (admin only)"""
    try:
        # Check if user is admin
        is_admin = await chat_service.is_group_admin(chat_id, current_user.user_id)
        if not is_admin:
            raise HTTPException(
                status_code=403,
                detail="Only admins can remove members"
            )
        
        result = await chat_service.remove_group_member(
            chat_id=chat_id,
            user_id=request.user_id,
            removed_by=current_user.user_id,
            reason=request.reason
        )
        
        # Notify via WebSocket
        await manager.broadcast_to_chat(
            chat_id,
            {
                "type": "member_removed",
                "user_id": request.user_id,
                "removed_by": current_user.user_id
            }
        )
        
        return {"message": "Member removed successfully"}
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error removing member: {str(e)}"
        )


# ================================ Leave group chat =============================
@router.post("/group/{chat_id}/leave")
async def leave_group(
    chat_id: str,
    request: LeaveGroupRequest,
    current_user: User = Depends(get_current_user)
):
    """Leave a group chat"""
    try:
        # Check if user is the only admin
        is_admin = await chat_service.is_group_admin(chat_id, current_user.user_id)
        if is_admin:
            other_admins = await chat_service.get_other_admins(chat_id, current_user.user_id)
            if not other_admins:
                raise HTTPException(
                    status_code=400,
                    detail="You are the only admin. Please assign another admin before leaving"
                )
        
        result = await chat_service.remove_group_member(
            chat_id=chat_id,
            user_id=current_user.user_id,
            is_leaving=True,
            reason=request.reason
        )
        
        # Notify others
        await manager.broadcast_to_chat(
            chat_id,
            {
                "type": "member_left",
                "user_id": current_user.user_id
            }
        )
        
        return {"message": "Left group successfully"}
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error leaving group: {str(e)}"
        )


# ================================ Block user =============================
@router.post("/block-user/{user_id}")
async def block_user(
    user_id: int,
    request: BlockUserRequest,
    current_user: User = Depends(get_current_user)
):
    """Block a user"""
    try:
        # Check if already blocked
        is_blocked = await chat_service.is_user_blocked(user_id, current_user.user_id)
        if is_blocked:
            raise HTTPException(status_code=400, detail="User is already blocked")
            
        result = await chat_service.block_user(
            blocker_id=current_user.user_id,
            blocked_id=user_id,
            reason=request.reason
        )
        return {"message": "User blocked successfully"}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error blocking user: {str(e)}"
        )


# ================================ Unblock user =============================
@router.post("/unblock-user/{user_id}")
async def unblock_user(
    user_id: int,
    request: UnblockUserRequest,
    current_user: User = Depends(get_current_user)
):
    """Unblock a user"""
    try:
        # Check if actually blocked
        is_blocked = await chat_service.is_user_blocked(user_id, current_user.user_id)
        if not is_blocked:
            raise HTTPException(status_code=400, detail="User is not blocked")
            
        result = await chat_service.unblock_user(
            blocker_id=current_user.user_id,
            blocked_id=user_id,
            reason=request.reason
        )
        return {"message": "User unblocked successfully"}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error unblocking user: {str(e)}"
        )

# ================================ Report user =============================
@router.post("/report-user")
async def report_user(
    request: ReportUserRequest,
    current_user: User = Depends(get_current_user)
):
    """Report a user"""
    try:
        result = await chat_service.create_user_report(
            reporter_id=current_user.user_id,
            reported_id=request.user_id,
            report_type=request.report_type,
            reason=request.reason,
            description=request.description
        )
        return {"message": "User reported successfully", "report_id": result}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error reporting user: {str(e)}"
        )


# ================================ Edit message =============================
@router.put("/messages/{message_id}")
async def edit_message(
    message_id: str,
    request: EditMessageRequest,
    current_user: User = Depends(get_current_user)
):
    """Edit a message"""
    try:
        # Get message
        message = await chat_service.get_message(message_id)
        if not message:
            raise HTTPException(status_code=404, detail="Message not found")
            
        # Check if user is the sender
        if str(message["sender_id"]) != str(current_user.user_id):
            raise HTTPException(
                status_code=403,
                detail="You can only edit your own messages"
            )
            
        result = await chat_service.edit_message(
            message_id=message_id,
            new_content=request.content,
            edited_reason=request.edited_reason
        )
        
        # Notify via WebSocket
        await manager.broadcast_to_chat(
            message["chat_id"],
            {
                "type": "message_edited",
                "message_id": message_id,
                "new_content": request.content,
                "edited_at": datetime.utcnow().isoformat()
            }
        )
        
        return result
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error editing message: {str(e)}"
        )
