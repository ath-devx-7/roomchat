/**
 * Dashboard JavaScript
 * Handles: notification WebSocket, friend system AJAX, room invitations
 */

// ─── Notification WebSocket ─────────────────────────────────
let notificationSocket = null;

function connectNotificationSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${protocol}//${window.location.host}/ws/notifications/`;

    notificationSocket = new WebSocket(url);

    notificationSocket.onopen = () => {
        console.log('[Notifications] Connected');
    };

    notificationSocket.onmessage = (event) => {
        const data = JSON.parse(event.data);
        handleNotification(data);
    };

    notificationSocket.onclose = (event) => {
        console.log('[Notifications] Disconnected, reconnecting in 3s...');
        setTimeout(connectNotificationSocket, 3000);
    };

    notificationSocket.onerror = (error) => {
        console.error('[Notifications] Error:', error);
    };
}

function handleNotification(data) {
    switch (data.type) {
        case 'room_invitation_received':
            addRoomInvitation(data);
            showToast(`${data.sender_username} invited you to ${data.room_name}`, 'info');
            break;

        case 'friend_request_received':
            showToast(`${data.sender_username} sent you a friend request`, 'info');
            // Reload to show the request (simple approach for now)
            setTimeout(() => location.reload(), 1000);
            break;

        case 'invite_response':
            if (data.status === 'accepted' && data.room_code) {
                window.location.href = `/room/${data.room_code}/`;
            } else if (data.status === 'declined') {
                showToast(data.message, 'info');
            } else {
                showToast(data.message || 'Error processing invitation.', 'error');
            }
            break;
    }
}

// ─── Room Invitation UI ─────────────────────────────────────

function addRoomInvitation(data) {
    const list = document.getElementById('invitations-list');
    const noInvitations = document.getElementById('no-invitations');
    if (noInvitations) noInvitations.remove();

    const item = document.createElement('div');
    item.className = 'list-item invitation-item';
    item.id = `invitation-${data.invitation_id}`;
    item.innerHTML = `
        <div class="list-item-info">
            <div class="avatar avatar-sm avatar-room">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>
            </div>
            <div class="list-item-details">
                <span class="list-item-name">${data.room_name}</span>
                <span class="list-item-status">from ${data.sender_username}</span>
            </div>
        </div>
        <div class="list-item-actions">
            <button class="btn btn-sm btn-success" onclick="acceptRoomInvite(${data.invitation_id}, '${data.room_code}')">Join</button>
            <button class="btn btn-sm btn-danger" onclick="rejectRoomInvite(${data.invitation_id})">Decline</button>
        </div>
    `;
    list.appendChild(item);

    // Update count badge
    updateInvitationCount();
}

function acceptRoomInvite(invitationId, roomCode) {
    if (notificationSocket && notificationSocket.readyState === WebSocket.OPEN) {
        notificationSocket.send(JSON.stringify({
            type: 'accept_room_invite',
            invitation_id: invitationId,
        }));
    }

    // Remove the invitation item
    const item = document.getElementById(`invitation-${invitationId}`);
    if (item) item.remove();
    updateInvitationCount();
}

function rejectRoomInvite(invitationId) {
    if (notificationSocket && notificationSocket.readyState === WebSocket.OPEN) {
        notificationSocket.send(JSON.stringify({
            type: 'reject_room_invite',
            invitation_id: invitationId,
        }));
    }

    const item = document.getElementById(`invitation-${invitationId}`);
    if (item) {
        item.style.opacity = '0';
        item.style.transform = 'translateX(20px)';
        setTimeout(() => {
            item.remove();
            updateInvitationCount();
        }, 300);
    }
}

function updateInvitationCount() {
    const count = document.querySelectorAll('.invitation-item').length;
    const badge = document.getElementById('invitations-count');
    if (count > 0) {
        badge.textContent = count;
        badge.style.display = 'inline-flex';
    } else {
        badge.style.display = 'none';
        // Show empty state if no invitations
        const list = document.getElementById('invitations-list');
        if (!list.querySelector('.invitation-item')) {
            list.innerHTML = '<div class="empty-state" id="no-invitations"><p>No pending invitations</p></div>';
        }
    }
}

// ─── Friend System (AJAX) ───────────────────────────────────

function sendFriendRequest() {
    const input = document.getElementById('friend-username-input');
    const username = input.value.trim();
    if (!username) return;

    fetch('/accounts/friends/send/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
            'X-CSRFToken': csrftoken,
        },
        body: `username=${encodeURIComponent(username)}`,
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            showToast(data.message, 'success');
            input.value = '';
        } else {
            showToast(data.error, 'error');
        }
    })
    .catch(err => {
        showToast('Network error. Please try again.', 'error');
    });
}

function acceptFriendRequest(friendshipId) {
    fetch(`/accounts/friends/accept/${friendshipId}/`, {
        method: 'POST',
        headers: {
            'X-CSRFToken': csrftoken,
        },
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            showToast(data.message, 'success');
            const item = document.getElementById(`friend-request-${friendshipId}`);
            if (item) {
                item.style.opacity = '0';
                setTimeout(() => {
                    item.remove();
                    location.reload(); // Reload to show in friends list
                }, 300);
            }
        } else {
            showToast(data.error, 'error');
        }
    })
    .catch(err => showToast('Network error.', 'error'));
}

function rejectFriendRequest(friendshipId) {
    fetch(`/accounts/friends/reject/${friendshipId}/`, {
        method: 'POST',
        headers: {
            'X-CSRFToken': csrftoken,
        },
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            showToast(data.message, 'info');
            const item = document.getElementById(`friend-request-${friendshipId}`);
            if (item) {
                item.style.opacity = '0';
                setTimeout(() => item.remove(), 300);
            }
        } else {
            showToast(data.error, 'error');
        }
    })
    .catch(err => showToast('Network error.', 'error'));
}

function removeFriend(friendshipId) {
    if (!confirm('Remove this friend?')) return;

    fetch(`/accounts/friends/remove/${friendshipId}/`, {
        method: 'POST',
        headers: {
            'X-CSRFToken': csrftoken,
        },
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            showToast(data.message, 'info');
            const item = document.getElementById(`friend-${friendshipId}`);
            if (item) {
                item.style.opacity = '0';
                setTimeout(() => item.remove(), 300);
            }
        } else {
            showToast(data.error, 'error');
        }
    })
    .catch(err => showToast('Network error.', 'error'));
}

// ─── Enter key for friend input ─────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    connectNotificationSocket();
    updateInvitationCount();

    const friendInput = document.getElementById('friend-username-input');
    if (friendInput) {
        friendInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                sendFriendRequest();
            }
        });
    }
});
