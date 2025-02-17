import os
from datetime import datetime
from fastapi import UploadFile, HTTPException
from PIL import Image, UnidentifiedImageError

async def save_uploaded_file(
    file: UploadFile,
    destination_folder: str,
    user_id: str,
    file_naming_format: str = "timestamp_userid_original",
    max_width: int = 500,
    max_height: int = 500,
) -> str:
    """Save an uploaded file with optional resizing and cropping."""
    try:
        os.makedirs(destination_folder, exist_ok=True)

        file_extension = os.path.splitext(file.filename)[-1].lower()
        if not file_extension:
            raise HTTPException(status_code=400, detail="File must have a valid extension.")

        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        if file_naming_format == "timestamp_userid_original":
            filename = f"{timestamp}_{user_id}_{file.filename}"
        elif file_naming_format == "timestamp_userid":
            filename = f"{timestamp}_{user_id}{file_extension}"
        elif file_naming_format == "timestamp_original":
            filename = f"{timestamp}_{file.filename}"
        elif file_naming_format == "original":
            filename = file.filename
        else:
            raise HTTPException(status_code=400, detail="Invalid file_naming_format")

        file_path = os.path.join(destination_folder, filename)

        with open(file_path, "wb") as f:
            f.write(await file.read())

        if file.content_type.startswith("image/"):
            try:
                with Image.open(file_path) as img:
                    img.thumbnail((max_width, max_height))
                    img.save(file_path)
            except UnidentifiedImageError:
                os.remove(file_path)
                raise HTTPException(status_code=400, detail="Uploaded file is not a valid image.")

        return file_path

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")