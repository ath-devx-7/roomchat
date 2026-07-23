import json

from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import User
from django.utils import timezone
from pydantic import ValidationError, TypeAdapter, Field
from typing import Union, Annotated

from roomchat.errors import format_pydantic_errors

from .models import Room, RoomMembership, Message
from . import services
from .schemas import (
    WSIncomingMessage,
    WSSendMessage,
    WSEditMessage,
    WSDeleteMessage,
    WSReplyMessage,
    WSKickUser,
    WSTransferOwnership,
    WSDeleteRoom,
    WSSendRoomInvite,
    WSAcceptRoomInvite,
    WSRejectRoomInvite,
    WSUserJoinedEvent,
    WSUserLeftEvent,
    WSMessageCreatedEvent,
    WSMessageEditedEvent,
    WSMessageDeletedEvent,
    WSActiveUsersUpdatedEvent,
    WSUserKickedEvent,
    WSUserKickedBroadcastEvent,
    WSOwnershipTransferredEvent,
    WSRoomDeletedEvent,
    WSRoomInfoEvent,
    WSRoomInvitationReceivedEvent,
    WSInviteResponseEvent,
    WSInviteSentEvent,
    WSErrorEvent,
)


# Application close codes. The client keys off these to decide whether to
# reconnect and what to tell the user.
CLOSE_ROOM_FULL = 4001
CLOSE_NOT_AUTHENTICATED = 4003
CLOSE_ROOM_NOT_FOUND = 4004


class ChatConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for room-based chat.

    Handles: messaging (send, edit, delete, reply),
    active user tracking, and owner controls (kick, transfer, delete room).
    """

    async def connect(self):
        self.room_code = self.scope['url_route']['kwargs']['room_code']
        self.room_group_name = f'room_{self.room_code}'
        self.user = self.scope['user']

        if self.user.is_anonymous:
            await self.reject(CLOSE_NOT_AUTHENTICATED, 'You must be signed in to join a room.')
            return

        # Validate room exists
        self.room = await self.get_room()
        if not self.room:
            await self.reject(CLOSE_ROOM_NOT_FOUND, 'This room no longer exists.')
            return

        # Check capacity
        if await self.is_room_full() and not await self.is_member():
            await self.reject(CLOSE_ROOM_FULL, 'This room is full.')
            return

        # Check if the user is authorized to join the room (owner, accepted invite, or password session)
        if self.room.password and not await self.is_member():
            authorized_rooms = self.scope['session'].get('authorized_rooms', [])
            is_authorized = (
                await self.check_is_owner()
                or await self.has_accepted_invite()
                or self.room.room_code in authorized_rooms
            )
            if not is_authorized:
                await self.reject(CLOSE_NOT_AUTHENTICATED, 'This room is protected. Please join using the password on the dashboard.')
                return

        # Join the channel group
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

        # Create membership
        await self.create_membership()

        # Notify room
        await self.channel_layer.group_send(
            self.room_group_name,
            WSUserJoinedEvent(username=self.user.username, user_id=self.user.id).model_dump(mode='json')
        )

        # Send updated active users list
        await self.send_active_users()

        # Send updated room info (in case ownership changed, etc.)
        await self.send_room_info()

    async def reject(self, code, reason):
        """Accept then immediately close, so the browser sees our close code.

        Closing before accept() makes the server reject the handshake with an
        HTTP 403, which the browser reports as close code 1006 — the client
        cannot tell 'room full' from a dropped connection.
        """
        self._rejected = True
        await self.accept()
        await self.send(text_data=WSErrorEvent(message=reason).model_dump_json())
        await self.close(code=code)

    async def disconnect(self, close_code):
        if getattr(self, '_rejected', False):
            return

        if hasattr(self, 'user') and not self.user.is_anonymous and getattr(self, 'room', None):
            # Remove membership
            await self.delete_membership()

            # Check if room is empty and delete it if so
            room_deleted = await self.check_and_delete_room_if_empty()

            if not room_deleted:
                # Notify room
                await self.channel_layer.group_send(
                    self.room_group_name,
                    WSUserLeftEvent(username=self.user.username, user_id=self.user.id).model_dump(mode='json')
                )

                # Update active users
                await self.send_active_users()

        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        """Route incoming WebSocket messages to appropriate handlers."""
        try:
            msg = TypeAdapter(WSIncomingMessage).validate_json(text_data)
        except ValidationError as e:
            # Send back validation error event
            message = "; ".join(format_pydantic_errors(e).values())
            await self.send(text_data=WSErrorEvent(message=message).model_dump_json())
            return
        except Exception:
            return

        handlers = {
            WSSendMessage: self.handle_send_message,
            WSEditMessage: self.handle_edit_message,
            WSDeleteMessage: self.handle_delete_message,
            WSReplyMessage: self.handle_reply_message,
            WSKickUser: self.handle_kick_user,
            WSTransferOwnership: self.handle_transfer_ownership,
            WSDeleteRoom: self.handle_delete_room,
            WSSendRoomInvite: self.handle_send_room_invite,
        }

        handler = handlers.get(type(msg))
        if handler:
            await handler(msg)

    # ─── Message Handlers 

    async def handle_send_message(self, msg: WSSendMessage):
        # save message in DB
        message = await self.save_message(msg.content)

        event = WSMessageCreatedEvent(
            message_id=message.id,
            sender_id=self.user.id,
            sender_username=self.user.username,
            content=msg.content,
            created_at=message.created_at.isoformat(),
            reply_to=None
        )
        await self.channel_layer.group_send(self.room_group_name, event.model_dump(mode='json'))

    async def handle_reply_message(self, msg: WSReplyMessage):
        reply_to_data = await self.get_message_preview(msg.reply_to_id)
        if reply_to_data is None:
            await self.send(text_data=WSErrorEvent(
                message='The message you replied to no longer exists.'
            ).model_dump_json())
            return

        message = await self.save_message(msg.content, reply_to_id=msg.reply_to_id)

        event = WSMessageCreatedEvent(
            message_id=message.id,
            sender_id=self.user.id,
            sender_username=self.user.username,
            content=msg.content,
            created_at=message.created_at.isoformat(),
            reply_to=reply_to_data
        )
        await self.channel_layer.group_send(self.room_group_name, event.model_dump(mode='json'))

    async def handle_edit_message(self, msg: WSEditMessage):
        edited_at = await self.update_message(msg.message_id, msg.content)
        if edited_at is None:
            await self.send(text_data=WSErrorEvent(message='Cannot edit this message.').model_dump_json())
            return

        edited_at = edited_at.isoformat()

        event = WSMessageEditedEvent(
            message_id=msg.message_id,
            content=msg.content,
            edited_at=edited_at
        )
        await self.channel_layer.group_send(self.room_group_name, event.model_dump(mode='json'))

    async def handle_delete_message(self, msg: WSDeleteMessage):
        success = await self.soft_delete_message(msg.message_id)
        if not success:
            await self.send(text_data=WSErrorEvent(message='Cannot delete this message.').model_dump_json())
            return

        event = WSMessageDeletedEvent(message_id=msg.message_id)
        await self.channel_layer.group_send(self.room_group_name, event.model_dump(mode='json'))

    # ─── Owner Controls 

    async def handle_kick_user(self, msg: WSKickUser):
        is_owner = await self.check_is_owner()
        if not is_owner:
            await self.send(text_data=WSErrorEvent(message='Only the room owner can kick users.').model_dump_json())
            return

        # Cannot kick yourself
        if msg.user_id == self.user.id:
            return

        target_username = await self.get_username(msg.user_id)
        target_channel = await self.get_member_channel(msg.user_id)

        # Remove membership
        await self.remove_membership(msg.user_id)

        # Notify the kicked user specifically
        if target_channel:
            await self.channel_layer.send(
                target_channel,
                WSUserKickedEvent(message='You have been kicked from the room.').model_dump(mode='json')
            )

        # Notify everyone
        event = WSUserKickedBroadcastEvent(user_id=msg.user_id, username=target_username)
        await self.channel_layer.group_send(self.room_group_name, event.model_dump(mode='json'))

        await self.send_active_users()

    async def handle_transfer_ownership(self, msg: WSTransferOwnership):
        is_owner = await self.check_is_owner()
        if not is_owner:
            await self.send(text_data=WSErrorEvent(message='Only the room owner can transfer ownership.').model_dump_json())
            return

        target_username = await self.transfer_room_ownership(msg.user_id)
        if not target_username:
            await self.send(text_data=WSErrorEvent(
                message='That user is no longer in this room.'
            ).model_dump_json())
            return

        event = WSOwnershipTransferredEvent(new_owner_id=msg.user_id, new_owner_username=target_username)
        await self.channel_layer.group_send(self.room_group_name, event.model_dump(mode='json'))

        # Broadcast updated room info and active users to reflect ownership transfer
        await self.send_room_info()
        await self.send_active_users()

    async def handle_delete_room(self, msg: WSDeleteRoom):
        is_owner = await self.check_is_owner()
        if not is_owner:
            await self.send(text_data=WSErrorEvent(message='Only the room owner can delete the room.').model_dump_json())
            return

        # Notify all users before deletion
        event = WSRoomDeletedEvent(message='This room has been deleted by the owner.')
        await self.channel_layer.group_send(self.room_group_name, event.model_dump(mode='json'))

        # Delete room from database
        await self.delete_room_from_db()

    # ─── Room Invitation 

    async def handle_send_room_invite(self, msg: WSSendRoomInvite):
        result = await self.create_room_invitation(msg.user_id)
        if result.get('error'):
            await self.send(text_data=WSErrorEvent(message=result['error']).model_dump_json())
            return

        # Send notification to the target user's personal channel
        event = WSRoomInvitationReceivedEvent(
            invitation_id=result['invitation_id'],
            room_code=self.room_code,
            room_name=result['room_name'],
            sender_username=self.user.username,
            sender_id=self.user.id
        )
        await self.channel_layer.group_send(f'user_{msg.user_id}', event.model_dump(mode='json'))

        await self.send(text_data=WSInviteSentEvent(message=f'Invitation sent to {result["receiver_username"]}.').model_dump_json())

    # ─── Group Event Handlers (called by channel_layer.group_send) ───
    # The sender already serialized via Pydantic .model_dump(), so the event
    # dict arriving here is already clean. We forward it as-is.

    async def user_joined(self, event):
        await self.send(text_data=json.dumps(event))

    async def user_left(self, event):
        await self.send(text_data=json.dumps(event))

    async def message_created(self, event):
        await self.send(text_data=json.dumps(event))

    async def message_edited(self, event):
        await self.send(text_data=json.dumps(event))

    async def message_deleted(self, event):
        await self.send(text_data=json.dumps(event))

    async def active_users_updated(self, event):
        await self.send(text_data=json.dumps(event))

    async def user_kicked(self, event):
        """Sent directly to the kicked user's channel."""
        await self.send(text_data=json.dumps(event))
        await self.close()

    async def user_kicked_broadcast(self, event):
        await self.send(text_data=json.dumps(event))

    async def ownership_transferred(self, event):
        await self.send(text_data=json.dumps(event))

    async def room_deleted(self, event):
        await self.send(text_data=json.dumps(event))
        await self.close()

    async def room_info(self, event):
        await self.send(text_data=json.dumps(event))

    # ─── Helper: send active users to group 

    async def send_active_users(self):
        users = await self.get_active_users()
        event = WSActiveUsersUpdatedEvent(users=users)
        await self.channel_layer.group_send(
            self.room_group_name,
            event.model_dump(mode='json')
        )

    async def send_room_info(self):
        info = await self.get_room_info()
        await self.channel_layer.group_send(
            self.room_group_name,
            info.model_dump(mode='json')
        )

    # ─── Database Access (sync_to_async) 

    @database_sync_to_async
    def get_room(self):
        try:
            return Room.objects.get(room_code=self.room_code)
        except Room.DoesNotExist:
            return None

    @database_sync_to_async
    def is_room_full(self):
        return self.room.is_full

    @database_sync_to_async
    def is_member(self):
        return RoomMembership.objects.filter(user=self.user, room=self.room).exists()

    @database_sync_to_async
    def has_accepted_invite(self):
        return services.has_accepted_room_invitation(self.user, self.room)

    @database_sync_to_async
    def create_membership(self):
        RoomMembership.objects.update_or_create(
            user=self.user,
            room=self.room,
            defaults={'channel_name': self.channel_name},
        )

    @database_sync_to_async
    def delete_membership(self):
        RoomMembership.objects.filter(user=self.user, room=self.room).delete()

    @database_sync_to_async
    def get_active_users(self):
        from .schemas import WSActiveUserItem
        memberships = RoomMembership.objects.filter(room=self.room).select_related('user')
        return [
            WSActiveUserItem(
                user_id=m.user.id,
                username=m.user.username,
                is_owner=m.user.id == self.room.owner_id,
            )
            for m in memberships
        ]

    @database_sync_to_async
    def get_room_info(self):
        # Refresh from DB
        room = Room.objects.get(pk=self.room.pk)
        self.room = room
        return WSRoomInfoEvent(
            owner_id=room.owner_id,
            owner_username=room.owner.username,
            room_name=room.name,
            room_description=room.description,
            capacity=room.capacity,
        )

    @database_sync_to_async
    def save_message(self, content, reply_to_id=None):
        reply_to = None
        if reply_to_id:
            try:
                reply_to = Message.objects.get(id=reply_to_id, room=self.room)
            except Message.DoesNotExist:
                pass
        return Message.objects.create(
            room=self.room,
            sender=self.user,
            content=content,
            reply_to=reply_to,
        )

    @database_sync_to_async
    def get_message_preview(self, message_id):
        try:
            msg = Message.objects.select_related('sender').get(id=message_id, room=self.room)
            if msg.is_deleted:
                return {
                    'message_id': msg.id,
                    'sender_username': msg.sender.username,
                    'content': 'This message was deleted.',
                }
            return {
                'message_id': msg.id,
                'sender_username': msg.sender.username,
                'content': msg.content[:100],
            }
        except Message.DoesNotExist:
            return None

    @database_sync_to_async
    def update_message(self, message_id, new_content):
        try:
            msg = Message.objects.get(id=message_id, sender=self.user, room=self.room, is_deleted=False)
            msg.content = new_content
            msg.edited_at = timezone.now()
            msg.save()
            return msg.edited_at
        except Message.DoesNotExist:
            return None

    @database_sync_to_async
    def soft_delete_message(self, message_id):
        try:
            msg = Message.objects.get(id=message_id, sender=self.user, room=self.room, is_deleted=False)
            msg.is_deleted = True
            msg.content = 'This message was deleted.'
            msg.save()
            return True
        except Message.DoesNotExist:
            return False

    @database_sync_to_async
    def check_is_owner(self):
        room = Room.objects.get(pk=self.room.pk)
        self.room = room
        return room.owner_id == self.user.id

    @database_sync_to_async
    def get_username(self, user_id):
        try:
            return User.objects.get(id=user_id).username
        except User.DoesNotExist:
            return 'Unknown'

    @database_sync_to_async
    def get_member_channel(self, user_id):
        try:
            m = RoomMembership.objects.get(user_id=user_id, room=self.room)
            return m.channel_name
        except RoomMembership.DoesNotExist:
            return None

    @database_sync_to_async
    def remove_membership(self, user_id):
        RoomMembership.objects.filter(user_id=user_id, room=self.room).delete()

    @database_sync_to_async
    def transfer_room_ownership(self, target_user_id):
        try:
            target_user = User.objects.get(id=target_user_id)
            # Ensure target is a member
            if not RoomMembership.objects.filter(user=target_user, room=self.room).exists():
                return None
            self.room.owner = target_user
            self.room.save()
            return target_user.username
        except User.DoesNotExist:
            return None

    @database_sync_to_async
    def delete_room_from_db(self):
        # Delete all memberships first
        RoomMembership.objects.filter(room=self.room).delete()
        self.room.delete()

    @database_sync_to_async
    def create_room_invitation(self, target_user_id):
        return services.create_room_invitation(self.user, self.room, target_user_id)

    @database_sync_to_async
    def check_and_delete_room_if_empty(self):
        try:
            # Check if the room still exists in the database
            if not Room.objects.filter(pk=self.room.pk).exists():
                return True

            members_count = RoomMembership.objects.filter(room=self.room).count()
            if members_count == 0:
                self.room.delete()
                return True
            return False
        except Exception:
            return True

