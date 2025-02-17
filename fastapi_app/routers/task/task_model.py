from datetime import datetime
from typing import Optional, List
from bson import ObjectId
from ...models.mongo_modles import Task
from ...database import get_mongo_collection
from fastapi import Depends, HTTPException
from fastapi_app.routers.auth import get_current_user

class TaskModel:
    collection = get_mongo_collection("tasks")

    @staticmethod
    async def create_task(
        user_id: int,
        title: str,
        description: Optional[str],
        type: str,
        priority: str,
        category: str,
        related_transaction_id: Optional[int],
        due_date: Optional[datetime]
    ) -> dict:
        task = Task(
            task_id=str(ObjectId()),
            user_id=user_id,
            title=title,
            description=description,
            type=type,
            priority=priority,
            category=category,
            related_transaction_id=related_transaction_id,
            due_date=due_date,
            is_completed=False,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        result = await TaskModel.collection.insert_one(task.dict())
        created_task = await TaskModel.collection.find_one({"_id": result.inserted_id})
        if created_task:
            created_task["task_id"] = str(created_task.pop("_id"))
        return created_task

    @staticmethod
    async def get_user_tasks(
        user_id: int,
        is_completed: Optional[bool] = None,
        priority: Optional[str] = None,
        category: Optional[str] = None
    ) -> List[dict]:
        query = {"user_id": user_id}
        
        if is_completed is not None:
            query["is_completed"] = is_completed
        if priority:
            query["priority"] = priority
        if category:
            query["category"] = category

        tasks = await TaskModel.collection.find(query).to_list(length=None)
        for task in tasks:
            task["task_id"] = str(task.pop("_id"))
        return tasks

    @staticmethod
    async def update_task(task_id: str, user_id: int, is_completed: bool) -> Optional[dict]:
        query = {
            "_id": ObjectId(task_id),
            "user_id": user_id
        }
        
        update = {
            "$set": {
                "is_completed": is_completed,
                "updated_at": datetime.utcnow()
            }
        }

        result = await TaskModel.collection.find_one_and_update(
            query,
            update,
            return_document=True
        )

        if result:
            result["task_id"] = str(result.pop("_id"))
            return result
        return None

    @staticmethod
    async def delete_task(task_id: str, user_id: int) -> bool:
        result = await TaskModel.collection.delete_one({
            "_id": ObjectId(task_id),
            "user_id": user_id
        })
        return result.deleted_count > 0

    @staticmethod
    async def get_overdue_tasks(user_id: int) -> List[dict]:
        query = {
            "user_id": user_id,
            "due_date": {"$lt": datetime.utcnow()},
            "is_completed": False
        }
        
        tasks = await TaskModel.collection.find(query).to_list(length=None)
        for task in tasks:
            task["task_id"] = str(task.pop("_id"))
        return tasks 