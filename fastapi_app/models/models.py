from sqlalchemy import (
    Column, Integer, String, Float, ForeignKey, Text, JSON, DateTime, Boolean, Date
)
from sqlalchemy.orm import relationship
from datetime import datetime
from fastapi_app.database import Base, engine
import qrcode  # type: ignore
import base64
import json
import os

# User Model
class User(Base):
    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True, unique=True, index=True)
    first_name = Column(String(50), nullable=False)
    last_name = Column(String(50), nullable=False)
    ID = Column(String(50), unique=True, nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    phone_number = Column(String(15), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    country = Column(Text, nullable=True)
    state = Column(Text, nullable=True)
    city = Column(Text, nullable=True)
    address = Column(Text, nullable=True)
    is_verified = Column(Boolean, default=False)
    last_login = Column(DateTime, nullable=True)
    is_superuser = Column(Boolean, default=False)
    is_staff = Column(Boolean, default=False)
    is_active = Column(Boolean, default=False)
    date_joined = Column(DateTime, default=datetime.utcnow)

    # Profile customization and verification
    profile_image = Column(String(255), default="uploads/profile_images/man.png")
    cover_image = Column(String(255), default="uploads/cover_images/Blue-Sapphires.jpg")
    is_verified_id = Column(Boolean, default=False)
    dob = Column(Date, nullable=True)
    qr_code = Column(String(255), nullable=True)  # Stores QR Image Path

    # Relationships
    gems = relationship("Gem", back_populates="owner", cascade="all, delete-orphan")
    transactions_sold = relationship(
        "Transaction",
        back_populates="seller",
        cascade="all, delete-orphan",
        foreign_keys="[Transaction.seller_id]"
    )
    transactions_bought = relationship(
        "Transaction",
        back_populates="buyer",
        cascade="all, delete-orphan",
        foreign_keys="[Transaction.buyer_id]"
    )

    def generate_qr(self):
        """Generate an encrypted QR code for this user and store as an image."""
        qr_data = {"user_id": self.user_id, "ID": self.ID}
        
        # Encrypt data (Base64 Encoding for simplicity)
        encoded_data = base64.urlsafe_b64encode(json.dumps(qr_data).encode()).decode()
        
        qr_img = qrcode.make(encoded_data)
        file_path = f"uploads/qrcodes/{self.user_id}.png"
        qr_img.save(file_path)
        
        self.qr_code = file_path


# Gem Model
class Gem(Base):
    __tablename__ = "gems"

    gem_id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    name = Column(String(100), nullable=False)
    category = Column(String(50), nullable=False)  # e.g., Rough, Geuda, Cut and Polished, Lot
    sub_category = Column(String(50), nullable=True)  # For Geuda: Burn After Color (natural or Heat)
    cost = Column(Float, nullable=False)
    sell_price = Column(Float, nullable=True)
    description = Column(Text, nullable=True)
    images = Column(JSON, nullable=False)  # List of image URLs

    # Relationships
    owner = relationship("User", back_populates="gems")
    expenses = relationship("Expense", back_populates="gem", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="gem", cascade="all, delete-orphan")
    non_user_transactions = relationship("NonUserTransaction", back_populates="gem", cascade="all, delete-orphan")


# Transaction Model
class Transaction(Base):
    __tablename__ = "transactions"

    transaction_id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    buyer_id = Column(Integer, ForeignKey("users.user_id"), nullable=True)
    gem_id = Column(Integer, ForeignKey("gems.gem_id"), nullable=False)
    amount = Column(Float, nullable=False)
    payment_type = Column(String(20), nullable=False)  # Cash, Cheque, Credit
    fulfillment_date = Column(DateTime, nullable=True)
    transaction_status = Column(String(20), default="pending")  # pending, approved, fulfilled
    transaction_type = Column(String(20), nullable=False)  # direct_sell, brokerage

    # Relationships
    seller = relationship("User", back_populates="transactions_sold", foreign_keys=[seller_id])
    buyer = relationship("User", back_populates="transactions_bought", foreign_keys=[buyer_id])
    gem = relationship("Gem", back_populates="transactions")


# Expense Model
class Expense(Base):
    __tablename__ = "expenses"

    expense_id = Column(Integer, primary_key=True, index=True)
    gem_id = Column(Integer, ForeignKey("gems.gem_id"), nullable=False)
    reason = Column(Text, nullable=False)
    amount = Column(Float, nullable=False)
    date_added = Column(DateTime, default=datetime.utcnow)

    # Relationships
    gem = relationship("Gem", back_populates="expenses")


# Non-User Transaction Model
class NonUserTransaction(Base):
    __tablename__ = "non_user_transactions"

    transaction_id = Column(Integer, primary_key=True, index=True)
    seller_id = Column(Integer, nullable=False)  
    buyer_id = Column(Integer, nullable=True)  
    gem_id = Column(Integer, ForeignKey("gems.gem_id"), nullable=False)
    amount = Column(Float, nullable=False)
    payment_type = Column(String(20), nullable=False)
    fulfillment_date = Column(DateTime, nullable=True)  
    transaction_status = Column(String(20), default="pending")
    transaction_type = Column(String(20), nullable=False)

    # Relationships
    gem = relationship("Gem", back_populates="non_user_transactions")


# Create all tables in the database
Base.metadata.create_all(bind=engine)