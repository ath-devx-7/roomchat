/**
 * Room JavaScript
 * Handles: Chat WebSocket, messaging actions (send, reply, edit, delete),
 * active users display, owner controls, and friend invitation.
 */

// ─── Constants & Setup ──────────────────────────────────────
const container = document.getElementById('room-page');
const roomCode = container.getAttribute('data-room-code');
const currentUserId = parseInt(container.getAttribute('data-user-id'));
const currentUsername = container.getAttribute('data-username');

let chatSocket = null;
let replyToId = null;
let editMessageId = null;
let activeUsers = [];
let friendsList = [];

// Set once we are leaving for good, so onclose does not reconnect us into a
// room we were just removed from while the redirect is still pending.
let kicked = false;
let roomDeleted = false;
let pendingInviteUserId = null;

// Close codes the server uses to refuse a connection. The server accepts the
// socket before closing so these actually reach us; reconnecting is pointless.
const FATAL_CLOSE_CODES = {
    4001: 'This room is full.',
    4003: 'You must be signed in to join a room.',
    4004: 'This room no longer exists.',
};

// ─── WebSocket Connection ───────────────────────────────────
function connectChatSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${protocol}//${window.location.host}/ws/chat/${roomCode}/`;

    chatSocket = new WebSocket(url);

    chatSocket.onopen = () => {
        console.log('[Chat] Connected');
    };

    chatSocket.onmessage = (event) => {
        const data = JSON.parse(event.data);
        handleChatMessage(data);
    };

    chatSocket.onclose = (event) => {
        if (kicked || roomDeleted) return;

        const fatalReason = FATAL_CLOSE_CODES[event.code];
        if (fatalReason) {
            showToast(fatalReason, 'error');
            setTimeout(() => { window.location.href = '/dashboard/'; }, 2000);
            return;
        }

        console.log('[Chat] Disconnected, reconnecting in 3s...');
        setTimeout(connectChatSocket, 3000);
    };

    chatSocket.onerror = (error) => {
        console.error('[Chat] Error:', error);
    };
}

function handleChatMessage(data) {
    switch (data.type) {
        case 'user_joined':
            appendSystemMessage(`<span class="highlight">${data.username}</span> joined the room`);
            break;

        case 'user_left':
            appendSystemMessage(`<span class="highlight">${data.username}</span> left the room`);
            break;

        case 'message_created':
            appendMessage(data);
            break;

        case 'message_edited':
            updateMessageDOM(data);
            break;

        case 'message_deleted':
            deleteMessageDOM(data.message_id);
            break;

        case 'active_users_updated':
            activeUsers = data.users;
            updateActiveUsersUI();
            updateInviteFriendsUI();
            break;

        case 'user_kicked':
            kicked = true;
            showToast(data.message || 'You have been kicked from the room.', 'error');
            setTimeout(() => {
                window.location.href = '/dashboard/';
            }, 1500);
            break;

        case 'user_kicked_broadcast':
            appendSystemMessage(`<span class="highlight">${data.username}</span> was kicked from the room`);
            break;

        case 'ownership_transferred':
            appendSystemMessage(`Ownership was transferred to <span class="highlight">${data.new_owner_username}</span>`);
            // Highlight owner UI change
            break;

        case 'room_deleted':
            roomDeleted = true;
            showToast(data.message || 'This room has been deleted by the owner.', 'warning');
            setTimeout(() => {
                window.location.href = '/dashboard/';
            }, 2000);
            break;

        case 'room_info':
            updateRoomInfoUI(data);
            break;

        case 'invite_sent':
            resolvePendingInvite(true);
            showToast(data.message, 'success');
            break;

        case 'error':
            resolvePendingInvite(false);
            showToast(data.message, 'error');
            break;

        default:
            console.warn('[Chat] Unhandled message type:', data.type, data);
    }
}

// ─── Helpers: Time formatting ──────────────────────────────
function formatTime(isoString) {
    const d = new Date(isoString);
    const year = d.getFullYear();
    const month = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    const hours = String(d.getHours()).padStart(2, '0');
    const minutes = String(d.getMinutes()).padStart(2, '0');
    return `${year}-${month}-${day} ${hours}:${minutes}`;
}

