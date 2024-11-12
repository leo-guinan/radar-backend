from sqlalchemy import Column, String, UUID, DateTime, JSON, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()

class Conversation(Base):
    __tablename__ = "conversations"
    
    id = Column(UUID, primary_key=True)
    url = Column(String, nullable=False)
    media_type = Column(String, nullable=False)
    user_insight = Column(String)
    ai_analysis = Column(String)
    world_model = Column(JSON)
    created_at = Column(DateTime, server_default=func.now())

class Message(Base):
    __tablename__ = "messages"
    
    id = Column(UUID, primary_key=True)
    conversation_id = Column(UUID, ForeignKey("conversations.id"))
    role = Column(String, nullable=False)
    content = Column(String, nullable=False)
    timestamp = Column(DateTime, server_default=func.now()) 