from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional

# User Schemas
class UserBase(BaseModel):
    username: str
    email: str

class UserCreate(UserBase):
    password: str

class UserLogin(BaseModel):
    username: str
    password: str

class UserResponse(UserBase):
    id: int
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

# Chat Room Schemas
class ChatRoomBase(BaseModel):
    name: str
    description: Optional[str] = None
    max_participants: Optional[int] = 100

class ChatRoomCreate(ChatRoomBase):
    pass

class ChatRoomResponse(ChatRoomBase):
    id: int
    created_by_id: Optional[int] = None
    created_at: datetime
    is_active: bool

    model_config = ConfigDict(from_attributes=True)

# Message Schemas
class MessageBase(BaseModel):
    content: Optional[str] = None
    message_type: str = "text"
    file_url: Optional[str] = None
    file_name: Optional[str] = None
    file_size: Optional[int] = None
    mime_type: Optional[str] = None

class MessageResponse(MessageBase):
    id: int
    uuid: str
    room_id: int
    user_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