// ─── DOM Message Rendering ──────────────────────────────────
function appendMessage(data) {
    const chatMessages = document.getElementById('chat-messages');
    
    // Remove welcome screen if it exists
    const welcomeScreen = document.getElementById('chat-welcome');
    if (welcomeScreen) welcomeScreen.remove();

    const isMe = data.sender_id === currentUserId;
    const msgId = data.message_id;

    const msgDiv = document.createElement('div');
    msgDiv.className = 'message';
    msgDiv.id = `message-${msgId}`;
    msgDiv.setAttribute('data-message-id', msgId);

    // Escape contents to prevent XSS
    const senderEscaped = escapeHTML(data.sender_username);
    const contentEscaped = escapeHTML(data.content);
    const timeFormatted = formatTime(data.created_at);

    // Initial avatar letter
    const avatarLetter = data.sender_username.charAt(0).toUpperCase();

    // Reply preview block HTML
    let replyPreviewHTML = '';
    if (data.reply_to) {
        const replyUserEscaped = escapeHTML(data.reply_to.sender_username);
        const replyContentEscaped = escapeHTML(data.reply_to.content);
        replyPreviewHTML = `
            <div class="message-reply-preview">
                <span class="reply-user">${replyUserEscaped}</span>
                <span class="reply-text">${replyContentEscaped}</span>
            </div>
        `;
    }

    // Action buttons (Escape strings for safe onclick payload)
    const senderJs = escapeJSString(data.sender_username);
    const contentJs = escapeJSString(data.content);

    let actionsHTML = '';
    actionsHTML += `
        <button class="message-action-btn btn-reply" onclick="setReplyTo(${msgId}, '${senderJs}', '${contentJs}')" title="Reply">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <polyline points="9 17 4 12 9 7"></polyline>
                <path d="M20 18v-2a4 4 0 0 0-4-4H4"></path>
            </svg>
        </button>
    `;

    if (isMe) {
        actionsHTML += `
            <button class="message-action-btn btn-edit" onclick="setEditMessage(${msgId}, '${contentJs}')" title="Edit">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path><path d="M18.5 2.5a2.121 2.121 0 1 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path></svg>
            </button>
            <button class="message-action-btn btn-delete" onclick="deleteMessage(${msgId})" title="Delete">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
            </button>
        `;
    }

    msgDiv.innerHTML = `
        <div class="avatar avatar-sm message-avatar">${avatarLetter}</div>
        <div class="message-body">
            <div class="message-header">
                <span class="message-sender">${senderEscaped}</span>
                <span class="message-time">${timeFormatted}</span>
                <span class="message-edited" style="display:none;">(edited)</span>
            </div>
            ${replyPreviewHTML}
            <div class="message-content">${contentEscaped}</div>
        </div>
        <div class="message-actions">
            ${actionsHTML}
        </div>
    `;

    chatMessages.appendChild(msgDiv);
    scrollToBottom();
}

function updateMessageDOM(data) {
    const msgDiv = document.getElementById(`message-${data.message_id}`);
    if (!msgDiv) return;

    const contentDiv = msgDiv.querySelector('.message-content');
    const editedSpan = msgDiv.querySelector('.message-edited');

    if (contentDiv) {
        contentDiv.textContent = data.content;
    }
    if (editedSpan) {
        editedSpan.style.display = 'inline';
    }

    // Update the onclick arguments for edit button to reflect new content
    const editBtn = msgDiv.querySelector('.btn-edit');
    if (editBtn) {
        const contentJs = escapeJSString(data.content);
        editBtn.setAttribute('onclick', `setEditMessage(${data.message_id}, '${contentJs}')`);
    }
}

function deleteMessageDOM(messageId) {
    const msgDiv = document.getElementById(`message-${messageId}`);
    if (!msgDiv) return;

    msgDiv.classList.add('message-deleted');
    
    const contentDiv = msgDiv.querySelector('.message-content');
    if (contentDiv) {
        contentDiv.textContent = 'This message was deleted.';
        contentDiv.style.fontStyle = 'italic';
        contentDiv.style.color = 'var(--text-muted)';
    }

    // Remove action buttons and reply preview
    const actionsDiv = msgDiv.querySelector('.message-actions');
    if (actionsDiv) actionsDiv.remove();
}

function appendSystemMessage(content) {
    const chatMessages = document.getElementById('chat-messages');
    
    // Remove welcome screen if it exists
    const welcomeScreen = document.getElementById('chat-welcome');
    if (welcomeScreen) welcomeScreen.remove();

    const sysDiv = document.createElement('div');
    sysDiv.className = 'system-message';
    sysDiv.innerHTML = content;

    chatMessages.appendChild(sysDiv);
    scrollToBottom();
}

