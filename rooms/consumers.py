import json
from datetime import datetime

from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import User
from django.utils import timezone

from .models import Room, RoomMembership, RoomInvitation, Message
from accounts.models import Friendship
from django.db.models import Q


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
            await self.close()
            return

        # Validate room exists
        self.room = await self.get_room()
        if not self.room:
            await self.close()
            return

        # Check capacity
        if await self.is_room_full() and not await self.is_member():
            await self.close(code=4001)
            return

        # Join the channel group
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

        # Create membership
        await self.create_membership()

        # Notify room
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'user_joined',
                'username': self.user.username,
                'user_id': self.user.id,
            }
        )

        # Send updated active users list
        await self.send_active_users()

        # Send updated room info (in case ownership changed, etc.)
        await self.send_room_info()

    async def disconnect(self, close_code):
        if hasattr(self, 'user') and not self.user.is_anonymous and hasattr(self, 'room'):
            # Remove membership
            await self.delete_membership()

            # Check if room is empty and delete it if so
            room_deleted = await self.check_and_delete_room_if_empty()

            if not room_deleted:
                # Notify room
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'user_left',
                        'username': self.user.username,
                        'user_id': self.user.id,
                    }
                )

                # Update active users
                await self.send_active_users()

        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        """Route incoming WebSocket messages to appropriate handlers."""
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            return

        event_type = data.get('type')
        handlers = {
            'send_message': self.handle_send_message,
            'edit_message': self.handle_edit_message,
            'delete_message': self.handle_delete_message,
            'reply_message': self.handle_reply_message,
            'kick_user': self.handle_kick_user,
            'transfer_ownership': self.handle_transfer_ownership,
            'delete_room': self.handle_delete_room,
            'send_room_invite': self.handle_send_room_invite,
        }

        handler = handlers.get(event_type)
        if handler:
            await handler(data)

    # ─── Message Handlers 

    async def handle_send_message(self, data):
        content = data.get('content', '').strip()
        if not content:
            return

        # save message in DB
        message = await self.save_message(content)

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'message_created',
                'message_id': message.id,
                'sender_id': self.user.id,
                'sender_username': self.user.username,
                'content': content,
                'created_at': message.created_at.isoformat(),
                'reply_to': None,
            }
        )

    async def handle_reply_message(self, data):
        content = data.get('content', '').strip()
        reply_to_id = data.get('reply_to_id')
        if not content or not reply_to_id:
            return

        reply_to_data = await self.get_message_preview(reply_to_id)
        message = await self.save_message(content, reply_to_id=reply_to_id)

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'message_created',
                'message_id': message.id,
                'sender_id': self.user.id,
                'sender_username': self.user.username,
                'content': content,
                'created_at': message.created_at.isoformat(),
                'reply_to': reply_to_data,
            }
        )

    async def handle_edit_message(self, data):
        message_id = data.get('message_id')
        new_content = data.get('content', '').strip()
        if not message_id or not new_content:
            return

        success = await self.update_message(message_id, new_content)
        if not success:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Cannot edit this message.',
            }))
            return

        edited_at = timezone.now().isoformat()

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'message_edited',
                'message_id': message_id,
                'content': new_content,
                'edited_at': edited_at,
            }
        )

    async def handle_delete_message(self, data):
        message_id = data.get('message_id')
        if not message_id:
            return

        success = await self.soft_delete_message(message_id)
        if not success:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Cannot delete this message.',
            }))
            return

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'message_deleted',
                'message_id': message_id,
            }
        )

    # ─── Owner Controls 

    async def handle_kick_user(self, data):
        target_user_id = data.get('user_id')
        if not target_user_id:
            return

        is_owner = await self.check_is_owner()
        if not is_owner:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Only the room owner can kick users.',
            }))
            return

        # Cannot kick yourself
        if target_user_id == self.user.id:
            return

        target_username = await self.get_username(target_user_id)
        target_channel = await self.get_member_channel(target_user_id)

        # Remove membership
        await self.remove_membership(target_user_id)

        # Notify the kicked user specifically
        if target_channel:
            await self.channel_layer.send(
                target_channel,
                {
                    'type': 'user_kicked',
                    'message': 'You have been kicked from the room.',
                }
            )

        # Notify everyone
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'user_kicked_broadcast',
                'user_id': target_user_id,
                'username': target_username,
            }
        )

        await self.send_active_users()

    async def handle_transfer_ownership(self, data):
        target_user_id = data.get('user_id')
        if not target_user_id:
            return

        is_owner = await self.check_is_owner()
        if not is_owner:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Only the room owner can transfer ownership.',
            }))
            return

        target_username = await self.transfer_room_ownership(target_user_id)
        if not target_username:
            return

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'ownership_transferred',
                'new_owner_id': target_user_id,
                'new_owner_username': target_username,
            }
        )

        # Broadcast updated room info and active users to reflect ownership transfer
        await self.send_room_info()
        await self.send_active_users()

    async def handle_delete_room(self, data):
        is_owner = await self.check_is_owner()
        if not is_owner:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Only the room owner can delete the room.',
            }))
            return

        # Notify all users before deletion
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'room_deleted',
                'message': 'This room has been deleted by the owner.',
            }
        )

        # Delete room from database
        await self.delete_room_from_db()

    # ─── Room Invitation 

    async def handle_send_room_invite(self, data):
        target_user_id = data.get('user_id')
        if not target_user_id:
            return

        result = await self.create_room_invitation(target_user_id)
        if result.get('error'):
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': result['error'],
            }))
            return

        # Send notification to the target user's personal channel
        await self.channel_layer.group_send(
            f'user_{target_user_id}',
            {
                'type': 'room_invitation_received',
                'invitation_id': result['invitation_id'],
                'room_code': self.room_code,
                'room_name': result['room_name'],
                'sender_username': self.user.username,
                'sender_id': self.user.id,
            }
        )

        await self.send(text_data=json.dumps({
            'type': 'invite_sent',
            'message': f'Invitation sent to {result["receiver_username"]}.',
        }))

    # ─── Group Event Handlers (called by channel_layer.group_send) 

    async def user_joined(self, event):
        await self.send(text_data=json.dumps({
            'type': 'user_joined',
            'username': event['username'],
            'user_id': event['user_id'],
        }))

    async def user_left(self, event):
        await self.send(text_data=json.dumps({
            'type': 'user_left',
            'username': event['username'],
            'user_id': event['user_id'],
        }))

    async def message_created(self, event):
        await self.send(text_data=json.dumps({
            'type': 'message_created',
            'message_id': event['message_id'],
            'sender_id': event['sender_id'],
            'sender_username': event['sender_username'],
            'content': event['content'],
            'created_at': event['created_at'],
            'reply_to': event['reply_to'],
        }))

    async def message_edited(self, event):
        await self.send(text_data=json.dumps({
            'type': 'message_edited',
            'message_id': event['message_id'],
            'content': event['content'],
            'edited_at': event['edited_at'],
        }))

    async def message_deleted(self, event):
        await self.send(text_data=json.dumps({
            'type': 'message_deleted',
            'message_id': event['message_id'],
        }))

    async def active_users_updated(self, event):
        await self.send(text_data=json.dumps({
            'type': 'active_users_updated',
            'users': event['users'],
        }))

    async def user_kicked(self, event):
        """Sent directly to the kicked user's channel."""
        await self.send(text_data=json.dumps({
            'type': 'user_kicked',
            'message': event['message'],
        }))
        await self.close()

    async def user_kicked_broadcast(self, event):
        await self.send(text_data=json.dumps({
            'type': 'user_kicked_broadcast',
            'user_id': event['user_id'],
            'username': event['username'],
        }))

    async def ownership_transferred(self, event):
        await self.send(text_data=json.dumps({
            'type': 'ownership_transferred',
            'new_owner_id': event['new_owner_id'],
            'new_owner_username': event['new_owner_username'],
        }))

    async def room_deleted(self, event):
        await self.send(text_data=json.dumps({
            'type': 'room_deleted',
            'message': event['message'],
        }))
        await self.close()

    async def room_info(self, event):
        await self.send(text_data=json.dumps({
            'type': 'room_info',
            'owner_id': event['owner_id'],
            'owner_username': event['owner_username'],
            'room_name': event['room_name'],
            'room_description': event['room_description'],
            'capacity': event['capacity'],
        }))

    # ─── Helper: send active users to group 

    async def send_active_users(self):
        users = await self.get_active_users()
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'active_users_updated',
                'users': users,
            }
        )

    async def send_room_info(self):
        info = await self.get_room_info()
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'room_info',
                **info,
            }
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
        memberships = RoomMembership.objects.filter(room=self.room).select_related('user')
        return [
            {
                'user_id': m.user.id,
                'username': m.user.username,
                'is_owner': m.user.id == self.room.owner_id,
            }
            for m in memberships
        ]

    @database_sync_to_async
    def get_room_info(self):
        # Refresh from DB
        room = Room.objects.get(pk=self.room.pk)
        self.room = room
        return {
            'owner_id': room.owner_id,
            'owner_username': room.owner.username,
            'room_name': room.name,
            'room_description': room.description,
            'capacity': room.capacity,
        }

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
            return True
        except Message.DoesNotExist:
            return False

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
        try:
            target_user = User.objects.get(id=target_user_id)
        except User.DoesNotExist:
            return {'error': 'User not found.'}

        # Check they are friends
        are_friends = Friendship.objects.filter(
            Q(sender=self.user, receiver=target_user, status='accepted') |
            Q(sender=target_user, receiver=self.user, status='accepted')
        ).exists()

        if not are_friends:
            return {'error': 'You can only invite friends.'}

        # Check if already invited
        existing = RoomInvitation.objects.filter(
            room=self.room, receiver=target_user, status='pending'
        ).exists()
        if existing:
            return {'error': 'Invitation already sent.'}

        # Check if already in room
        in_room = RoomMembership.objects.filter(user=target_user, room=self.room).exists()
        if in_room:
            return {'error': 'User is already in this room.'}

        inv = RoomInvitation.objects.create(
            room=self.room,
            sender=self.user,
            receiver=target_user,
        )

        return {
            'invitation_id': inv.id,
            'room_name': self.room.name,
            'receiver_username': target_user.username,
        }

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
            data = json.loads(text_data)
        except json.JSONDecodeError:
            return

        event_type = data.get('type')
        handlers = {
            'accept_room_invite': self.handle_accept_room_invite,
            'reject_room_invite': self.handle_reject_room_invite,
        }

        handler = handlers.get(event_type)
        if handler:
            await handler(data)

    async def handle_accept_room_invite(self, data):
        invitation_id = data.get('invitation_id')
        result = await self.accept_invitation(invitation_id) # {'room_code': inv.room.room_code}

        await self.send(text_data=json.dumps({
            'type': 'invite_response',
            'status': 'accepted' if result else 'error',
            'room_code': result.get('room_code') if result else None,
            'message': 'Invitation accepted!' if result else 'Invitation not found.',
        }))

    async def handle_reject_room_invite(self, data):
        invitation_id = data.get('invitation_id')
        await self.reject_invitation(invitation_id)

        await self.send(text_data=json.dumps({
            'type': 'invite_response',
            'status': 'declined',
            'message': 'Invitation declined.',
        }))

    # ─── Group Event Handlers 

    async def room_invitation_received(self, event):
        await self.send(text_data=json.dumps({
            'type': 'room_invitation_received',
            'invitation_id': event['invitation_id'],
            'room_code': event['room_code'],
            'room_name': event['room_name'],
            'sender_username': event['sender_username'],
            'sender_id': event['sender_id'],
        }))

    async def friend_request_received(self, event):
        await self.send(text_data=json.dumps({
            'type': 'friend_request_received',
            'friendship_id': event['friendship_id'],
            'sender_username': event['sender_username'],
            'sender_id': event['sender_id'],
        }))

    # ─── Database Access 

    @database_sync_to_async
    def accept_invitation(self, invitation_id):
        try:
            inv = RoomInvitation.objects.get(
                id=invitation_id, receiver=self.user, status='pending'
            )
            inv.status = 'accepted'
            inv.save()
            return {'room_code': inv.room.room_code}
        except RoomInvitation.DoesNotExist:
            return None

    @database_sync_to_async
    def reject_invitation(self, invitation_id):
        try:
            inv = RoomInvitation.objects.get(
                id=invitation_id, receiver=self.user, status='pending'
            )
            inv.status = 'declined'
            inv.save()
            return True
        except RoomInvitation.DoesNotExist:
            return False