_NotificationIncoming = Annotated[
    Union[WSAcceptRoomInvite, WSRejectRoomInvite],
    Field(discriminator='type')
]
_NotificationAdapter = TypeAdapter(_NotificationIncoming)


class NotificationConsumer(AsyncWebsocketConsumer):
    """
    Global notification WebSocket consumer (one per logged-in user).

    Handles: room invitations, friend request notifications.
    Each user joins a personal group 'user_{user_id}'.
    """

    async def connect(self):
        self.user = self.scope['user']

        if self.user.is_anonymous:
            await self.close()
            return

        self.user_group = f'user_{self.user.id}'
        await self.channel_layer.group_add(self.user_group, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, 'user_group'):
            await self.channel_layer.group_discard(self.user_group, self.channel_name)

    async def receive(self, text_data):
        try:
            msg = _NotificationAdapter.validate_json(text_data)
        except ValidationError as e:
            message = "; ".join(format_pydantic_errors(e).values())
            await self.send(text_data=WSErrorEvent(message=message).model_dump_json())
            return
        except Exception:
            return

        handlers = {
            WSAcceptRoomInvite: self.handle_accept_room_invite,
            WSRejectRoomInvite: self.handle_reject_room_invite,
        }

        handler = handlers.get(type(msg))
        if handler:
            await handler(msg)

    async def handle_accept_room_invite(self, msg: WSAcceptRoomInvite):
        result = await self.accept_invitation(msg.invitation_id)

        event = WSInviteResponseEvent(
            status='accepted' if result else 'error',
            room_code=result.get('room_code') if result else None,
            message='Invitation accepted!' if result else 'Invitation not found.',
        )
        await self.send(text_data=event.model_dump_json())

    async def handle_reject_room_invite(self, msg: WSRejectRoomInvite):
        await self.reject_invitation(msg.invitation_id)

        event = WSInviteResponseEvent(
            status='declined',
            message='Invitation declined.',
        )
        await self.send(text_data=event.model_dump_json())

    # ─── Group Event Handlers ───
    # Events arrive already serialized via Pydantic .model_dump() from the sender.

    async def room_invitation_received(self, event):
        await self.send(text_data=json.dumps(event))

    async def friend_request_received(self, event):
        await self.send(text_data=json.dumps(event))

    # ─── Database Access 

    @database_sync_to_async
    def accept_invitation(self, invitation_id):
        return services.accept_room_invitation(self.user, invitation_id)

    @database_sync_to_async
    def reject_invitation(self, invitation_id):
        return services.reject_room_invitation(self.user, invitation_id)
