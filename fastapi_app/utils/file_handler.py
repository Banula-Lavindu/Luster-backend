from fastapi import UploadFile, File
import os
from datetime import datetime
from typing import Optional
import aiofiles
import magic
from PIL import Image
import io
import uuid

class FileHandler:
    UPLOAD_DIR = "uploads/chat_attachments"
    ALLOWED_EXTENSIONS = {
        'image': ['jpg', 'jpeg', 'png', 'gif'],
        'document': ['pdf', 'doc', 'docx', 'txt'],
        'audio': ['mp3', 'wav', 'ogg'],
        'video': ['mp4', 'avi', 'mov']
    }
    
    def __init__(self):
        self.upload_dir = "uploads"
        os.makedirs(self.upload_dir, exist_ok=True)

    @staticmethod
    async def save_chat_attachment(
        file: UploadFile,
        chat_id: str,
        user_id: int
    ) -> dict:
        """Save a chat attachment and return its details"""
        
        # Create directory if it doesn't exist
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        file_dir = os.path.join(FileHandler.UPLOAD_DIR, chat_id)
        os.makedirs(file_dir, exist_ok=True)
        
        # Get file extension and generate filename
        file_ext = file.filename.split('.')[-1].lower()
        filename = f"{user_id}_{timestamp}.{file_ext}"
        file_path = os.path.join(file_dir, filename)
        
        # Save file
        async with aiofiles.open(file_path, 'wb') as f:
            content = await file.read()
            await f.write(content)
        
        # Get file type and size
        mime_type = magic.from_file(file_path, mime=True)
        file_size = os.path.getsize(file_path)
        
        # Generate thumbnail for images
        thumbnail_path = None
        if mime_type.startswith('image/'):
            thumbnail_path = await FileHandler.create_thumbnail(file_path)
        
        return {
            "file_name": file.filename,
            "file_path": file_path,
            "file_size": file_size,
            "mime_type": mime_type,
            "thumbnail_path": thumbnail_path
        }
    
    @staticmethod
    async def create_thumbnail(image_path: str, size=(128, 128)) -> Optional[str]:
        """Create a thumbnail for an image"""
        try:
            thumbnail_dir = os.path.join(os.path.dirname(image_path), 'thumbnails')
            os.makedirs(thumbnail_dir, exist_ok=True)
            
            thumbnail_path = os.path.join(
                thumbnail_dir,
                f"thumb_{os.path.basename(image_path)}"
            )
            
            with Image.open(image_path) as img:
                img.thumbnail(size)
                img.save(thumbnail_path)
            
            return thumbnail_path
        except Exception:
            return None 

    async def save_file(self, file: UploadFile, path: str) -> Optional[str]:
        try:
            # Create full path
            full_path = os.path.join(self.upload_dir, path)
            
            # Ensure directory exists
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            
            # Save file
            async with aiofiles.open(full_path, 'wb') as f:
                content = await file.read()
                await f.write(content)
            
            return f"/uploads/{path}"
        except Exception as e:
            print(f"Error saving file: {str(e)}")
            return None

    async def delete_file(self, file_path: str) -> bool:
        try:
            full_path = os.path.join(self.upload_dir, file_path.lstrip('/uploads/'))
            if os.path.exists(full_path):
                os.remove(full_path)
                return True
            return False
        except Exception as e:
            print(f"Error deleting file: {str(e)}")
            return False

file_handler = FileHandler() 