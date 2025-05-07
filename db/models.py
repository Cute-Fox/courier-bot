# db/models.py

from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, Enum, ARRAY
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime
import enum

Base = declarative_base()

class RequestStatus(enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    NEED_INFO = "need_info"
    CLOSED = "closed"

class EquipmentStatus(enum.Enum):
    IN_STOCK = "in_stock"
    WITH_COURIER = "with_courier"
    NEED_REPAIR = "need_repair"

class User(Base):
    __tablename__ = "users"
    id       = Column(Integer, primary_key=True, index=True)
    name     = Column(String, nullable=True)
    role     = Column(String, default="courier")
    requests = relationship("Request", back_populates="user")

class Request(Base):
    __tablename__ = "requests"
    id          = Column(Integer, primary_key=True)
    user_id     = Column(Integer, ForeignKey("users.id"), nullable=False)
    category    = Column(String, nullable=False)
    subcategory = Column(String, nullable=True)
    title       = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    priority    = Column(String, nullable=False)
    photos      = Column(ARRAY(String), nullable=True)
    status      = Column(Enum(RequestStatus), default=RequestStatus.OPEN)
    created_at  = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="requests")

class Equipment(Base):
    __tablename__ = "equipment"
    id          = Column(Integer, primary_key=True, index=True)
    eq_id       = Column(String, unique=True, nullable=False)
    type        = Column(String, nullable=False)
    status      = Column(Enum(EquipmentStatus), default=EquipmentStatus.IN_STOCK)
    assigned_to = Column(Integer, ForeignKey("users.id"), nullable=True)

    user = relationship("User")

class Message(Base):
    __tablename__ = "messages"
    id         = Column(Integer, primary_key=True, index=True)
    request_id = Column(Integer, ForeignKey("requests.id"), nullable=True)
    from_user  = Column(Integer, ForeignKey("users.id"), nullable=False)
    to_user    = Column(Integer, ForeignKey("users.id"), nullable=False)
    text       = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
