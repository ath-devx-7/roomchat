from datetime import datetime
from typing import List, Literal, Optional, Union, Annotated

from django.contrib.auth.hashers import check_password
from pydantic import BaseModel, Field, PrivateAttr, field_validator, ConfigDict, model_validator

from .models import Room


# ─── Room HTTP Schemas ───

class RoomBase(BaseModel):
    name: str = Field(..., max_length=100)
    description: str = Field(default="")
    capacity: int = Field(default=10)


class RoomCreate(RoomBase):
    password: str = Field(default="")

    @field_validator('name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Room name is required.")
        return v

    @field_validator('capacity', mode='before')
    @classmethod
    def validate_capacity_before(cls, v):
        if v is None:
            return 10
        try:
            val = int(v)
        except (TypeError, ValueError):
            return 10
        if val < 2:
            return 2
        if val > 100:
            return 100
        return val
    


class RoomJoin(BaseModel):
    room_code: str
    password: str = Field(default="")

    _room: Optional[Room] = PrivateAttr(default=None)

    @property
    def room(self) -> Optional[Room]:
        return self._room

    @field_validator('room_code')
    @classmethod
    def validate_room_code(cls, code: str) -> str:
        code = code.strip().upper()
        if not code:
            raise ValueError("Please enter a room code.")
        if len(code) != 6:
            raise ValueError("Room code must be 6 characters.")
        return code

    @field_validator('password')
    @classmethod
    def validate_password(cls, password: str) -> str:
        password = password.strip()
        return password

    @model_validator(mode='after')
    def validate_room_access(self) -> "RoomJoin":
        try:
            self._room = Room.objects.get(room_code=self.room_code)
        except Room.DoesNotExist as exc:
            raise ValueError("Room not found. Check the code and try again.") from exc

        if self._room.password and not check_password(self.password, self._room.password):
            raise ValueError("Incorrect room password.")

        if self._room.is_full:
            raise ValueError("Room is full.")

        return self


class RoomInvitationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    room_code: str
    room_name: str
    sender_username: str
    created_at: datetime


# ─── WebSocket Incoming Payload Schemas (Discriminated Union) ───

class WSBaseMessage(BaseModel):
    type: str


class WSSendMessage(WSBaseMessage):
    type: Literal['send_message']
    content: str

    @field_validator('content')
    @classmethod
    def validate_content(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Message content cannot be empty.")
        return v


class WSEditMessage(WSBaseMessage):
    type: Literal['edit_message']
    message_id: int
    content: str

    @field_validator('content')
    @classmethod
    def validate_content(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Edited content cannot be empty.")
        return v


class WSDeleteMessage(WSBaseMessage):
    type: Literal['delete_message']
    message_id: int


class WSReplyMessage(WSBaseMessage):
    type: Literal['reply_message']
    content: str
    reply_to_id: int

    @field_validator('content')
    @classmethod
    def validate_content(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Reply content cannot be empty.")
        return v


class WSKickUser(WSBaseMessage):
    type: Literal['kick_user']
    user_id: int


class WSTransferOwnership(WSBaseMessage):
    type: Literal['transfer_ownership']
    user_id: int


class WSDeleteRoom(WSBaseMessage):
    type: Literal['delete_room']


class WSSendRoomInvite(WSBaseMessage):
    type: Literal['send_room_invite']
    user_id: int


class WSAcceptRoomInvite(WSBaseMessage):
    type: Literal['accept_room_invite']
    invitation_id: int


class WSRejectRoomInvite(WSBaseMessage):
    type: Literal['reject_room_invite']
    invitation_id: int


# The union of all incoming WebSocket schemas discriminated by the "type" field
WSIncomingMessage = Annotated[
    Union[
        WSSendMessage,
        WSEditMessage,
        WSDeleteMessage,
        WSReplyMessage,
        WSKickUser,
        WSTransferOwnership,
        WSDeleteRoom,
        WSSendRoomInvite,
        WSAcceptRoomInvite,
        WSRejectRoomInvite
    ],
    Field(discriminator='type')
]


# ─── WebSocket Outgoing Broadcast Events ───

class WSUserJoinedEvent(BaseModel):
    type: Literal['user_joined'] = 'user_joined'
    username: str
    user_id: int


class WSUserLeftEvent(BaseModel):
    type: Literal['user_left'] = 'user_left'
    username: str
    user_id: int


class WSMessageCreatedEvent(BaseModel):
    type: Literal['message_created'] = 'message_created'
    message_id: int
    sender_id: int
    sender_username: str
    content: str
    created_at: str
    reply_to: Optional[dict] = None


class WSMessageEditedEvent(BaseModel):
    type: Literal['message_edited'] = 'message_edited'
    message_id: int
    content: str
    edited_at: str


class WSMessageDeletedEvent(BaseModel):
    type: Literal['message_deleted'] = 'message_deleted'
    message_id: int


class WSActiveUserItem(BaseModel):
    user_id: int
    username: str
    is_owner: bool


class WSActiveUsersUpdatedEvent(BaseModel):
    type: Literal['active_users_updated'] = 'active_users_updated'
    users: List[WSActiveUserItem]


class WSUserKickedEvent(BaseModel):
    type: Literal['user_kicked'] = 'user_kicked'
    message: str


class WSUserKickedBroadcastEvent(BaseModel):
    type: Literal['user_kicked_broadcast'] = 'user_kicked_broadcast'
    user_id: int
    username: str


class WSOwnershipTransferredEvent(BaseModel):
    type: Literal['ownership_transferred'] = 'ownership_transferred'
    new_owner_id: int
    new_owner_username: str


class WSRoomDeletedEvent(BaseModel):
    type: Literal['room_deleted'] = 'room_deleted'
    message: str


class WSRoomInfoEvent(BaseModel):
    type: Literal['room_info'] = 'room_info'
    owner_id: int
    owner_username: str
    room_name: str
    room_description: str
    capacity: int


class WSRoomInvitationReceivedEvent(BaseModel):
    type: Literal['room_invitation_received'] = 'room_invitation_received'
    invitation_id: int
    room_code: str
    room_name: str
    sender_username: str
    sender_id: int


class WSFriendRequestReceivedEvent(BaseModel):
    type: Literal['friend_request_received'] = 'friend_request_received'
    friendship_id: int
    sender_username: str
    sender_id: int


class WSInviteResponseEvent(BaseModel):
    type: Literal['invite_response'] = 'invite_response'
    status: str
    room_code: Optional[str] = None
    message: str


class WSInviteSentEvent(BaseModel):
    type: Literal['invite_sent'] = 'invite_sent'
    message: str


class WSErrorEvent(BaseModel):
    type: Literal['error'] = 'error'
    message: str
