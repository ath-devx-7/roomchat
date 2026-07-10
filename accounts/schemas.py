import re
from datetime import datetime
from typing import List
from pydantic import BaseModel, EmailStr, field_validator, ConfigDict


class UserBase(BaseModel):
    username: str
    email: str


class UserCreate(UserBase):
    email: EmailStr
    # Length is enforced in validate_password so the user sees its wording, not
    # pydantic's "String should have at least 8 characters".
    password: str

    @field_validator('username')
    @classmethod
    def validate_username(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError('Username is required.')
        if len(v) > 150:
            raise ValueError('Username must be 150 characters or fewer.')
        if not re.match(r'^[\w.@+-]+$', v):
            raise ValueError('Enter a valid username. This value may contain only letters, numbers, and @/./+/-/_ characters.')
        return v

    @field_validator('password')
    @classmethod
    def validate_password(cls, v: str) -> str:
        if not v:
            raise ValueError('Password is required.')
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters long.')
        return v


class UserLogin(BaseModel):
    username: str
    password: str

    @field_validator('username')
    @classmethod
    def validate_username(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError('Username is required.')
        return v

    @field_validator('password')
    @classmethod
    def validate_password(cls, v: str) -> str:
        if not v:
            raise ValueError('Password is required.')
        return v


class UserResponse(UserBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


class FriendshipBase(BaseModel):
    status: str


class FriendshipResponse(FriendshipBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    sender_id: int
    receiver_id: int
    created_at: datetime


class FriendItemResponse(BaseModel):
    id: int
    user_id: int
    username: str


class FriendPendingReceivedResponse(BaseModel):
    id: int
    sender_id: int
    sender_username: str
    created_at: datetime


class FriendPendingSentResponse(BaseModel):
    id: int
    receiver_id: int
    receiver_username: str
    created_at: datetime


class FriendsListResponse(BaseModel):
    friends: List[FriendItemResponse]
    pending_received: List[FriendPendingReceivedResponse]
    pending_sent: List[FriendPendingSentResponse]
