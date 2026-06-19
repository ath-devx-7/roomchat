import random
import string

from django.db import models
from django.contrib.auth.models import User


def generate_room_code():
    """Generate a unique 6-character alphanumeric uppercase room code."""
    while True:
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        if not Room.objects.filter(room_code=code).exists():
            return code


class Room(models.Model):
    """A chat room that users can join via a unique code."""

    room_code = models.CharField(max_length=6, unique=True, editable=False)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, default='')
    password = models.CharField(max_length=128, blank=True, default='')
    capacity = models.PositiveIntegerField(default=10)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='owned_rooms')
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.room_code:
            self.room_code = generate_room_code()
        super().save(*args, **kwargs)

    @property
    def active_user_count(self):
        return self.memberships.count()

    @property
    def is_full(self):
        return self.active_user_count >= self.capacity

    def __str__(self):
        return f"{self.name} ({self.room_code})"


class RoomMembership(models.Model):
    """Tracks currently active users in a room (created on WS connect, deleted on disconnect)."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='room_memberships')
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='memberships')
    channel_name = models.CharField(max_length=255, blank=True, default='')
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'room')

    def __str__(self):
        return f"{self.user.username} in {self.room.name}"


class RoomInvitation(models.Model):
    """An invitation to join a room, sent from one user to another."""

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('declined', 'Declined'),
    ]

    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='invitations')
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_invitations')
    receiver = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_invitations')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.sender.username} invited {self.receiver.username} to {self.room.name}"


class Message(models.Model):
    """A chat message within a room."""

    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='messages')
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    edited_at = models.DateTimeField(null=True, blank=True)
    is_deleted = models.BooleanField(default=False)
    reply_to = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.SET_NULL, related_name='replies'
    )

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"{self.sender.username}: {self.content[:50]}"