function scrollToBottom() {
    const chatMessages = document.getElementById('chat-messages');
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// ─── Messaging Controls (Reply / Edit / Send) ────────────────
window.setReplyTo = function(messageId, senderUsername, content) {
    // Cancel Edit if active
    cancelEdit();

    replyToId = messageId;

    const replyBar = document.getElementById('reply-bar');
    const replyUser = document.getElementById('reply-bar-user');
    const replyText = document.getElementById('reply-bar-text');

    replyUser.textContent = senderUsername;
    replyText.textContent = content.length > 60 ? content.slice(0, 60) + '...' : content;
    
    replyBar.style.display = 'flex';
    document.getElementById('message-input').focus();
};

window.cancelReply = function() {
    replyToId = null;
    document.getElementById('reply-bar').style.display = 'none';
};

window.setEditMessage = function(messageId, content) {
    // Cancel Reply if active
    cancelReply();

    editMessageId = messageId;

    const editBar = document.getElementById('edit-bar');
    const input = document.getElementById('message-input');

    input.value = content;
    editBar.style.display = 'flex';
    input.focus();
};

window.cancelEdit = function() {
    editMessageId = null;
    document.getElementById('edit-bar').style.display = 'none';
    document.getElementById('message-input').value = '';
};

window.sendMessage = function() {
    const input = document.getElementById('message-input');
    const content = input.value.trim();
    if (!content || !chatSocket || chatSocket.readyState !== WebSocket.OPEN) return;

    if (editMessageId !== null) {
        // Send edit action
        chatSocket.send(JSON.stringify({
            type: 'edit_message',
            message_id: editMessageId,
            content: content
        }));
        cancelEdit();
    } else if (replyToId !== null) {
        // Send reply action
        chatSocket.send(JSON.stringify({
            type: 'reply_message',
            reply_to_id: replyToId,
            content: content
        }));
        cancelReply();
    } else {
        // Send normal message
        chatSocket.send(JSON.stringify({
            type: 'send_message',
            content: content
        }));
    }

    input.value = '';
};

window.deleteMessage = function(messageId) {
    if (!confirm('Are you sure you want to delete this message?')) return;
    if (chatSocket && chatSocket.readyState === WebSocket.OPEN) {
        chatSocket.send(JSON.stringify({
            type: 'delete_message',
            message_id: messageId
        }));
    }
};

// ─── Owner Controls Actions ─────────────────────────────────
window.kickUser = function(userId) {
    if (!confirm('Are you sure you want to kick this user?')) return;
    if (chatSocket && chatSocket.readyState === WebSocket.OPEN) {
        chatSocket.send(JSON.stringify({
            type: 'kick_user',
            user_id: userId
        }));
    }
};

window.transferOwnership = function(userId) {
    if (!confirm('Are you sure you want to transfer ownership of this room to this user? This cannot be undone.')) return;
    if (chatSocket && chatSocket.readyState === WebSocket.OPEN) {
        chatSocket.send(JSON.stringify({
            type: 'transfer_ownership',
            user_id: userId
        }));
    }
};

window.deleteRoom = function() {
    if (!confirm('Are you sure you want to delete this room? This action is permanent.')) return;
    if (chatSocket && chatSocket.readyState === WebSocket.OPEN) {
        chatSocket.send(JSON.stringify({
            type: 'delete_room'
        }));
    }
};

window.inviteFriend = function(userId) {
    if (!chatSocket || chatSocket.readyState !== WebSocket.OPEN) return;

    chatSocket.send(JSON.stringify({
        type: 'send_room_invite',
        user_id: userId
    }));

    // Disable while in flight; the server confirms with invite_sent or rejects
    // with an error, and we only commit to "Invited" on confirmation.
    pendingInviteUserId = userId;
    const btn = document.getElementById(`invite-btn-${userId}`);
    if (btn) {
        btn.disabled = true;
        btn.textContent = 'Inviting...';
    }
};

function resolvePendingInvite(succeeded) {
    if (pendingInviteUserId === null) return;

    const btn = document.getElementById(`invite-btn-${pendingInviteUserId}`);
    if (btn) {
        btn.disabled = succeeded;
        btn.textContent = succeeded ? 'Invited' : 'Invite';
    }
    pendingInviteUserId = null;
}

// ─── Room UI Updates ────────────────────────────────────────
function updateRoomInfoUI(data) {
    document.getElementById('room-name').textContent = data.room_name;
    document.getElementById('room-description').textContent = data.room_description;
    
    const capacityText = `${activeUsers.length} / ${data.capacity}`;
    document.getElementById('room-capacity').innerHTML = `
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path>
            <circle cx="9" cy="7" r="4"></circle>
            <path d="M23 21v-2a4 4 0 0 0-3-3.87"></path>
            <path d="M16 3.13a4 4 0 0 1 0 7.75"></path>
        </svg>
        <span id="active-count">${activeUsers.length}</span> / ${data.capacity}
    `;

    // Show/hide owner controls section
    const ownerControlsSection = document.getElementById('owner-controls');
    if (data.owner_id === currentUserId) {
        ownerControlsSection.style.display = 'block';
    } else {
        ownerControlsSection.style.display = 'none';
    }
}

function updateActiveUsersUI() {
    const listContainer = document.getElementById('active-users-list');
    listContainer.innerHTML = '';

    // Update counts
    document.getElementById('online-count-badge').textContent = activeUsers.length;
    const activeCountSpan = document.getElementById('active-count');
    if (activeCountSpan) activeCountSpan.textContent = activeUsers.length;

    // Check if the current user is the owner
    const amIOwner = activeUsers.some(u => u.user_id === currentUserId && u.is_owner);

    activeUsers.forEach(user => {
        const userDiv = document.createElement('div');
        userDiv.className = 'sidebar-user';
        userDiv.id = `active-user-${user.user_id}`;

        const ownerBadge = user.is_owner ? '<span class="owner-badge">Owner</span>' : '';

        // Add actions if current user is owner and this user is not the owner
        let actionsHTML = '';
        if (amIOwner && user.user_id !== currentUserId) {
            actionsHTML = `
                <div class="sidebar-user-actions">
                    <button class="sidebar-user-btn btn-transfer" onclick="transferOwnership(${user.user_id})" title="Transfer Ownership">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><path d="M23 21v-2a4 4 0 0 0-3-3.87"></path><path d="M16 3.13a4 4 0 0 1 0 7.75"></path></svg>
                    </button>
                    <button class="sidebar-user-btn btn-kick" onclick="kickUser(${user.user_id})" title="Kick User">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
                    </button>
                </div>
            `;
        }

        userDiv.innerHTML = `
            <div class="sidebar-user-info">
                <span class="online-dot"></span>
                <span class="sidebar-user-name">
                    ${escapeHTML(user.username)}
                    ${ownerBadge}
                </span>
            </div>
            ${actionsHTML}
        `;
        listContainer.appendChild(userDiv);
    });
}

function updateInviteFriendsUI() {
    const listContainer = document.getElementById('invite-friend-list');
    listContainer.innerHTML = '';

    // Filter out friends who are already inside the room
    const inviteableFriends = friendsList.filter(f => !activeUsers.some(u => u.user_id === f.user_id));

    if (inviteableFriends.length === 0) {
        listContainer.innerHTML = '<div class="empty-state"><p>No friends to invite</p></div>';
        return;
    }

    inviteableFriends.forEach(friend => {
        const itemDiv = document.createElement('div');
        itemDiv.className = 'invite-friend-item';
        itemDiv.innerHTML = `
            <span class="invite-friend-name">${escapeHTML(friend.username)}</span>
            <button class="invite-btn" id="invite-btn-${friend.user_id}" onclick="inviteFriend(${friend.user_id})">Invite</button>
        `;
        listContainer.appendChild(itemDiv);
    });
}

// ─── Fetch Friends List ─────────────────────────────────────
function fetchFriends() {
    fetch('/accounts/friends/')
        .then(res => res.json().then(data => {
            if (!res.ok) throw new Error(firstErrorMessage(data) || 'Could not load your friends list.');
            return data;
        }))
        .then(data => {
            friendsList = data.friends || [];
            updateInviteFriendsUI();
        })
        .catch(err => {
            console.error('Error fetching friends list:', err);
            showToast(err.message || 'Could not load your friends list.', 'error');
        });
}

// The @json_validation_errors middleware replies with {"errors": {field: msg}}.
function firstErrorMessage(data) {
    if (!data) return null;
    if (data.error) return data.error;
    if (data.errors) return Object.values(data.errors)[0];
    return null;
}

// ─── Copy Room Code to Clipboard ────────────────────────────
window.copyRoomCode = function() {
    navigator.clipboard.writeText(roomCode)
        .then(() => showToast('Room code copied to clipboard!', 'success'))
        .catch(err => showToast('Failed to copy room code.', 'error'));
};

// ─── Utilities: Escape HTML / JS ───────────────────────────
function escapeHTML(str) {
    if (!str) return '';
    return str.replace(/[&<>'"]/g, 
        tag => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[tag] || tag)
    );
}

function escapeJSString(str) {
    if (!str) return '';
    return str.replace(/\\/g, '\\\\')
              .replace(/'/g, "\\'")
              .replace(/"/g, '\\"')
              .replace(/\n/g, '\\n')
              .replace(/\r/g, '\\r');
}

// ─── Initializer ────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    connectChatSocket();
    fetchFriends();
    scrollToBottom();

    // Setup input message enter submit trigger
    const input = document.getElementById('message-input');
    if (input) {
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                sendMessage();
            }
        });
    }
});
