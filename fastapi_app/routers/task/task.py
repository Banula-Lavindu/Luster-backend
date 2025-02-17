from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel, Field
from typing import Optional, List
from fastapi_app.routers.task.task_model import TaskModel
from datetime import datetime
from enum import Enum
from fastapi_app.routers.auth import get_current_user
from sqlalchemy.orm import Session
from ...database import get_db
from ...models.models import User

# Define the router
router = APIRouter(prefix="/task", tags=["Task"])

# Define task priority and category enums
class TaskPriority(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

class TaskType(str, Enum):
    DEAL = "deal"
    MAINTENANCE = "maintenance"
    REMINDER = "reminder"
    OTHER = "other"

class TaskCategory(str, Enum):
    GEM = "gem"
    DEALER = "dealer"
    TRANSACTION = "transaction"
    OTHER = "other"

# Pydantic models for request and response validation
class CreateTaskRequest(BaseModel):
    title: str = Field(..., description="Title of the task", max_length=255)
    description: Optional[str] = Field(None, description="Description of the task")
    type: TaskType = Field(..., description="Type of task")
    priority: TaskPriority = Field(..., description="Priority of the task")
    category: TaskCategory = Field(..., description="Category of the task")
    related_transaction_id: Optional[int] = Field(None, description="Related transaction ID")
    due_date: Optional[datetime] = Field(None, description="Due date for the task")

class UpdateTaskRequest(BaseModel):
    is_completed: bool = Field(..., description="Task completion status")

class TaskResponse(BaseModel):
    task_id: str
    user_id: int
    title: str
    description: Optional[str]
    type: str
    priority: str
    category: str
    related_transaction_id: Optional[int]
    due_date: Optional[datetime]
    is_completed: bool
    created_at: datetime
    updated_at: datetime

# Create a new task
@router.post("/", response_model=TaskResponse)
async def create_task(
    request: CreateTaskRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    task = await TaskModel.create_task(
        user_id=current_user.user_id,
        title=request.title,
        description=request.description,
        type=request.type.value,
        priority=request.priority.value,
        category=request.category.value,
        related_transaction_id=request.related_transaction_id,
        due_date=request.due_date
    )
    return task

# Get all tasks for current user
@router.get("/", response_model=List[TaskResponse])
async def get_tasks(
    is_completed: Optional[bool] = Query(None, description="Filter by completion status"),
    priority: Optional[TaskPriority] = Query(None, description="Filter by priority"),
    category: Optional[TaskCategory] = Query(None, description="Filter by category"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    tasks = await TaskModel.get_user_tasks(
        user_id=current_user.user_id,
        is_completed=is_completed,
        priority=priority.value if priority else None,
        category=category.value if category else None
    )
    return tasks

# Update task completion status
@router.put("/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: str,
    request: UpdateTaskRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    task = await TaskModel.update_task(
        task_id=task_id,
        user_id=current_user.user_id,
        is_completed=request.is_completed
    )
    if not task:
        raise HTTPException(status_code=404, detail="Task not found or unauthorized")
    return task

# Delete a task
@router.delete("/{task_id}")
async def delete_task(
    task_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    result = await TaskModel.delete_task(
        task_id=task_id,
        user_id=current_user.user_id
    )
    if not result:
        raise HTTPException(status_code=404, detail="Task not found or unauthorized")
    return {"message": "Task deleted successfully"}

# Get overdue tasks for current user
@router.get("/overdue", response_model=List[TaskResponse])
async def get_overdue_tasks(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    tasks = await TaskModel.get_overdue_tasks(user_id=current_user.user_id)
    return tasks
