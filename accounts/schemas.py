import re
from datetime import datetime
from typing import List
from pydantic import BaseModel, EmailStr, ValidationInfo, field_validator


class UserBase(BaseModel):
    username: str
    email: str


class UserCreate(UserBase):
    email: EmailStr
    # Length is enforced in validate_password so the user sees its wording, not
    # pydantic's "String should have at least 8 characters".
    password: str
    # Must stay declared after `password`: the match check reads info.data, which
    # only holds fields validated before this one. Defaulted so the model is still
    # constructible with the three original arguments.
    confirm_password: str = ''

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

    @field_validator('confirm_password')
    @classmethod
    def validate_confirm_password(cls, v: str, info: ValidationInfo) -> str:
        if not v:
            raise ValueError('Please confirm your password.')
        # `password` is missing from info.data when it failed its own validator.
        # That error is already on its way to the user, so don't pile a spurious
        # mismatch on top of it.
        password = info.data.get('password')
        if password is not None and v != password:
            raise ValueError('The two passwords do not match.')
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
