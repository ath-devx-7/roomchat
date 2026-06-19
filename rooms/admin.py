from django.contrib import admin
from .models import Room, RoomMembership, RoomInvitation, Message


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ('name', 'room_code', 'owner', 'capacity', 'created_at')
    readonly_fields = ('room_code',)


@admin.register(RoomMembership)
class RoomMembershipAdmin(admin.ModelAdmin):
    list_display = ('user', 'room', 'joined_at')


@admin.register(RoomInvitation)
class RoomInvitationAdmin(admin.ModelAdmin):
    list_display = ('sender', 'receiver', 'room', 'status', 'created_at')
    list_filter = ('status',)


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('sender', 'room', 'content', 'created_at', 'is_deleted')
    list_filter = ('is_deleted',)
