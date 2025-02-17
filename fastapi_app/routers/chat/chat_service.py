from fastapi_app.models.chat_models import ChatRoom, ChatMessage, ChatStatus, ChatAttachment
from fastapi_app.database import get_mongo_collection
from bson import ObjectId
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Union
import os
import secrets
from fastapi.encoders import jsonable_encoder
from fastapi import HTTPException, UploadFile
from fastapi_app.utils.file_handler import file_handler
from fastapi_app.models.models import User
from sqlalchemy.orm import Session
from fastapi_app.database import get_db
from fastapi_app.routers.Trade.deal_service import DealService
from fastapi_app.models.models import Gem

class ChatService:
    def __init__(self):
        # Core collections
        self.chat_collection = get_mongo_collection("chats")
        self.message_collection = get_mongo_collection("chat_messages")
        self.status_collection = get_mongo_collection("chat_statuses")
        self.attachment_collection = get_mongo_collection("chat_attachments")
        self.dealer_collection = get_mongo_collection("dealers")
        self.invite_collection = get_mongo_collection("group_invites")
        
        # User management collections
        self.report_collection = get_mongo_collection("user_reports")
        self.blocked_users_collection = get_mongo_collection("blocked_users")
        self.removed_members_collection = get_mongo_collection("removed_members")
        # Removed message_edits_collection as we're storing edits in messages

        # Additional services
        self.deal_service = DealService()

    async def get_dealer_info(self, dealer_id: str) -> Optional[Dict]:
        """Get dealer information from MongoDB"""
        dealer = await self.dealer_collection.find_one({"dealer_id": dealer_id})
        return dealer

    async def create_chat(self, chat: ChatRoom) -> str:
        """Create a new chat room"""
        chat_dict = chat.dict(exclude_none=True)
        result = await self.chat_collection.insert_one(chat_dict)
        return str(result.inserted_id)

    async def add_message(self, message: ChatMessage) -> Dict:
        """Add a new message and return the saved message"""
        try:
            current_time = datetime.utcnow()
            
            # Create message document with all required fields
            message_dict = {
                "chat_id": str(message.chat_id),
                "sender_id": str(message.sender_id),
                "sender_type": message.sender_type,
                "content": message.content,
                "message_type": message.message_type,
                "timestamp": current_time,
                "read_by": [{
                    "user_id": str(message.sender_id),
                    "user_type": message.sender_type,
                    "timestamp": current_time
                }],
                "delivered_to": [],
                "is_deleted": False,
                "is_edited": False,
            }

            # Insert into database
            result = await self.message_collection.insert_one(message_dict)
            
            if not result.inserted_id:
                raise Exception("Failed to insert message")

            # Add the message ID to the document and format for JSON response
            message_dict["_id"] = result.inserted_id
            message_dict["message_id"] = str(result.inserted_id)
            message_dict["timestamp"] = message_dict["timestamp"].isoformat()
            
            # Update timestamps in read_by to ISO format
            for reader in message_dict["read_by"]:
                reader["timestamp"] = reader["timestamp"].isoformat()

            # Update chat's last message and activity
            await self.chat_collection.update_one(
                {"_id": ObjectId(message.chat_id)},
                {
                    "$set": {
                        "last_message": {
                            "message_id": str(result.inserted_id),
                            "content": message.content,
                            "sender_id": str(message.sender_id),
                            "sender_type": message.sender_type,
                            "timestamp": current_time.isoformat(),
                            "message_type": message.message_type,
                        },
                        "last_activity": current_time
                    }
                }
            )

            return message_dict

        except Exception as e:
            print(f"Error adding message: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to add message: {str(e)}")

    async def get_message(self, message_id: str) -> Optional[Dict]:
        """Get a message by ID"""
        try:
            message = await self.message_collection.find_one(
                {"_id": ObjectId(message_id)}
            )
            
            if message:
                # Convert ObjectId to string
                message["_id"] = str(message["_id"])
                message["message_id"] = str(message["_id"])
                
                # Add edit information if message was edited
                if message.get("is_edited"):
                    message["edit_info"] = {
                        "last_edited_at": message.get("last_edited_at"),
                        "edit_count": len(message.get("edit_history", [])),
                        "latest_edit": message.get("edit_history", [])[-1] if message.get("edit_history") else None
                    }
                
                return message
            
            return None
        except Exception as e:
            print(f"Error getting message: {str(e)}")
            return None

    async def delete_message(
        self,
        message_id: str,
        user_id: Union[int, str],
        user_type: str,
        delete_for_everyone: bool = False
    ) -> bool:
        """Delete a message"""
        try:
            # Try to find the message first
            message = await self.get_message(message_id)
            if not message:
                return False

            query = {
                "$or": [
                    {"_id": ObjectId(message["_id"])},
                    {"message_id": message["message_id"]},
                    {"chat_id": message["chat_id"]}
                ]
            }

            if delete_for_everyone:
                update = {
                    "$set": {
                        "is_deleted": True,
                        "content": "This message was deleted",
                        "deleted_at": datetime.utcnow(),
                        "deleted_by": {
                            "user_id": user_id,
                            "user_type": user_type,
                            "timestamp": datetime.utcnow()
                        }
                    },
                    "$unset": {"attachment": ""}
                }
            else:
                update = {
                    "$addToSet": {
                        "deleted_for": {
                            "user_id": user_id,
                            "user_type": user_type,
                            "deleted_at": datetime.utcnow()
                        }
                    }
                }

            result = await self.message_collection.update_one(query, update)
            return result.modified_count > 0
        except Exception as e:
            print(f"Error deleting message: {str(e)}")
            return False

    async def get_chat(self, chat_id: str) -> Optional[Dict]:
        """Get chat room details"""
        try:
            # First try with the provided chat_id as is
            chat = await self.chat_collection.find_one({"chat_id": chat_id})
            
            if not chat:
                # If not found, try with ObjectId
                chat = await self.chat_collection.find_one({"_id": ObjectId(chat_id)})
            
            if chat:
                # Convert ObjectId to string
                if "_id" in chat:
                    chat["_id"] = str(chat["_id"])
                return chat
            
            return None
        except Exception as e:
            print(f"Error getting chat: {str(e)}")
            return None

    async def clear_chat(self, chat_id: str, user_id: int, user_type: str) -> bool:
        """Clear chat history for a user without affecting other participants"""
        try:
            # Get the chat first to verify it exists
            chat = await self.get_chat(chat_id)
            if not chat:
                return False
            
            # Get the last message ID before clearing
            last_message = await self.message_collection.find_one(
                {"chat_id": chat_id},
                sort=[("timestamp", -1)]
            )
            last_message_id = str(last_message["_id"]) if last_message else None

            # Add user to deleted_for array for all messages in the chat
            result = await self.message_collection.update_many(
                {"chat_id": chat_id},
                {
                    "$addToSet": {
                        "deleted_for": {
                            "id": user_id,
                            "type": user_type,
                            "cleared_at": datetime.utcnow(),
                            "clear_type": "clear_for_me"
                        }
                    }
                }
            )
            
            # Update chat's clear history for this user
            chat_id_for_update = ObjectId(chat["_id"]) if isinstance(chat["_id"], str) else chat["_id"]
            await self.chat_collection.update_one(
                {"_id": chat_id_for_update},
                {
                    "$set": {
                        f"settings.clear_history.{user_type}_{user_id}": {
                            "cleared_at": datetime.utcnow(),
                            "cleared_until_msg_id": last_message_id,
                            "clear_type": "clear_for_me"
                        }
                    }
                }
            )
            
            return True
        except Exception as e:
            print(f"Error clearing chat: {str(e)}")
            return False

    async def get_chat_participants(self, chat_id: str) -> List[Dict]:
        chat = await self.chat_collection.find_one({"_id": ObjectId(chat_id)})
        return chat["participants"] if chat else []

    async def get_participant_type(self, chat_id: str, user_id: Union[int, str]) -> str:
        """Get participant type in a chat"""
        try:
            chat = await self.get_chat_details(chat_id)
            if not chat:
                raise HTTPException(status_code=404, detail="Chat not found")

            for participant in chat.get("participants", []):
                if str(participant["id"]) == str(user_id):
                    return participant["type"]
            
            raise HTTPException(status_code=403, detail="User not in chat")
        except HTTPException as he:
            raise he
        except Exception as e:
            print(f"Error getting participant type: {str(e)}")
            raise HTTPException(status_code=500, detail="Internal server error")

    async def mark_as_read(
        self,
        chat_id: str,
        user_id: Union[int, str],
        user_type: str
    ) -> bool:
        """Mark all messages in a chat as read"""
        try:
            # Update all unread messages
            result = await self.message_collection.update_many(
                {
                    "chat_id": chat_id,
                    "sender_id": {"$ne": user_id},
                    "read_by": {
                        "$not": {
                            "$elemMatch": {
                                "user_id": user_id
                            }
                        }
                    }
                },
                {
                    "$addToSet": {
                        "read_by": {
                            "user_id": user_id,
                            "user_type": user_type,
                            "timestamp": datetime.utcnow()
                        }
                    }
                }
            )

            print(f"Marked {result.modified_count} messages as read")  # Debug print

            # Reset unread count in chat document
            await self.chat_collection.update_one(
                {"_id": ObjectId(chat_id)},
                {
                    "$set": {
                        f"unread_counts.{user_type}_{user_id}": 0
                    }
                }
            )

            return True

        except Exception as e:
            print(f"Error marking as read: {str(e)}")
            return False

    async def create_status(self, status: ChatStatus) -> str:
        status_dict = status.dict(exclude_none=True)
        result = await self.status_collection.insert_one(status_dict)
        return str(result.inserted_id)

    async def record_status_view(self, status_id: str, viewer_id: int, viewer_type: str) -> None:
        await self.status_collection.update_one(
            {"_id": ObjectId(status_id)},
            {
                "$addToSet": {
                    "viewed_by": {
                        "id": viewer_id,
                        "type": viewer_type,
                        "timestamp": datetime.utcnow()
                    }
                }
            }
        )

    async def get_user_chats(
        self,
        user_id: Union[int, str],
        user_type: str,
        db: Session
    ) -> List[Dict]:
        """Get all chats for a user with participant details"""
        try:
            cursor = self.chat_collection.find({
                "participants": {
                    "$elemMatch": {
                        "id": user_id,
                        "type": user_type
                    }
                }
            }).sort("last_activity", -1)

            chats = []
            async for chat in cursor:
                try:
                    # Format basic chat info
                    chat_info = {
                        "chat_id": str(chat["_id"]),
                        "chat_type": chat["chat_type"],
                        "participants": chat["participants"],
                    }

                    # Get correct unread count for current user
                    unread_count = 0
                    unread_counts = chat.get("unread_counts", {})
                    user_key = f"user_{user_id}"
                    
                    # Try different possible keys for unread counts
                    if user_key in unread_counts:
                        unread_count = unread_counts[user_key]
                    elif str(user_id) in unread_counts:
                        unread_count = unread_counts[str(user_id)]
                    
                    chat_info["unread_count"] = unread_count

                    # Add last message if exists
                    if last_message := chat.get("last_message"):
                        is_from_me = str(last_message["sender_id"]) == str(user_id)
                        read_by = last_message.get("read_by", [])
                        is_read = any(
                            str(read["user_id"]) == str(user_id) 
                            for read in read_by
                        )
                        
                        chat_info["last_message"] = {
                            "message_id": last_message["message_id"],
                            "content": last_message["content"],
                            "sender_id": last_message["sender_id"],
                            "sender_type": last_message["sender_type"],
                            "timestamp": last_message["timestamp"],
                            "message_type": last_message.get("message_type", "text"),
                            "attachment": last_message.get("attachment"),
                            "is_deleted": last_message.get("is_deleted", False),
                            "is_read": is_read or is_from_me,
                            "read_by": read_by
                        }

                    # Add other chat details
                    chat_info.update({
                        "created_at": chat["created_at"],
                        "last_activity": chat["last_activity"],
                        "title": chat.get("title", ""),
                        "group_image": chat.get("group_image"),
                        "other_user": await self._get_other_user_info(chat, user_id, db)
                    })

                    chats.append(chat_info)

                except Exception as e:
                    print(f"Error processing chat {chat.get('_id')}: {str(e)}")
                    continue

            return chats

        except Exception as e:
            print(f"Error in get_user_chats: {str(e)}")
            return []

    async def _get_other_user_info(self, chat: Dict, current_user_id: Union[int, str], db: Session) -> Dict:
        """Helper method to get other user's information"""
        try:
            other_participant = next(
                (p for p in chat["participants"] 
                 if str(p["id"]) != str(current_user_id)),
                None
            )
            
            if other_participant:
                other_user = db.query(User).filter(
                    User.user_id == int(other_participant["id"])
                ).first()
                
                if other_user:
                    return {
                        "name": f"{other_user.first_name} {other_user.last_name}",
                        "profile_image": other_user.profile_image or "uploads/profile_images/man.png"
                    }
            
            return {"name": "Unknown User", "profile_image": "uploads/profile_images/man.png"}
            
        except Exception as e:
            print(f"Error getting other user info: {str(e)}")
            return {"name": "Unknown User", "profile_image": "uploads/profile_images/man.png"}

    async def add_attachment(
        self,
        attachment: ChatAttachment,
        file: UploadFile
    ) -> Optional[Dict]:
        """Add a new attachment and upload file"""
        try:
            # Create a simpler file structure
            attachment_id = str(ObjectId())
            file_ext = file.filename.split('.')[-1].lower() if '.' in file.filename else ''
            
            # Simplified path structure: chat_attachments/CHAT_ID/FILE_ID.ext
            file_path = f"chat_attachments/{attachment.chat_id}/{attachment_id}.{file_ext}"
            
            # Save file
            file_url = await file_handler.save_file(file, file_path)
            
            if not file_url:
                return None

            # Get file size
            file_size = os.path.getsize(os.path.join("uploads", file_path))
            
            # Prepare attachment data
            attachment_data = {
                "chat_id": attachment.chat_id,
                "message_id": attachment_id,
                "uploader_id": attachment.uploader_id,
                "uploader_type": attachment.uploader_type,
                "file_name": file.filename,
                "file_type": attachment.file_type,
                "file_path": file_path,
                "file_size": file_size,
                "mime_type": attachment.content_type,
                "file_url": file_url,
                "content_type": attachment.content_type,
                "uploaded_at": datetime.utcnow(),
                "status": "completed"
            }
            
            # Save to database
            result = await self.attachment_collection.insert_one(attachment_data)
            
            return {
                "id": attachment_id,
                "name": file.filename,
                "type": attachment.content_type,
                "url": file_url,
                "size": file_size
            }

        except Exception as e:
            print(f"Error adding attachment: {str(e)}")
            return None

    async def get_chat_details(self, chat_id: str) -> Optional[Dict]:
        """Get detailed chat information"""
        try:
            # Try to find chat by both _id and chat_id
            chat = await self.chat_collection.find_one({
                "$or": [
                    {"_id": ObjectId(chat_id)},
                    {"chat_id": chat_id}
                ]
            })
            
            if not chat:
                return None
                
            # Convert ObjectId to string
            if isinstance(chat.get("_id"), ObjectId):
                chat["_id"] = str(chat["_id"])
            
            # Ensure chat_id exists
            if "chat_id" not in chat:
                chat["chat_id"] = str(chat["_id"])
                
            # Convert any other ObjectIds in the document
            if "last_message" in chat and isinstance(chat["last_message"].get("_id"), ObjectId):
                chat["last_message"]["_id"] = str(chat["last_message"]["_id"])
                
            return chat
            
        except Exception as e:
            print(f"Error getting chat details: {str(e)}")
            return None

    async def get_chat_participants_info(self, participants: List[Dict]) -> List[Dict]:
        """Get detailed information about chat participants"""
        try:
            participant_info = []
            for participant in participants:
                user_info = None
                if participant["type"] == "user":
                    # Get user info from your user service/database
                    user_info = {
                        "id": participant["id"],
                        "type": "user",
                        "name": participant.get("name", "User"),
                        "avatar": participant.get("avatar")
                    }
                elif participant["type"] == "dealer":
                    # Get dealer info
                    dealer = await self.dealer_collection.find_one({"dealer_id": participant["id"]})
                    if dealer:
                        user_info = {
                            "id": participant["id"],
                            "type": "dealer",
                            "name": dealer.get("name", "Dealer"),
                            "avatar": dealer.get("avatar")
                        }
                
                if user_info:
                    participant_info.append(user_info)
            
            return participant_info
            
        except Exception as e:
            print(f"Error getting participant info: {str(e)}")
            return []

    async def get_chat_messages(
        self,
        chat_id: str,
        user_id: Union[int, str],
        user_type: str,
        limit: int = 50,
        before_id: Optional[str] = None
    ) -> List[Dict]:
        """Get messages for a chat"""
        try:
            # Base query with both string and ObjectId possibilities for chat_id
            query = {
                "$or": [
                    {"chat_id": chat_id},
                    {"chat_id": str(chat_id)}
                ],
                "deleted_for": {
                    "$not": {
                        "$elemMatch": {
                            "user_id": user_id,
                            "user_type": user_type
                        }
                    }
                }
            }

            # Add before_id condition if provided
            if before_id:
                try:
                    query["_id"] = {"$lt": ObjectId(before_id)}
                except:
                    pass

            # Debug print
            print(f"Query for messages: {query}")

            # Get messages with explicit sort and limit
            cursor = self.message_collection.find(query)
            cursor.sort("timestamp", -1)
            cursor.limit(limit)
            
            messages = await cursor.to_list(length=limit)

            # Debug print
            print(f"Found {len(messages)} messages")

            # Process messages
            processed_messages = []
            for msg in messages:
                processed_msg = {
                    "message_id": str(msg["_id"]),
                    "chat_id": msg["chat_id"],
                    "sender_id": msg["sender_id"],
                    "sender_type": msg["sender_type"],
                    "content": "This message was deleted" if msg.get("is_deleted", False) else msg["content"],
                    "message_type": msg.get("message_type", "text"),
                    "timestamp": msg["timestamp"],
                    "read_by": msg.get("read_by", []),
                    "delivered_to": msg.get("delivered_to", []),
                    "reactions": msg.get("reactions", {}),
                    "is_edited": msg.get("is_edited", False),
                    "reply_to": msg.get("reply_to"),
                }

                if not msg.get("is_deleted", False):
                    processed_msg["attachment"] = msg.get("attachment")
                    processed_msg["gem_id"] = msg.get("gem_id")

                processed_messages.append(processed_msg)

            return processed_messages

        except Exception as e:
            print(f"Error getting chat messages: {str(e)}")
            return []

    async def get_user_chats_paginated(
        self, 
        user_id: int, 
        user_type: str,
        limit: int = 20,
        skip: int = 0
    ) -> List[Dict]:
        """Get paginated chats for a user"""
        try:
            cursor = self.chat_collection.find({
                "participants": {
                    "$elemMatch": {
                        "id": user_id,
                        "type": user_type
                    }
                },
                "is_active": True
            }).sort("last_activity", -1).skip(skip).limit(limit)
            
            chats = []
            async for chat in cursor:
                chat["_id"] = str(chat["_id"])
                chat["unread_count"] = chat.get("unread_counts", {}).get(f"{user_type}_{user_id}", 0)
                # Ensure all required fields have default values
                chat.setdefault("last_message", None)
                chat.setdefault("title", None)
                chat.setdefault("group_image", None)
                chats.append(chat)
            
            return chats
        except Exception as e:
            raise Exception(f"Database error: {str(e)}")

    async def is_user_in_dealer_network(self, user_id: int, dealer_id: int) -> bool:
        """Check if a user is in another user's dealer network"""
        dealer = await self.dealer_collection.find_one({
            "owner_id": user_id,
            "user_id": dealer_id
        })
        return dealer is not None

    async def get_dealer_network(self, user_id: int) -> List[Dict]:
        """Get all dealers in a user's network"""
        dealers = await self.dealer_collection.find({
            "owner_id": user_id
        }).to_list(None)
        return dealers

    async def get_visible_statuses(
        self,
        user_id: Union[int, str],
        user_type: str
    ) -> List[Dict]:
        """Get all visible statuses for a user"""
        try:
            # Get current time
            now = datetime.utcnow()
            
            # Get user's dealer network
            dealer_network = await self.get_dealer_network(user_id)
            dealer_ids = [dealer["user_id"] for dealer in dealer_network]
            
            # Find active statuses
            cursor = self.status_collection.find({
                "$or": [
                    # Statuses created by the user
                    {
                        "creator_id": user_id,
                        "creator_type": user_type
                    },
                    # Statuses created by dealers in user's network
                    {
                        "creator_id": {"$in": dealer_ids},
                        "creator_type": "user"
                    }
                ],
                "expires_at": {"$gt": now},
                "is_active": True
            }).sort("created_at", -1)
            
            statuses = []
            async for status in cursor:
                status["_id"] = str(status["_id"])
                status["status_id"] = status.get("status_id", status["_id"])
                statuses.append(status)
                
            return statuses
            
        except Exception as e:
            print(f"Error getting visible statuses: {str(e)}")
            return []

    async def is_group_admin(self, chat_id: str, user_id: int) -> bool:
        """Check if user is a group admin"""
        chat = await self.chat_collection.find_one({
            "_id": ObjectId(chat_id),
            "settings.group_admins": {
                "$elemMatch": {
                    "id": user_id,
                    "role": "admin"  # Explicitly check for admin role
                }
            }
        })
        return chat is not None

    async def update_group_admins(self, chat_id: str, admin_ids: List[int], current_user_id: int) -> Dict:
        """
        Update group admin list while preserving existing admins
        Returns information about the update operation
        """
        try:
            # Get current chat and settings
            chat = await self.chat_collection.find_one({"_id": ObjectId(chat_id)})
            if not chat:
                raise ValueError("Chat not found")

            # Get current admin list
            current_admins = chat.get("settings", {}).get("group_admins", [])
            current_admin_ids = [admin["id"] for admin in current_admins]

            # Ensure current user remains an admin
            if current_user_id not in admin_ids and current_user_id in current_admin_ids:
                admin_ids.append(current_user_id)

            # Add new admins while preserving existing ones
            new_admins = []
            for admin_id in admin_ids:
                if admin_id not in current_admin_ids:
                    new_admins.append({
                        "id": admin_id,
                        "type": "user",
                        "role": "admin",
                        "added_by": current_user_id,
                        "added_at": datetime.utcnow(),
                        "permissions": [
                            "invite",
                            "add_members",
                            "remove_members",
                            "manage_settings"
                        ]
                    })

            # Combine existing and new admins
            updated_admins = current_admins + new_admins

            # Update the settings
            result = await self.chat_collection.update_one(
                {"_id": ObjectId(chat_id)},
                {"$set": {"settings.group_admins": updated_admins}}
            )

            return {
                "success": result.modified_count > 0,
                "total_admins": len(updated_admins),
                "newly_added": len(new_admins),
                "admin_ids": [admin["id"] for admin in updated_admins]
            }

        except Exception as e:
            raise ValueError(f"Failed to update group admins: {str(e)}")

    async def create_group_invite(
        self, 
        chat_id: str, 
        creator_id: int,
        expires_in_hours: int = 24
    ) -> str:
        """Create a group invite link"""
        try:
            # Generate unique code
            invite_code = secrets.token_urlsafe(16)
            expires_at = datetime.utcnow() + timedelta(hours=expires_in_hours)
            
            # Create invite document
            invite_data = {
                "code": invite_code,
                "chat_id": chat_id,
                "creator_id": creator_id,
                "created_at": datetime.utcnow(),
                "expires_at": expires_at,
                "is_active": True,
                "used_by": None,
                "used_at": None
            }
            
            # Insert into database
            result = await self.invite_collection.insert_one(invite_data)
            if not result.inserted_id:
                raise Exception("Failed to create invite")
            
            return invite_code
            
        except Exception as e:
            print(f"Error creating invite: {str(e)}")
            raise HTTPException(status_code=500, detail="Failed to create invite")

    async def join_group_via_invite(self, invite_code: str, user_id: int) -> str:
        """Join a group using invite link"""
        # Find valid invite
        invite = await self.invite_collection.find_one({
            "code": invite_code,
            "expires_at": {"$gt": datetime.utcnow()},
            "is_active": True
        })
        
        if not invite:
            raise ValueError("Invalid or expired invite link")
        
        # Check if already in group
        chat = await self.chat_collection.find_one({
            "_id": ObjectId(invite["chat_id"]),
            "participants": {
                "$elemMatch": {
                    "id": user_id
                }
            }
        })
        
        if chat:
            raise ValueError("You are already in this group")
        
        # Add to group
        await self.chat_collection.update_one(
            {"_id": ObjectId(invite["chat_id"])},
            {
                "$push": {
                    "participants": {
                        "id": user_id,
                        "type": "user",
                        "role": "member",
                        "joined_at": datetime.utcnow()
                    }
                }
            }
        )
        
        return invite["chat_id"]

    async def can_create_invite(self, chat_id: str, user_id: int) -> bool:
        """Check if user can create invites"""
        chat = await self.chat_collection.find_one({"_id": ObjectId(chat_id)})
        if not chat:
            return False
        
        # Admins can always create invites
        if any(admin["id"] == user_id for admin in chat["settings"]["group_admins"]):
            return True
        
        # Check if members can create invites
        return chat["settings"].get("allow_member_invites", False)

    async def can_add_members(self, chat_id: str, user_id: int) -> bool:
        """Check if user can add members"""
        try:
            chat = await self.chat_collection.find_one({"_id": ObjectId(chat_id)})
            if not chat:
                print(f"Chat {chat_id} not found")
                return False

            # Debug prints
            print(f"Checking permissions for user {user_id} in chat {chat_id}")
            print(f"Chat settings: {chat.get('settings', {})}")
            
            # Check if user is admin
            admins = chat.get("settings", {}).get("group_admins", [])
            print(f"Group admins: {admins}")
            
            is_admin = any(
                str(admin.get("id")) == str(user_id) or 
                str(admin.get("user_id")) == str(user_id)  # Check both id and user_id
                for admin in admins
            )
            print(f"Is admin: {is_admin}")

            if is_admin:
                print(f"User {user_id} is an admin, allowing add members")
                return True

            # Check regular member permissions
            settings = chat.get("settings", {})
            allow_member_adds = settings.get("allow_member_adds", False)
            print(f"Allow member adds setting: {allow_member_adds}")

            # Check if user is a participant
            is_participant = any(
                str(p.get("id")) == str(user_id)
                for p in chat.get("participants", [])
            )
            print(f"Is participant: {is_participant}")

            if not is_participant:
                print(f"User {user_id} is not a participant")
                return False

            # Regular members can add if setting allows
            return allow_member_adds

        except Exception as e:
            print(f"Error checking add members permission: {str(e)}")
            return False

    async def add_group_members(
        self, 
        chat_id: str, 
        member_ids: List[int],
        added_by: int
    ) -> List[Dict]:
        """Add new members to the group"""
        try:
            chat = await self.chat_collection.find_one({"_id": ObjectId(chat_id)})
            if not chat:
                raise ValueError("Group not found")
            
            # Filter out existing members
            existing_ids = {str(p["id"]) for p in chat.get("participants", [])}
            new_members = []
            
            for member_id in member_ids:
                if str(member_id) not in existing_ids:
                    new_member = {
                        "id": member_id,
                        "type": "user",
                        "role": "member",
                        "joined_at": datetime.utcnow(),
                        "permissions": []  # Regular members have no special permissions
                    }
                    new_members.append(new_member)
            
            if new_members:
                await self.chat_collection.update_one(
                    {"_id": ObjectId(chat_id)},
                    {"$push": {"participants": {"$each": new_members}}}
                )
            
            # Return added member details
            return [{
                "user_id": member["id"],
                "role": member["role"],
                "joined_at": member["joined_at"]
            } for member in new_members]
            
        except Exception as e:
            print(f"Error adding members: {str(e)}")
            raise ValueError(f"Failed to add members: {str(e)}")

    async def is_dealer_in_user_network(self, dealer_id: str, user_id: str) -> bool:
        """Check if the dealer is part of the user's network."""
        dealer = await self.dealer_collection.find_one({"dealer_id": dealer_id, "owner_id": int(user_id)})
        
        return dealer is not None

    async def get_chats(self, user_id: int, user_type: str = "user") -> List[Dict]:
        """Get list of chats for a user"""
        try:
            # Find all chats where user is a participant
            chats = await self.chat_collection.find({
                "participants": {
                    "$elemMatch": {
                        "id": user_id,
                        "type": user_type
                    }
                }
            }).to_list(None)

            chat_list = []
            for chat in chats:
                # Debug print
                print(f"Processing chat: {chat}")
                
                # Get all possible chat IDs
                possible_chat_ids = [
                    str(chat["_id"]),
                    chat.get("chat_id"),
                    str(chat.get("chat_id"))
                ]
                
                # Get the latest message for this chat using any possible chat_id
                latest_message = await self.message_collection.find_one(
                    {
                        "chat_id": {"$in": possible_chat_ids},
                        "deleted_for": {
                            "$not": {
                                "$elemMatch": {
                                    "id": user_id,
                                    "type": user_type
                                }
                            }
                        }
                    },
                    sort=[("timestamp", -1)]
                )
                
                # Debug print
                print(f"Latest message found: {latest_message}")

                # Count unread messages
                unread_count = await self.message_collection.count_documents({
                    "chat_id": {"$in": possible_chat_ids},
                    "sender_id": {"$ne": user_id},
                    "read_by": {
                        "$not": {
                            "$elemMatch": {
                                "id": user_id,
                                "type": user_type
                            }
                        }
                    }
                })

                # Format the response
                chat_info = {
                    "chat_id": str(chat["_id"]),
                    "chat_type": chat["chat_type"],
                    "participants": chat["participants"],
                    "last_message": {
                        "content": latest_message["content"],
                        "sender_id": latest_message["sender_id"],
                        "sender_type": latest_message["sender_type"],
                        "timestamp": latest_message["timestamp"],
                        "message_id": latest_message.get("message_id", str(latest_message["_id"]))
                    } if latest_message else None,
                    "unread_count": unread_count,
                    "created_at": chat["created_at"],
                    "last_activity": latest_message["timestamp"] if latest_message else chat["created_at"],
                    "title": chat.get("title"),
                    "group_image": chat.get("group_image")
                }

                if "dealer_id" in chat:
                    chat_info["dealer_id"] = chat["dealer_id"]

                # Debug print
                print(f"Chat info created: {chat_info}")
                
                chat_list.append(chat_info)

            # Sort by last activity
            chat_list.sort(key=lambda x: x["last_activity"], reverse=True)
            return chat_list

        except Exception as e:
            print(f"Error getting chats: {str(e)}")
            print(f"Full error details: ", e)
            return []

    async def mark_messages_as_delivered(
        self,
        chat_id: str,
        user_id: Union[int, str],
        user_type: str,
        message_ids: Optional[List[str]] = None
    ) -> bool:
        """Mark messages as delivered for a user"""
        try:
            # Base query for messages
            query = {
                "chat_id": chat_id,
                "sender_id": {"$ne": user_id},  # Don't mark own messages
                "delivered_to": {
                    "$not": {
                        "$elemMatch": {
                            "user_id": user_id,
                            "user_type": user_type
                        }
                    }
                }
            }

            # If specific message IDs are provided
            if message_ids:
                query["$or"] = [
                    {"_id": ObjectId(msg_id)} for msg_id in message_ids
                ] + [
                    {"message_id": msg_id} for msg_id in message_ids
                ]

            # Update messages
            result = await self.message_collection.update_many(
                query,
                {
                    "$addToSet": {
                        "delivered_to": {
                            "user_id": user_id,
                            "user_type": user_type,
                            "timestamp": datetime.utcnow()
                        }
                    }
                }
            )

            # Update unread count in chat
            participant_id = f"{user_type}_{user_id}"
            await self.chat_collection.update_one(
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

            return result.modified_count > 0

        except Exception as e:
            print(f"Error marking messages as delivered: {str(e)}")
            return False

    async def update_user_last_seen(
        self,
        user_id: Union[int, str],
        timestamp: datetime
    ) -> bool:
        """Update user's last seen timestamp"""
        try:
            result = await self.chat_collection.update_many(
                {"participants.id": user_id},
                {
                    "$set": {
                        "participants.$.last_seen": timestamp
                    }
                }
            )
            return result.modified_count > 0
        except Exception as e:
            print(f"Error updating last seen: {str(e)}")
            return False

    async def increment_unread_count(
        self,
        chat_id: str,
        sender_id: Union[int, str],
        sender_type: str
    ) -> None:
        """Increment unread count for all participants except sender"""
        try:
            chat = await self.get_chat_details(chat_id)
            if not chat:
                return

            # Get all participants except sender
            other_participants = [
                p for p in chat.get("participants", [])
                if str(p["id"]) != str(sender_id) or p["type"] != sender_type
            ]

            # Update unread counts
            updates = {}
            for participant in other_participants:
                participant_id = f"{participant['type']}_{participant['id']}"
                updates[f"unread_counts.{participant_id}"] = 1

            if updates:
                await self.chat_collection.update_one(
                    {"$or": [
                        {"_id": ObjectId(chat_id)},
                        {"chat_id": chat_id}
                    ]},
                    {
                        "$inc": updates
                    }
                )

        except Exception as e:
            print(f"Error incrementing unread count: {str(e)}")

    async def get_last_message(self, chat_id: str) -> Optional[Dict]:
        """Get the last message for a chat"""
        try:
            # Find the last message using chat_id field
            message = await self.message_collection.find_one(
                {
                    "$or": [
                        {"chat_id": chat_id},
                        {"chat_id": str(chat_id)}  # Try both ObjectId and string
                    ],
                    "is_deleted": {"$ne": True},
                    "deleted_for": {"$size": 0}  # Only get messages not deleted for anyone
                },
                sort=[("timestamp", -1)]  # Sort by timestamp descending
            )
            
            if message:
                # Convert ObjectId to string
                if isinstance(message.get("_id"), ObjectId):
                    message["_id"] = str(message["_id"])
                
                # Format the last message
                return {
                    "message_id": message.get("message_id", str(message["_id"])),
                    "content": message["content"],
                    "sender_id": message["sender_id"],
                    "sender_type": message["sender_type"],
                    "timestamp": message["timestamp"],
                    "message_type": message.get("message_type", "text"),
                    "attachment": message.get("attachment"),
                    "read_by": message.get("read_by", []),
                    "delivered_to": message.get("delivered_to", []),
                    "is_deleted": message.get("is_deleted", False)
                }
            
            return None

        except Exception as e:
            print(f"Error getting last message: {str(e)}")
            return None

    async def get_invite(self, invite_code: str) -> Optional[Dict]:
        """Get invite details if valid"""
        try:
            # Find invite
            invite = await self.invite_collection.find_one({
                "code": invite_code,
                "is_active": True,
                "expires_at": {"$gt": datetime.utcnow()}
            })
            
            if not invite:
                # Debug: Check why invite wasn't found
                all_invite = await self.invite_collection.find_one({"code": invite_code})
                if all_invite:
                    if not all_invite.get("is_active"):
                        print(f"Invite {invite_code} is not active")
                    elif all_invite.get("expires_at") <= datetime.utcnow():
                        print(f"Invite {invite_code} has expired")
                else:
                    print(f"No invite found with code {invite_code}")
                
            return invite
            
        except Exception as e:
            print(f"Error getting invite: {str(e)}")
            return None

    async def add_chat_participant(
        self,
        chat_id: str,
        user_id: int,
        user_type: str,
        role: str = "member"
    ) -> bool:
        """Add a new participant to a chat"""
        try:
            result = await self.chat_collection.update_one(
                {"_id": ObjectId(chat_id)},
                {
                    "$addToSet": {
                        "participants": {
                            "id": user_id,
                            "type": user_type,
                            "role": role,
                            "joined_at": datetime.utcnow()
                        }
                    }
                }
            )
            return result.modified_count > 0
        except Exception as e:
            print(f"Error adding participant: {str(e)}")
            return False

    async def mark_invite_used(
        self,
        invite_code: str,
        used_by: int
    ) -> bool:
        """Mark an invite as used"""
        try:
            result = await self.invite_collection.update_one(
                {"code": invite_code},
                {
                    "$set": {
                        "is_active": False,
                        "used_by": used_by,
                        "used_at": datetime.utcnow()
                    }
                }
            )
            return result.modified_count > 0
        except Exception as e:
            print(f"Error marking invite used: {str(e)}")
            return False

    async def update_group_settings(self, chat_id: str, settings: dict) -> bool:
        """Update group chat settings"""
        try:
            result = await self.chat_collection.update_one(
                {"_id": ObjectId(chat_id)},
                {
                    "$set": {
                        "settings.allow_member_invites": settings.get("allow_member_invites", False),
                        "settings.allow_member_adds": settings.get("allow_member_adds", False),
                        "settings.only_admins_message": settings.get("only_admins_message", False),
                        "settings.allow_admin_invites": settings.get("allow_admin_invites", True),
                        "settings.allow_user_invites": settings.get("allow_user_invites", False)
                    }
                }
            )
            
            if result.modified_count == 0:
                raise HTTPException(status_code=404, detail="Chat not found")
            
            return True
            
        except Exception as e:
            print(f"Error updating group settings: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to update group settings: {str(e)}"
            )

    async def toggle_message_reaction(
        self,
        message_id: str,
        user_id: int,
        emoji: str
    ) -> Dict:
        """Toggle emoji reaction on a message"""
        try:
            message = await self.get_message(message_id)
            if not message:
                raise ValueError("Message not found")
            
            reactions = message.get("reactions", {})
            emoji_reactions = reactions.get(emoji, [])
            
            # Check if user already reacted with this emoji
            existing_reaction = next(
                (r for r in emoji_reactions if r["user_id"] == user_id),
                None
            )
            
            if existing_reaction:
                # Remove reaction
                emoji_reactions.remove(existing_reaction)
            else:
                # Add reaction
                emoji_reactions.append({
                    "user_id": user_id,
                    "timestamp": datetime.utcnow()
                })
            
            if emoji_reactions:
                reactions[emoji] = emoji_reactions
            else:
                reactions.pop(emoji, None)
            
            # Update message
            await self.message_collection.update_one(
                {"_id": ObjectId(message_id)},
                {"$set": {"reactions": reactions}}
            )
            
            return {
                "message_id": message_id,
                "reactions": reactions
            }
            
        except Exception as e:
            print(f"Error toggling reaction: {str(e)}")
            raise ValueError(f"Failed to update reaction: {str(e)}")

    async def remove_group_member(
        self,
        chat_id: str,
        user_id: int,
        removed_by: Optional[int] = None,
        is_leaving: bool = False,
        reason: Optional[str] = None
    ) -> bool:
        """Remove a member from group"""
        try:
            removal_data = {
                "chat_id": chat_id,
                "user_id": user_id,
                "removed_by": removed_by,
                "is_leaving": is_leaving,
                "reason": reason,
                "removed_at": datetime.utcnow()
            }
            
            # Add to removed_members collection
            await self.removed_members_collection.insert_one(removal_data)
            
            # Update chat participants
            result = await self.chat_collection.update_one(
                {"_id": ObjectId(chat_id)},
                {
                    "$pull": {
                        "participants": {"id": user_id}
                    },
                    "$push": {
                        "removed_members": removal_data
                    }
                }
            )
            return result.modified_count > 0
        except Exception as e:
            print(f"Error removing member: {str(e)}")
            return False

    async def get_other_admins(self, chat_id: str, current_admin_id: int) -> List[Dict]:
        """Get other admins of the group"""
        try:
            chat = await self.get_chat(chat_id)
            if not chat:
                return []
            
            admins = [
                admin for admin in chat.get("settings", {}).get("group_admins", [])
                if str(admin["id"]) != str(current_admin_id)
            ]
            return admins
        except Exception as e:
            print(f"Error getting other admins: {str(e)}")
            return []

    async def block_user(
        self,
        blocker_id: int,
        blocked_id: int,
        reason: Optional[str] = None
    ) -> bool:
        """Block a user"""
        try:
            # Check if already blocked
            existing_block = await self.blocked_users_collection.find_one({
                "blocker_id": blocker_id,
                "blocked_id": blocked_id,
                "status": "active"
            })
            if existing_block:
                raise ValueError("User is already blocked")
            
            block_data = {
                "blocker_id": blocker_id,
                "blocked_id": blocked_id,
                "reason": reason,
                "blocked_at": datetime.utcnow(),
                "status": "active"
            }
            
            # Add to blocked_users collection
            await self.blocked_users_collection.insert_one(block_data)
            
            # Update chat settings
            result = await self.chat_collection.update_many(
                {"participants.id": {"$in": [blocker_id, blocked_id]}},
                {
                    "$push": {
                        "settings.blocked_users": block_data
                    }
                }
            )
            return True
        except Exception as e:
            print(f"Error blocking user: {str(e)}")
            raise ValueError(str(e))

    async def unblock_user(
        self,
        blocker_id: int,
        blocked_id: int,
        reason: Optional[str] = None
    ) -> bool:
        """Unblock a user"""
        try:
            # Update block status in blocked_users collection
            await self.blocked_users_collection.update_many(
                {
                    "blocker_id": blocker_id,
                    "blocked_id": blocked_id,
                    "status": "active"
                },
                {
                    "$set": {
                        "status": "inactive",
                        "unblocked_at": datetime.utcnow(),
                        "unblock_reason": reason
                    }
                }
            )
            
            # Remove from chat settings
            result = await self.chat_collection.update_many(
                {"participants.id": {"$in": [blocker_id, blocked_id]}},
                {
                    "$pull": {
                        "settings.blocked_users": {
                            "blocker_id": blocker_id,
                            "blocked_id": blocked_id
                        }
                    }
                }
            )
            return True
        except Exception as e:
            print(f"Error unblocking user: {str(e)}")
            return False

    async def create_user_report(
        self,
        reporter_id: int,
        reported_id: int,
        report_type: str,
        reason: str,
        description: Optional[str] = None
    ) -> str:
        """Create a user report"""
        try:
            report_data = {
                "reporter_id": reporter_id,
                "reported_id": reported_id,
                "report_type": report_type,
                "reason": reason,
                "description": description,
                "status": "pending",
                "created_at": datetime.utcnow()
            }
            
            result = await self.report_collection.insert_one(report_data)
            return str(result.inserted_id)
        except Exception as e:
            print(f"Error creating report: {str(e)}")
            raise ValueError(f"Failed to create report: {str(e)}")

    async def edit_message(
        self,
        message_id: str,
        new_content: str,
        edited_reason: Optional[str] = None
    ) -> Dict:
        """Edit a message"""
        try:
            # Get original message
            original_message = await self.get_message(message_id)
            if not original_message:
                raise ValueError("Message not found")
            
            # Don't allow editing of deleted messages
            if original_message.get("is_deleted", False):
                raise ValueError("Cannot edit deleted messages")
            
            # Create edit history entry
            edit_entry = {
                "previous_content": original_message["content"],
                "edited_at": datetime.utcnow(),
                "reason": edited_reason
            }
            
            # Get existing history or initialize new
            edit_history = original_message.get("edit_history", [])
            edit_history.append(edit_entry)
            
            # Update message
            update_data = {
                "content": new_content,
                "is_edited": True,
                "last_edited_at": datetime.utcnow(),
                "edit_history": edit_history
            }
            
            result = await self.message_collection.update_one(
                {"_id": ObjectId(message_id)},
                {"$set": update_data}
            )
            
            if result.modified_count == 0:
                raise ValueError("Message not found or not modified")
            
            # Get and return updated message
            updated_message = await self.get_message(message_id)
            return {
                **updated_message,
                "edit_details": {
                    "previous_content": edit_entry["previous_content"],
                    "edited_at": edit_entry["edited_at"],
                    "reason": edit_entry["reason"]
                }
            }
            
        except Exception as e:
            print(f"Error editing message: {str(e)}")
            raise ValueError(f"Failed to edit message: {str(e)}")

    async def is_user_blocked(self, user_id: int, by_user_id: int) -> bool:
        """Check if a user is blocked"""
        try:
            block = await self.blocked_users_collection.find_one({
                "blocker_id": by_user_id,
                "blocked_id": user_id,
                "status": "active"
            })
            return bool(block)
        except Exception as e:
            print(f"Error checking block status: {str(e)}")
            return False

    async def get_block_history(self, user_id: int) -> List[Dict]:
        """Get block history for a user"""
        try:
            blocks = await self.blocked_users_collection.find({
                "$or": [
                    {"blocker_id": user_id},
                    {"blocked_id": user_id}
                ]
            }).to_list(length=None)
            return blocks
        except Exception as e:
            print(f"Error getting block history: {str(e)}")
            return []

    async def share_gem_in_chat(
        self,
        chat_id: str,
        gem_id: int,
        sender_id: int,
        db: Session
    ):
        """Share a gem in a chat"""
        try:
            # Get gem details directly from the database
            gem = db.query(Gem).filter(Gem.gem_id == gem_id).first()
            if not gem:
                raise ValueError("Gem not found")

            # Calculate total expenses
            total_expenses = sum(expense.amount for expense in gem.expenses)
            full_cost = gem.cost + total_expenses

            # Create gem details dictionary
            gem_details = {
                "gem_id": gem.gem_id,
                "name": gem.name,
                "category": gem.category,
                "sub_category": gem.sub_category,
                "sell_price": gem.sell_price,
                "description": gem.description,
                "images": gem.images,
                "total_expenses": total_expenses,
                "full_cost": full_cost
            }

            # Create message
            message = ChatMessage(
                chat_id=chat_id,
                sender_id=sender_id,
                sender_type="user",
                content=f"Shared gem: {gem.name}",
                message_type="gem",
                gem_id=gem_id,
                gem_details=gem_details
            )

            message_id = await self.add_message(message)
            return message_id
            
        except Exception as e:
            print(f"Error sharing gem: {str(e)}")
            raise ValueError(f"Failed to share gem: {str(e)}")

    async def get_unread_count(
        self,
        chat_id: str,
        user_id: Union[int, str]
    ) -> int:
        """Get unread message count for a user in a chat"""
        try:
            unread_count = await self.message_collection.count_documents({
                "chat_id": chat_id,
                "sender_id": {"$ne": user_id},
                "read_by": {
                    "$not": {
                        "$elemMatch": {
                            "user_id": {"$eq": user_id}
                        }
                    }
                }
            })
            return unread_count
        except Exception as e:
            print(f"Error getting unread count: {str(e)}")
            return 0

    async def get_existing_dealer_chat(
        self,
        user_id: Union[int, str],
        dealer_id: Union[int, str]
    ) -> Optional[str]:
        """Check if a chat already exists between user and dealer"""
        try:
            # Convert IDs to integers for consistent comparison
            user_id_int = int(user_id)
            dealer_id_int = int(dealer_id)

            # Find chat where both users are participants
            existing_chat = await self.chat_collection.find_one({
                "chat_type": "dealer_chat",
                "is_active": True,
                "$and": [
                    {
                        "participants": {
                            "$elemMatch": {
                                "id": user_id_int,
                                "type": "user"
                            }
                        }
                    },
                    {
                        "participants": {
                            "$elemMatch": {
                                "id": dealer_id_int,
                                "type": "user"
                            }
                        }
                    }
                ]
            })

            if existing_chat:
                print(f"Found existing chat: {existing_chat['_id']}")  # Debug print
                return str(existing_chat["_id"])
            
            print(f"No existing chat found for user {user_id_int} and dealer {dealer_id_int}")  # Debug print
            return None

        except Exception as e:
            print(f"Error checking existing chat: {str(e)}")
            return None

    async def mark_messages_as_read(
        self,
        chat_id: str,
        user_id: Union[int, str],
        user_type: str,
        message_id: Optional[str] = None
    ) -> bool:
        """Mark specific message as read"""
        try:
            query = {
                "chat_id": chat_id,
                "sender_id": {"$ne": user_id},
                "read_by": {
                    "$not": {
                        "$elemMatch": {
                            "user_id": user_id,
                            "user_type": user_type
                        }
                    }
                }
            }

            if message_id:
                query["_id"] = ObjectId(message_id)

            result = await self.message_collection.update_many(
                query,
                {
                    "$addToSet": {
                        "read_by": {
                            "user_id": user_id,
                            "user_type": user_type,
                            "timestamp": datetime.utcnow()
                        }
                    }
                }
            )

            return result.modified_count > 0
        except Exception as e:
            print(f"Error marking messages as read: {str(e)}")
            return False

    async def get_unread_count(self, chat_info: Dict, user_id: Union[int, str]) -> int:
        """Get correct unread count for the current user"""
        try:
            # Convert user_id to string for comparison
            user_id_str = str(user_id)
            
            # Check unread_counts field first
            unread_counts = chat_info.get('unread_counts', {})
            
            # Try different possible keys for unread counts
            possible_keys = [
                f"user_{user_id_str}",  # format: user_1
                user_id_str,            # format: 1
                f"{user_id_str}"        # format: "1"
            ]
            
            for key in possible_keys:
                if key in unread_counts:
                    return unread_counts[key]
            
            return 0
            
        except Exception as e:
            print(f"Error getting unread count: {str(e)}")
            return 0

    async def get_chat_list(self, user_id: Union[int, str]) -> List[Dict]:
        """Get list of chats with correct unread counts and last messages"""
        try:
            # Find all chats where user is a participant
            cursor = self.chat_collection.find({
                "participants": {
                    "$elemMatch": {
                        "id": int(user_id)
                    }
                }
            }).sort("last_activity", -1)

            chats = []
            async for chat in cursor:
                try:
                    # Format basic chat info
                    chat_info = {
                        "chat_id": str(chat["_id"]),
                        "chat_type": chat["chat_type"],
                        "title": chat.get("title", ""),
                        "dealer_id": chat.get("dealer_id"),
                        "created_at": chat["created_at"],
                        "last_activity": chat["last_activity"],
                        "participants": chat["participants"],
                        "unread_count": await self.get_unread_count(chat, user_id)
                    }

                    # Add last message if exists
                    if last_message := chat.get("last_message"):
                        chat_info["last_message"] = {
                            "message_id": last_message["message_id"],
                            "content": last_message["content"],
                            "sender_id": last_message["sender_id"],
                            "sender_type": last_message["sender_type"],
                            "timestamp": last_message["timestamp"],
                            "message_type": last_message.get("message_type", "text"),
                            "is_from_me": str(last_message["sender_id"]) == str(user_id)
                        }

                    chats.append(chat_info)

                except Exception as e:
                    print(f"Error processing chat {chat.get('_id')}: {str(e)}")
                    continue

            return chats

        except Exception as e:
            print(f"Error getting chat list: {str(e)}")
            return []
