from fastapi_app.models.mongo_modles import DealRequest, DealStatus, DealNotification, Task, GemLifetimeTrace
from fastapi_app.models.models import Gem, Transaction
from fastapi_app.database import get_mongo_collection
from sqlalchemy.orm import Session
from datetime import datetime
from bson import ObjectId
from typing import List, Dict, Optional, Union, Tuple

# MongoDB collections - using a single collection for all deals
deals_collection = get_mongo_collection("deals")
notifications_collection = get_mongo_collection("notifications")
tasks_collection = get_mongo_collection("tasks")
gem_traces_collection = get_mongo_collection("gem_lifetime_traces")


class DealService:
    @staticmethod
    async def create_deal_task(user_id: int, deal_id: str, gem_id: int, due_date: datetime):
        """Create a task for a deal with a future fulfillment date."""
        task = Task(
            task_id=str(ObjectId()),
            user_id=user_id,
            title="Deal Fulfillment Reminder",
            description=f"Reminder to fulfill deal {deal_id} for gem {gem_id}.",
            type="reminder",
            priority="medium",
            category="deal",
            related_transaction_id=deal_id,
            due_date=due_date,
            is_completed=False,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        await tasks_collection.insert_one(task.dict())

    @staticmethod
    async def create_request(request, current_user, db: Session, request_type: str = "buy"):
        """Create a new buy/sell request"""
        # Verify gem availability/ownership
        if request_type == "buy":
            gem = db.query(Gem).filter(
                Gem.gem_id == request.gem_id,
                Gem.user_id == request.counterparty_id  # seller_id
            ).first()
            if not gem:
                raise ValueError("Gem not found or not available for sale")
            seller_id = request.counterparty_id
            buyer_id = current_user.user_id
        else:
            gem = db.query(Gem).filter(
                Gem.gem_id == request.gem_id,
                Gem.user_id == current_user.user_id
            ).first()
            if not gem:
                raise ValueError("Gem not found or not owned by you")
            seller_id = current_user.user_id
            buyer_id = request.counterparty_id

        # Create request
        deal_request = DealRequest(
            gem_id=request.gem_id,
            seller_id=seller_id,
            buyer_id=buyer_id,
            initial_price=request.price,
            current_price=request.price,
            payment_method=request.payment_method,
            fulfillment_date=request.fulfillment_date,
            last_action_by=current_user.user_id,
            request_type=request_type,  # Add request type to distinguish between buy/sell
            notes=request.notes,
            status=DealStatus.PENDING,
            negotiation_history=[{
                "price": request.price,
                "payment_method": request.payment_method,
                "date": request.fulfillment_date,
                "proposed_by": current_user.user_id,
                "timestamp": datetime.utcnow()
            }],
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        # Insert request
        result = await deals_collection.insert_one(deal_request.dict())
        request_id = str(result.inserted_id)

        # Create notification
        notify_user_id = seller_id if request_type == "buy" else buyer_id
        notification = DealNotification(
            deal_id=request_id,
            user_id=notify_user_id,
            type=f"new_{request_type}_request",
            content=f"New {request_type} request for gem {gem.name}",
            request_type=request_type,
            gem_name=gem.name,
            gem_image=gem.images[0] if gem.images else None
        )
        await notifications_collection.insert_one(notification.dict())

        # Create task if fulfillment date is not today
        if request.fulfillment_date.date() != datetime.utcnow().date():
            await DealService.create_deal_task(
                user_id=current_user.user_id,
                deal_id=request_id,
                gem_id=request.gem_id,
                due_date=request.fulfillment_date
            )

        return request_id

    @staticmethod
    async def negotiate_request(request_id: str, request, current_user, request_type: str = "buy"):
        """Counter-offer or negotiate a request"""
        deal_request = await deals_collection.find_one({
            "_id": ObjectId(request_id),
            "request_type": request_type
        })
        
        if not deal_request:
            raise ValueError(f"{request_type.capitalize()} request not found")

        if current_user.user_id not in [deal_request["seller_id"], deal_request["buyer_id"]]:
            raise ValueError("Not authorized")

        negotiation_entry = {
            "price": request.price,
            "payment_method": request.payment_method,
            "date": request.fulfillment_date,
            "proposed_by": current_user.user_id,
            "timestamp": datetime.utcnow()
        }

        await deals_collection.update_one(
            {"_id": ObjectId(request_id)},
            {
                "$set": {
                    "current_price": request.price,
                    "payment_method": request.payment_method,
                    "fulfillment_date": request.fulfillment_date,
                    "status": DealStatus.NEGOTIATING,
                    "last_action_by": current_user.user_id,
                    "updated_at": datetime.utcnow()
                },
                "$push": {
                    "negotiation_history": negotiation_entry
                }
            }
        )

        # Create notification for other party
        notify_user_id = deal_request["buyer_id"] if current_user.user_id == deal_request["seller_id"] else deal_request["seller_id"]
        
        # Fetch gem details
        gem = await get_mongo_collection("gems").find_one({"gem_id": deal_request["gem_id"]})
        
        notification = DealNotification(
            deal_id=request_id,
            user_id=notify_user_id,
            type="counter_offer",
            content=f"New counter offer: {request.price} {request.payment_method}",
            request_type=request_type,
            gem_name=gem["name"] if gem else None,
            gem_image=gem["images"][0] if gem and gem.get("images") else None
        )
        await notifications_collection.insert_one(notification.dict())

    @staticmethod
    async def update_gem_lifetime_trace(
        gem_id: int,
        transaction: Transaction,
        gem: Gem,
        db: Session
    ):
        """Update or create gem lifetime trace"""
        try:
            existing_trace = await gem_traces_collection.find_one({"gem_id": gem_id})
            
            if existing_trace:
                # Update existing trace
                update_data = {
                    "$set": {
                        "user_id": gem.user_id,
                        "sell_price": transaction.amount,
                        "description": gem.description,
                        "images": gem.images
                    },
                    "$push": {
                        "transactions": transaction.transaction_id,
                        "ownership_history": {
                            "user_id": gem.user_id,
                            "transaction_id": transaction.transaction_id,
                            "timestamp": datetime.utcnow(),
                            "price": transaction.amount,
                            "payment_type": transaction.payment_type
                        }
                    }
                }
                await gem_traces_collection.update_one(
                    {"gem_id": gem_id},
                    update_data
                )
            else:
                # Create new trace
                new_trace = GemLifetimeTrace(
                    gem_id=gem_id,
                    user_id=gem.user_id,
                    name=gem.name,
                    category=gem.category,
                    sub_category=gem.sub_category,
                    cost=gem.cost,
                    sell_price=transaction.amount,
                    description=gem.description,
                    images=gem.images,
                    transactions=[transaction.transaction_id],
                    expenses=[expense.expense_id for expense in gem.expenses],
                    ownership_history=[{
                        "user_id": gem.user_id,
                        "transaction_id": transaction.transaction_id,
                        "timestamp": datetime.utcnow(),
                        "price": transaction.amount,
                        "payment_type": transaction.payment_type
                    }]
                )
                await gem_traces_collection.insert_one(new_trace.dict())

        except Exception as e:
            print(f"Error updating gem lifetime trace: {str(e)}")
            raise

    @staticmethod
    async def create_transaction(
        deal_request: dict,
        db: Session,
        status: str = "completed"
    ) -> Transaction:
        """Create a transaction record"""
        try:
            transaction = Transaction(
                seller_id=deal_request["seller_id"],
                buyer_id=deal_request["buyer_id"],
                gem_id=deal_request["gem_id"],
                amount=deal_request["current_price"],
                payment_type=deal_request["payment_method"],
                fulfillment_date=datetime.fromisoformat(deal_request["fulfillment_date"]),
                transaction_status=status,
                transaction_type="direct_sell"
            )
            
            db.add(transaction)
            db.commit()
            db.refresh(transaction)
            
            return transaction
        except Exception as e:
            db.rollback()
            raise ValueError(f"Error creating transaction: {str(e)}")

    @staticmethod
    async def accept_request(
        request_id: str,
        current_user,
        db: Session,
        request_type: str = "buy"
    ) -> Tuple[int, Transaction]:
        """Accept a request and handle all related updates"""
        try:
            # Get deal request
            deal_request = await deals_collection.find_one({
                "_id": ObjectId(request_id),
                "request_type": request_type
            })
            
            if not deal_request:
                raise ValueError(f"{request_type.capitalize()} request not found")

            if current_user.user_id not in [deal_request["seller_id"], deal_request["buyer_id"]]:
                raise ValueError("Not authorized")

            # Create transaction
            transaction = await DealService.create_transaction(deal_request, db)

            # Update gem ownership
            gem = db.query(Gem).filter(Gem.gem_id == deal_request["gem_id"]).first()
            if gem:
                gem.user_id = deal_request["buyer_id"]
                gem.cost = deal_request["current_price"]
                gem.sell_price = None
                db.commit()

                # Update gem lifetime trace
                await DealService.update_gem_lifetime_trace(
                    gem_id=gem.gem_id,
                    transaction=transaction,
                    gem=gem,
                    db=db
                )

            # Update deal status
            await deals_collection.update_one(
                {"_id": ObjectId(request_id)},
                {
                    "$set": {
                        "status": DealStatus.COMPLETED,
                        "updated_at": datetime.utcnow(),
                        "last_action_by": current_user.user_id
                    }
                }
            )

            # Create notification
            notification = DealNotification(
                deal_id=request_id,
                user_id=deal_request["seller_id"] if current_user.user_id == deal_request["buyer_id"] else deal_request["buyer_id"],
                type="accepted",
                content=f"{request_type.capitalize()} request has been accepted",
                request_type=request_type,
                gem_name=gem.name if gem else None,
                gem_image=gem.images[0] if gem and gem.images else None
            )
            await notifications_collection.insert_one(notification.dict())

            return gem.gem_id, transaction

        except Exception as e:
            db.rollback()
            raise ValueError(f"Error accepting request: {str(e)}")

    @staticmethod
    async def get_user_requests(user_id: int, request_type: str = "all") -> List[dict]:
        """Get all requests for a user"""
        try:
            query = {
                "$or": [
                    {"buyer_id": user_id},
                    {"seller_id": user_id}
                ]
            }
            
            # Add request_type filter if specified
            if request_type != "all":
                query["request_type"] = request_type

            cursor = deals_collection.find(query).sort("created_at", -1)
            requests = await cursor.to_list(length=None)
            
            for request in requests:
                request["_id"] = str(request["_id"])
            
            return requests
        except Exception as e:
            print(f"Error retrieving requests: {str(e)}")
            return [] 

    @staticmethod
    async def update_gem_qr_history(
        gem_id: int,
        generated_by: int,
        price: float,
        payment_method: str,
        valid_until: datetime
    ):
        """Update gem's QR code history"""
        try:
            qr_history_entry = {
                "generated_by": generated_by,
                "price": price,
                "payment_method": payment_method,
                "generated_at": datetime.utcnow(),
                "valid_until": valid_until
            }

            # Update or create gem trace
            existing_trace = await gem_traces_collection.find_one({"gem_id": gem_id})
            if existing_trace:
                await gem_traces_collection.update_one(
                    {"gem_id": gem_id},
                    {"$push": {"qr_history": qr_history_entry}}
                )
            else:
                # Create new trace with QR history
                new_trace = GemLifetimeTrace(
                    gem_id=gem_id,
                    qr_history=[qr_history_entry]
                )
                await gem_traces_collection.insert_one(new_trace.dict())

        except Exception as e:
            print(f"Error updating QR history: {str(e)}")
            raise

   

