from sqlalchemy.orm import Session
from fastapi_app.database import get_mongo_collection
from fastapi_app.models.models import Gem, NonUserTransaction
from fastapi_app.models.mongo_modles import GemLifetimeTrace, Task, NonUserGem
from datetime import datetime

# MongoDB collections
tasks_collection = get_mongo_collection("tasks")
gem_traces_collection = get_mongo_collection("gem_lifetime_traces")
non_user_gems_collection = get_mongo_collection("non_user_gems")

async def process_buy_request(dealer_id: int, gem_data: dict, transaction_type: str, fulfillment_date: datetime, db: Session, current_user: int):
    # Check if dealer is created with QR
    dealer = await get_mongo_collection("dealers").find_one({"dealer_id": dealer_id, "created_withqr": False})
    if not dealer:
        raise ValueError("Dealer not eligible for this operation")

    # Verify that the dealer is associated with the current user
    user_dealer_relationship = await get_mongo_collection("dealers").find_one({"owner_id": current_user, "dealer_id": dealer_id})
    if not user_dealer_relationship:
        raise ValueError("This dealer is not associated with the current user")

    # Add new gem to the SQL database
    new_gem = Gem(
        user_id=current_user,
        name=gem_data["name"],
        category=gem_data["category"],
        sub_category=gem_data.get("sub_category"),
        cost=gem_data["cost"],
        sell_price=gem_data["sell_price"],
        description=gem_data.get("description"),
        images=gem_data.get("images", [])
    )
    db.add(new_gem)
    db.commit()
    db.refresh(new_gem)

    # Update GemLifetimeTrace in MongoDB
    gem_trace = GemLifetimeTrace(
        gem_id=new_gem.gem_id,
        user_id=dealer_id,
        name=new_gem.name,
        category=new_gem.category,
        sub_category=new_gem.sub_category,
        cost=new_gem.cost,
        sell_price=new_gem.sell_price,
        description=new_gem.description,
        images=new_gem.images,
        transactions=[],
        expenses=[],
        ownership_history=[{
            "user_id": dealer_id,
            "transaction_id": None,
            "timestamp": datetime.utcnow()
        }]
    )
    await gem_traces_collection.insert_one(gem_trace.dict())

    # Create a non-user transaction
    non_user_transaction = NonUserTransaction(
        seller_id=dealer_id,
        buyer_id=current_user,
        gem_id=new_gem.gem_id,
        amount=new_gem.cost,
        payment_type=transaction_type,
        fulfillment_date=fulfillment_date,
        transaction_status="completed" if fulfillment_date <= datetime.utcnow() else "pending",
        transaction_type="non_user"
    )
    db.add(non_user_transaction)
    db.commit()

    # Add a task if the fulfillment date is in the future
    if fulfillment_date > datetime.utcnow():
        task = Task(
            user_id=current_user,
            title="Fulfillment Reminder",
            description=f"Reminder to fulfill transaction for gem {new_gem.name}.",
            type="reminder",
            priority="medium",
            category="transaction",
            related_transaction_id=non_user_transaction.transaction_id,
            due_date=fulfillment_date,
            is_completed=False,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        await tasks_collection.insert_one(task.dict())

    return new_gem.gem_id

async def process_sell_request(gem_id: int, dealer_id: int, sell_price: float, fulfillment_date: datetime, db: Session, current_user: int):
    # Verify gem ownership
    gem = db.query(Gem).filter(Gem.gem_id == gem_id, Gem.user_id == current_user).first()
    if not gem:
        raise ValueError("Gem not found or not owned by you")

    # Verify dealer relationship
    user_dealer_relationship = await get_mongo_collection("dealers").find_one({"owner_id": current_user, "dealer_id": dealer_id})
    if not user_dealer_relationship:
        raise ValueError("This dealer is not associated with the current user")

    # Add gem to NonUserGem
    non_user_gem = NonUserGem(
        gem_id=gem.gem_id,
        dealer_id=dealer_id,
        name=gem.name,
        category=gem.category,
        sub_category=gem.sub_category,
        cost=gem.cost,
        sell_price=sell_price,
        description=gem.description,
        images=gem.images
    )
    await non_user_gems_collection.insert_one(non_user_gem.dict())

    # Update GemLifetimeTrace in MongoDB
    await gem_traces_collection.update_one(
        {"gem_id": gem.gem_id},
        {"$set": {"user_id": dealer_id, "sell_price": sell_price}}
    )

    # Create a non-user transaction
    non_user_transaction = NonUserTransaction(
        seller_id=current_user,
        buyer_id=dealer_id,
        gem_id=gem.gem_id,
        amount=sell_price,
        payment_type="sell",
        fulfillment_date=fulfillment_date,
        transaction_status="completed" if fulfillment_date <= datetime.utcnow() else "pending",
        transaction_type="non_user"
    )
    db.add(non_user_transaction)
    db.commit()

    # Add a task if the fulfillment date is in the future
    if fulfillment_date > datetime.utcnow():
        task = Task(
            user_id=current_user,
            title="Upcoming Transaction Reminder",
            description=f"Reminder to fulfill transaction for gem {gem.name}.",
            type="reminder",
            priority="medium",
            category="transaction",
            related_transaction_id=non_user_transaction.transaction_id,
            due_date=fulfillment_date,
            is_completed=False,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        await tasks_collection.insert_one(task.dict())

    # Remove gem from Gem model
    db.delete(gem)
    db.commit()

    return {"gem_id": gem.gem_id, "transaction_id": non_user_transaction.transaction_id}

async def get_pending_transactions(db: Session, current_user: int):
    # Fetch pending transactions for the current user
    transactions = db.query(NonUserTransaction).filter(
        NonUserTransaction.seller_id == current_user,
        NonUserTransaction.transaction_status == "pending"
    ).all()
    return [transaction.to_dict() for transaction in transactions]

async def complete_transaction(transaction_id: int, db: Session, current_user: int):
    # Complete a pending transaction
    transaction = db.query(NonUserTransaction).filter(
        NonUserTransaction.transaction_id == transaction_id,
        NonUserTransaction.seller_id == current_user,
        NonUserTransaction.transaction_status == "pending"
    ).first()

    if not transaction:
        raise ValueError("Transaction not found or already completed")

    transaction.transaction_status = "completed"
    db.commit()

    # Update task status if any
    await tasks_collection.update_many(
        {"related_transaction_id": transaction_id},
        {"$set": {"is_completed": True, "updated_at": datetime.utcnow()}}
    )

    return {"transaction_id": transaction_id, "status": "completed"} 