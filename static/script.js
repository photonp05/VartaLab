// Initialize Socket.IO
const socket = io();

// Global variables
let currentChatUser = null;
let users = [];

// DOM elements
const usersList = document.getElementById('users-list');
const searchInput = document.getElementById('search-input');
const chatWelcome = document.getElementById('chat-welcome');
const chatArea = document.getElementById('chat-area');
const chatUsername = document.getElementById('chat-username');
const chatAvatar = document.getElementById('chat-avatar');
const chatAvatarText = document.getElementById('chat-avatar-text');
const messagesContainer = document.getElementById('messages');
const messageForm = document.getElementById('message-form');
const messageInput = document.getElementById('message-input');
const mobileChatInfo = document.getElementById('mobile-chat-info');

// Initialize app
document.addEventListener('DOMContentLoaded', function() {
    loadUsers();
    setupEventListeners();
});

// Socket event listeners
socket.on('connect', function() {
    console.log('Connected to server');
});

socket.on('disconnect', function() {
    console.log('Disconnected from server');
});

socket.on('receive_message', function(data) {
    if (currentChatUser && data.sender_id === currentChatUser.id) {
        addMessageToChat(data, false);
        scrollToBottom();
    }
});

socket.on('message_sent', function(data) {
    // Message confirmation - could be used for delivery status
    console.log('Message sent successfully');
});

// Setup event listeners
function setupEventListeners() {
    // Search functionality
    searchInput.addEventListener('input', handleSearch);
    
    // Message form submission
    messageForm.addEventListener('submit', function(e) {
        e.preventDefault();
        sendMessage();
    });
    
    // Mobile sidebar controls
    window.openSidebar = function() {
        document.getElementById('sidebar').classList.add('open');
    };
    
    window.closeSidebar = function() {
        document.getElementById('sidebar').classList.remove('open');
    };
}

// Load users from server
async function loadUsers() {
    try {
        const response = await fetch('/api/users');
        if (response.ok) {
            users = await response.json();
            displayUsers(users);
        } else {
            console.error('Failed to load users');
            usersList.innerHTML = '<div class="no-users">Failed to load users</div>';
        }
    } catch (error) {
        console.error('Error loading users:', error);
        usersList.innerHTML = '<div class="no-users">Error loading users</div>';
    }
}

// Display users in sidebar
function displayUsers(usersToShow) {
    if (usersToShow.length === 0) {
        usersList.innerHTML = '<div class="no-users">No users found</div>';
        return;
    }
    
    usersList.innerHTML = usersToShow.map(user => `
        <div class="user-item" onclick="selectUser(${user.id}, '${user.username}', '${user.name}')">
            <div class="user-avatar">
                <span>${user.name.charAt(0).toUpperCase()}</span>
            </div>
            <div class="user-details">
                <h4>${user.name}</h4>
                <span>@${user.username}</span>
            </div>
        </div>
    `).join('');
}

// Handle search functionality
async function handleSearch() {
    const query = searchInput.value.trim();
    
    if (query === '') {
        displayUsers(users);
        return;
    }
    
    try {
        const response = await fetch(`/api/search/${encodeURIComponent(query)}`);
        if (response.ok) {
            const user = await response.json();
            displayUsers([user]);
        } else {
            usersList.innerHTML = '<div class="no-users">No user found</div>';
        }
    } catch (error) {
        console.error('Search error:', error);
        usersList.innerHTML = '<div class="no-users">Search error</div>';
    }
}

// Select user for chat
async function selectUser(userId, username, name) {
    // Remove active class from all users
    document.querySelectorAll('.user-item').forEach(item => {
        item.classList.remove('active');
    });
    
    // Add active class to selected user
    event.currentTarget.classList.add('active');
    
    // Set current chat user
    currentChatUser = { id: userId, username: username, name: name };
    
    // Update UI
    chatUsername.textContent = name;
    chatAvatarText.textContent = name.charAt(0).toUpperCase();
    mobileChatInfo.textContent = name;
    
    // Show chat area, hide welcome
    chatWelcome.style.display = 'none';
    chatArea.style.display = 'flex';
    
    // Load chat history
    await loadChatHistory(userId);
    
    // Focus message input
    messageInput.focus();
    
    // Close mobile sidebar
    if (window.innerWidth <= 768) {
        closeSidebar();
    }
}

// Load chat history
async function loadChatHistory(userId) {
    try {
        const response = await fetch(`/api/messages/${userId}`);
        if (response.ok) {
            const messages = await response.json();
            messagesContainer.innerHTML = '';
            
            messages.forEach(message => {
                addMessageToChat({
                    message: message.text,
                    sender_username: message.sender_username,
                    sender_name: message.sender_name,
                    timestamp: message.timestamp
                }, message.is_own);
            });
            
            scrollToBottom();
        }
    } catch (error) {
        console.error('Error loading chat history:', error);
    }
}

// Send message
function sendMessage() {
    const message = messageInput.value.trim();
    
    if (!message || !currentChatUser) {
        return;
    }
    
    // Emit message to server
    socket.emit('send_message', {
        receiver_id: currentChatUser.id,
        message: message
    });
    
    // Add message to chat immediately (optimistic update)
    addMessageToChat({
        message: message,
        sender_username: 'You',
        sender_name: 'You',
        timestamp: new Date().toISOString()
    }, true);
    
    // Clear input and scroll
    messageInput.value = '';
    scrollToBottom();
}

// Add message to chat
function addMessageToChat(data, isOwn) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${isOwn ? 'own' : ''}`;
    
    const avatarLetter = isOwn ? 'You'.charAt(0) : data.sender_name.charAt(0);
    const displayName = isOwn ? 'You' : data.sender_name;
    
    // Format timestamp
    const timestamp = new Date(data.timestamp);
    const timeString = timestamp.toLocaleTimeString([], { 
        hour: '2-digit', 
        minute: '2-digit' 
    });
    
    messageDiv.innerHTML = `
        <div class="message-avatar">
            <span>${avatarLetter.toUpperCase()}</span>
        </div>
        <div class="message-content">
            <div class="message-text">${escapeHtml(data.message)}</div>
            <div class="message-time">${timeString}</div>
        </div>
    `;
    
    messagesContainer.appendChild(messageDiv);
}

// Scroll to bottom of messages
function scrollToBottom() {
    setTimeout(() => {
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }, 100);
}

// Escape HTML to prevent XSS
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Handle window resize for mobile responsiveness
window.addEventListener('resize', function() {
    if (window.innerWidth > 768) {
        document.getElementById('sidebar').classList.remove('open');
    }
});

// Handle Enter key in message input
messageInput.addEventListener('keypress', function(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

// Auto-focus message input when chat is selected
document.addEventListener('click', function(e) {
    if (e.target.closest('.user-item') && currentChatUser) {
        setTimeout(() => {
            messageInput.focus();
        }, 100);
    }
});

// Handle connection errors
socket.on('connect_error', function(error) {
    console.error('Connection error:', error);
});

// Handle reconnection
socket.on('reconnect', function() {
    console.log('Reconnected to server');
    if (currentChatUser) {
        loadChatHistory(currentChatUser.id);
    }
});

// Prevent form submission on page refresh
window.addEventListener('beforeunload', function() {
    socket.disconnect();
});
