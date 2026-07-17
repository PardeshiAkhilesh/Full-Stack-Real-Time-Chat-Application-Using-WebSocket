// --- SYSTEM CONFIG & CONSTANTS ---
const BASE_HOST = window.location.hostname === '' ? 'localhost:8000' : window.location.host;
const API_URL = `${window.location.protocol}//${BASE_HOST}`;
const WS_PROTOCOL = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
const WS_URL = `${WS_PROTOCOL}//${BASE_HOST}/ws/chat`;

// --- STATE MANAGEMENT ---
const state = {
    token: localStorage.getItem('token') || null,
    user: JSON.parse(localStorage.getItem('user')) || null,
    rooms: [],
    activeRoom: null,
    ws: null,
    typingUsers: new Set(),
    typingTimeout: null,
    isTyping: false,
    selectedFile: null,
    
    // WebRTC properties
    peerConnection: null,
    localStream: null,
    remoteStream: null,
    currentCall: null, // { status: 'idle'|'ringing'|'active', role: 'caller'|'callee', targetUserId: int, callType: 'video'|'audio' }
    iceServers: [],
    roomUsers: [],
    bufferedIceCandidates: [],
    pendingCallType: 'video'
};

// --- DOM ELEMENTS REFERENCE ---
const dom = {
    authScreen: document.getElementById('auth-screen'),
    chatScreen: document.getElementById('chat-screen'),
    loginForm: document.getElementById('login-form'),
    registerForm: document.getElementById('register-form'),
    toRegister: document.getElementById('to-register'),
    toLogin: document.getElementById('to-login'),
    authTitle: document.getElementById('auth-title'),
    authSubtitle: document.getElementById('auth-subtitle'),
    
    profileUsername: document.getElementById('profile-username'),
    userAvatar: document.getElementById('user-avatar'),
    logoutBtn: document.getElementById('logout-btn'),
    
    roomsList: document.getElementById('rooms-list'),
    roomsLoading: document.getElementById('rooms-loading'),
    roomsEmpty: document.getElementById('rooms-empty'),
    openCreateRoom: document.getElementById('open-create-room'),
    
    noChatSelected: document.getElementById('no-chat-selected'),
    activeChat: document.getElementById('active-chat'),
    activeRoomName: document.getElementById('active-room-name'),
    activeRoomDesc: document.getElementById('active-room-desc'),
    activeRoomParticipants: document.getElementById('active-room-participants'),
    
    messagesViewport: document.getElementById('messages-viewport'),
    typingIndicator: document.getElementById('typing-indicator'),
    typingText: document.getElementById('typing-text'),
    
    messageForm: document.getElementById('message-form'),
    messageInput: document.getElementById('message-input'),
    attachBtn: document.getElementById('attach-btn'),
    fileInput: document.getElementById('file-input'),
    filePreviewBanner: document.getElementById('file-preview-banner'),
    previewFileName: document.getElementById('preview-file-name'),
    cancelFileUpload: document.getElementById('cancel-file-upload'),
    sendBtn: document.getElementById('send-btn'),
    
    createRoomModal: document.getElementById('create-room-modal'),
    createRoomForm: document.getElementById('create-room-form'),
    closeCreateRoomModal: document.getElementById('close-create-room-modal'),
    cancelCreateRoom: document.getElementById('cancel-create-room'),
    roomName: document.getElementById('room-name'),
    roomDesc: document.getElementById('room-desc'),
    roomLimit: document.getElementById('room-limit'),
    
    videoCallPanel: document.getElementById('video-call-panel'),
    videoStream: document.getElementById('video-stream'),
    videoCallBtn: document.getElementById('video-call-btn'),
    endCallBtn: document.getElementById('end-call-btn'),
    
    // WebRTC Elements
    webrtcVideoCallBtn: document.getElementById('webrtc-video-call-btn'),
    webrtcAudioCallBtn: document.getElementById('webrtc-audio-call-btn'),
    callSelectorModal: document.getElementById('call-selector-modal'),
    closeCallSelectorBtn: document.getElementById('close-call-selector-btn'),
    callUsersList: document.getElementById('call-users-list'),
    incomingCallModal: document.getElementById('incoming-call-modal'),
    callerName: document.getElementById('caller-name'),
    callTypeLabel: document.getElementById('call-type-label'),
    acceptCallBtn: document.getElementById('accept-call-btn'),
    rejectCallBtn: document.getElementById('reject-call-btn'),
    webrtcCallOverlay: document.getElementById('webrtc-call-overlay'),
    remoteVideo: document.getElementById('remote-video'),
    localVideo: document.getElementById('local-video'),
    audioCallPlaceholder: document.getElementById('audio-call-placeholder'),
    callStatusOverlay: document.getElementById('call-status-overlay'),
    callStatusText: document.getElementById('call-status-text'),
    toggleMicBtn: document.getElementById('toggle-mic-btn'),
    toggleVideoBtn: document.getElementById('toggle-video-btn'),
    hangupCallBtn: document.getElementById('hangup-call-btn'),
    
    toastContainer: document.getElementById('toast-container')
};

// --- INITIALIZATION ---
document.addEventListener('DOMContentLoaded', () => {
    setupEventListeners();
    checkAuth();
});

// --- ROUTING / SCREEN ROUTER ---
function showScreen(screen) {
    if (screen === 'auth') {
        dom.authScreen.classList.add('active');
        dom.chatScreen.classList.remove('active');
    } else {
        dom.authScreen.classList.remove('active');
        dom.chatScreen.classList.add('active');
    }
}

function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `
        <span class="toast-message">${message}</span>
    `;
    dom.toastContainer.appendChild(toast);
    
    setTimeout(() => {
        toast.style.animation = 'fadeOut 0.3s ease forwards';
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

// --- AUTHENTICATION FLOWS ---
function checkAuth() {
    if (state.token && state.user) {
        showScreen('chat');
        initWorkspace();
    } else {
        showScreen('auth');
    }
}

function setupEventListeners() {
    // Switch forms
    dom.toRegister.addEventListener('click', (e) => {
        e.preventDefault();
        dom.loginForm.classList.remove('active');
        dom.registerForm.classList.add('active');
        dom.authTitle.textContent = 'Create Account';
        dom.authSubtitle.textContent = 'Register to join the real-time chat spaces';
    });
    
    dom.toLogin.addEventListener('click', (e) => {
        e.preventDefault();
        dom.registerForm.classList.remove('active');
        dom.loginForm.classList.add('active');
        dom.authTitle.textContent = 'Welcome Back';
        dom.authSubtitle.textContent = 'Enter your credentials to enter the chat workspace';
    });
    
    // Auth actions
    dom.loginForm.addEventListener('submit', handleLogin);
    dom.registerForm.addEventListener('submit', handleRegister);
    dom.logoutBtn.addEventListener('click', handleLogout);
    
    // Create room actions
    dom.openCreateRoom.addEventListener('click', () => dom.createRoomModal.classList.add('active'));
    dom.closeCreateRoomModal.addEventListener('click', () => dom.createRoomModal.classList.remove('active'));
    dom.cancelCreateRoom.addEventListener('click', () => dom.createRoomModal.classList.remove('active'));
    dom.createRoomForm.addEventListener('submit', handleCreateRoom);
    
    // File inputs
    dom.attachBtn.addEventListener('click', () => dom.fileInput.click());
    dom.fileInput.addEventListener('change', handleFileSelection);
    dom.cancelFileUpload.addEventListener('click', handleCancelFile);
    
    // Message typing events
    dom.messageInput.addEventListener('input', handleTypingInput);
    dom.messageForm.addEventListener('submit', handleSendMessage);

    // Video call actions
    if (dom.videoCallBtn) dom.videoCallBtn.addEventListener('click', startVideoCall);
    if (dom.endCallBtn) dom.endCallBtn.addEventListener('click', stopVideoCall);

    // WebRTC Calling actions
    dom.webrtcVideoCallBtn.addEventListener('click', () => openCallSelector('video'));
    dom.webrtcAudioCallBtn.addEventListener('click', () => openCallSelector('audio'));
    dom.closeCallSelectorBtn.addEventListener('click', () => dom.callSelectorModal.classList.remove('active'));
    dom.acceptCallBtn.addEventListener('click', acceptIncomingCall);
    dom.rejectCallBtn.addEventListener('click', rejectIncomingCall);
    dom.hangupCallBtn.addEventListener('click', hangupCall);
    dom.toggleMicBtn.addEventListener('click', toggleMuteMic);
    dom.toggleVideoBtn.addEventListener('click', toggleMuteVideo);
}

async function handleLogin(e) {
    e.preventDefault();
    const username = dom.loginForm.elements['login-username'].value.trim();
    const password = dom.loginForm.elements['login-password'].value;
    
    try {
        const response = await fetch(`${API_URL}/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        });
        
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || 'Authentication failed');
        }
        
        const data = await response.json();
        
        // Save state
        state.token = data.access_token;
        state.user = data.user;
        localStorage.setItem('token', state.token);
        localStorage.setItem('user', JSON.stringify(state.user));
        
        showToast('Login successful', 'success');
        showScreen('chat');
        initWorkspace();
        
        // Reset form
        dom.loginForm.reset();
    } catch (error) {
        showToast(error.message, 'error');
    }
}

async function handleRegister(e) {
    e.preventDefault();
    const username = dom.registerForm.elements['register-username'].value.trim();
    const email = dom.registerForm.elements['register-email'].value.trim();
    const password = dom.registerForm.elements['register-password'].value;
    
    try {
        const response = await fetch(`${API_URL}/auth/register`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, email, password })
        });
        
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || 'Registration failed');
        }
        
        showToast('Account created! Please log in.', 'success');
        dom.toLogin.click(); // Toggle back to login
        dom.registerForm.reset();
    } catch (error) {
        showToast(error.message, 'error');
    }
}

function handleLogout() {
    stopVideoCall();
    // Terminate WS connection
    if (state.ws) {
        state.ws.close();
    }
    
    state.token = null;
    state.user = null;
    state.rooms = [];
    state.activeRoom = null;
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    
    dom.activeChat.classList.remove('active');
    dom.noChatSelected.classList.add('active');
    
    showScreen('auth');
    showToast('Logged out successfully', 'info');
}

// --- WORKSPACE CHANNELS & ROOM MANAGERS ---
async function initWorkspace() {
    // Show profile info
    dom.profileUsername.textContent = state.user.username;
    dom.userAvatar.textContent = state.user.username.charAt(0).toUpperCase();
    
    fetchIceServers();
    await fetchRooms();
}

async function fetchRooms() {
    dom.roomsLoading.classList.add('active');
    dom.roomsEmpty.classList.remove('active');
    dom.roomsList.innerHTML = '';
    
    try {
        const response = await fetch(`${API_URL}/rooms/`, {
            headers: { 'Authorization': `Bearer ${state.token}` }
        });
        
        if (!response.ok) throw new Error('Could not load channels');
        
        state.rooms = await response.json();
        
        dom.roomsLoading.classList.remove('active');
        
        if (state.rooms.length === 0) {
            dom.roomsEmpty.classList.add('active');
        } else {
            renderRooms();
        }
    } catch (error) {
        dom.roomsLoading.classList.remove('active');
        showToast(error.message, 'error');
    }
}

function renderRooms() {
    dom.roomsList.innerHTML = '';
    state.rooms.forEach(room => {
        const li = document.createElement('li');
        li.className = `room-item ${state.activeRoom && state.activeRoom.id === room.id ? 'active' : ''}`;
        li.setAttribute('data-id', room.id);
        
        li.innerHTML = `
            <div class="room-item-details">
                <div class="room-name-wrapper">
                    <span class="room-hash">#</span>
                    <span class="room-title">${escapeHTML(room.name)}</span>
                </div>
                <span class="room-desc">${escapeHTML(room.description || 'No description provided')}</span>
            </div>
            <span class="room-meta-badge">${room.max_participants} max</span>
        `;
        
        li.addEventListener('click', () => selectRoom(room));
        dom.roomsList.appendChild(li);
    });
}

async function handleCreateRoom(e) {
    e.preventDefault();
    const name = dom.roomName.value.trim();
    const description = dom.roomDesc.value.trim();
    const max_participants = parseInt(dom.roomLimit.value);
    
    try {
        const response = await fetch(`${API_URL}/rooms/`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${state.token}`
            },
            body: JSON.stringify({ name, description, max_participants })
        });
        
        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.detail || 'Could not create channel');
        }
        
        const newRoom = await response.json();
        showToast(`Channel #${newRoom.name} created!`, 'success');
        dom.createRoomModal.classList.remove('active');
        dom.createRoomForm.reset();
        
        // Reload rooms list and auto-select
        await fetchRooms();
        selectRoom(newRoom);
    } catch (error) {
        showToast(error.message, 'error');
    }
}

// --- CHAT WORKSPACE & WEBSOCKET ENGINE ---
async function selectRoom(room) {
    stopVideoCall();
    // Set active style in sidebar
    document.querySelectorAll('.room-item').forEach(item => {
        item.classList.remove('active');
        if (parseInt(item.getAttribute('data-id')) === room.id) {
            item.classList.add('active');
        }
    });
    
    state.activeRoom = room;
    dom.activeRoomName.textContent = `# ${room.name}`;
    dom.activeRoomDesc.textContent = room.description || 'No description provided';
    dom.activeRoomParticipants.innerHTML = `
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle></svg>
        <span>Limit: ${room.max_participants} users</span>
    `;
    
    dom.noChatSelected.classList.remove('active');
    dom.activeChat.classList.add('active');
    dom.messagesViewport.innerHTML = '<div class="spinner" style="margin: auto;"></div>';
    
    // Clear typing indicator state
    state.typingUsers.clear();
    updateTypingIndicator();
    
    // Disconnect old WS
    if (state.ws) {
        state.ws.close();
    }
    
    // Load historical messages
    await fetchMessages(room.id);
    
    // Connect to websocket
    setupWebSocket(room.id);
}

async function fetchMessages(roomId) {
    try {
        const response = await fetch(`${API_URL}/rooms/${roomId}/messages?limit=100`, {
            headers: { 'Authorization': `Bearer ${state.token}` }
        });
        
        if (!response.ok) throw new Error('Could not fetch message history');
        
        const messages = await response.json();
        dom.messagesViewport.innerHTML = '';
        messages.forEach(msg => appendMessageToViewport(msg));
        scrollToBottom();
    } catch (error) {
        dom.messagesViewport.innerHTML = '';
        showToast(error.message, 'error');
    }
}

function setupWebSocket(roomId) {
    state.ws = new WebSocket(`${WS_URL}/${roomId}?token=${state.token}`);
    
    state.ws.onopen = () => {
        showToast(`Connected to room websocket`, 'success');
    };
    
    state.ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        handleIncomingWSMessage(data);
    };
    
    state.ws.onerror = (error) => {
        console.error('WS Error:', error);
        showToast('Connection interrupted', 'error');
    };
    
    state.ws.onclose = (event) => {
        console.log('WS Connection Closed:', event.reason);
    };
}

function handleIncomingWSMessage(data) {
    if (data.type === 'new_message') {
        const msg = {
            id: data.message_id || Date.now(),
            uuid: data.message_id,
            user_id: data.user_id,
            user: { username: data.username }, // Mock relationship for ease of display
            content: data.content,
            message_type: data.message_type || 'text',
            created_at: data.timestamp
        };
        appendMessageToViewport(msg);
        scrollToBottom();
    } 
    else if (data.type === 'user_joined') {
        appendSystemMessage(data.message);
        scrollToBottom();
        if (data.user_id !== state.user.id) {
            if (!state.roomUsers.some(u => u.user_id === data.user_id)) {
                state.roomUsers.push({ user_id: data.user_id, username: data.username });
            }
        }
    } 
    else if (data.type === 'user_left') {
        appendSystemMessage(data.message);
        scrollToBottom();
        state.roomUsers = state.roomUsers.filter(u => u.user_id !== data.user_id);
    }
    else if (data.type === 'room_users') {
        state.roomUsers = data.users.filter(u => u.user_id !== state.user.id);
    }
    else if (data.type === 'call_invite') {
        handleIncomingCallInvite(data);
    }
    else if (data.type === 'call_accept') {
        handleCallAccepted(data);
    }
    else if (data.type === 'call_offer') {
        handleIncomingCallOffer(data);
    }
    else if (data.type === 'call_answer') {
        handleIncomingCallAnswer(data);
    }
    else if (data.type === 'ice_candidate') {
        handleIncomingIceCandidate(data);
    }
    else if (data.type === 'call_reject') {
        handleCallRejected(data);
    }
    else if (data.type === 'call_busy') {
        handleCallBusy(data);
    }
    else if (data.type === 'call_end') {
        handleCallEnded(data);
    }
    else if (data.type === 'user_typing') {
        if (data.user_id !== state.user.id) {
            if (data.typing) {
                state.typingUsers.add(data.username);
            } else {
                state.typingUsers.delete(data.username);
            }
            updateTypingIndicator();
        }
    }
}

// --- FILE UPLOADS & BANNER ---
function handleFileSelection(e) {
    const file = e.target.files[0];
    if (!file) return;
    
    state.selectedFile = file;
    dom.previewFileName.textContent = `${file.name} (${formatBytes(file.size)})`;
    dom.filePreviewBanner.classList.add('active');
    dom.messageInput.focus();
}

function handleCancelFile() {
    state.selectedFile = null;
    dom.fileInput.value = '';
    dom.filePreviewBanner.classList.remove('active');
}

async function uploadFileToServer(file) {
    const formData = new FormData();
    formData.append('file', file);
    
    const response = await fetch(`${API_URL}/upload-file/`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${state.token}` },
        body: formData
    });
    
    if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || 'File upload failed');
    }
    
    const data = await response.json();
    return data.file_info;
}

// --- COMPOSER & MESSAGE SENDER ---
async function handleSendMessage(e) {
    e.preventDefault();
    const contentText = dom.messageInput.value.trim();
    const file = state.selectedFile;
    
    if (!contentText && !file) return;
    if (!state.ws || state.ws.readyState !== WebSocket.OPEN) {
        showToast('WebSocket connection is not active', 'error');
        return;
    }
    
    // Disable send button
    dom.sendBtn.disabled = true;
    
    try {
        let payload = {
            type: 'chat_message',
            content: contentText,
            message_type: 'text'
        };
        
        if (file) {
            // Upload file first
            showToast('Uploading attachment...', 'info');
            const fileInfo = await uploadFileToServer(file);
            
            payload.message_type = fileInfo.file_type || 'file';
            
            // Build details
            payload.content = JSON.stringify({
                text: contentText,
                file_url: fileInfo.file_url,
                file_name: fileInfo.file_name,
                file_size: fileInfo.file_size,
                mime_type: fileInfo.mime_type
            });
            
            handleCancelFile();
        }
        
        // Send via WebSocket
        state.ws.send(JSON.stringify(payload));
        
        // Reset typing
        sendTypingStatus(false);
        
        dom.messageInput.value = '';
        dom.messageInput.focus();
    } catch (err) {
        showToast(err.message, 'error');
    } finally {
        dom.sendBtn.disabled = false;
    }
}

// --- TYPING DETECTION & THROTTLES ---
function handleTypingInput() {
    if (!state.ws || state.ws.readyState !== WebSocket.OPEN) return;
    
    if (!state.isTyping) {
        state.isTyping = true;
        sendTypingStatus(true);
    }
    
    // Debounce typing status stop
    clearTimeout(state.typingTimeout);
    state.typingTimeout = setTimeout(() => {
        state.isTyping = false;
        sendTypingStatus(false);
    }, 2500);
}

function sendTypingStatus(isTyping) {
    if (state.ws && state.ws.readyState === WebSocket.OPEN) {
        state.ws.send(JSON.stringify({
            type: isTyping ? 'typing_start' : 'typing_stop'
        }));
    }
}

function updateTypingIndicator() {
    if (state.typingUsers.size === 0) {
        dom.typingIndicator.classList.remove('active');
    } else {
        const users = Array.from(state.typingUsers);
        let typingMsg = '';
        if (users.length === 1) {
            typingMsg = `${users[0]} is typing...`;
        } else if (users.length === 2) {
            typingMsg = `${users[0]} and ${users[1]} are typing...`;
        } else {
            typingMsg = 'Multiple people are typing...';
        }
        dom.typingText.textContent = typingMsg;
        dom.typingIndicator.classList.add('active');
    }
}

// --- RENDER HELPERS ---
function appendMessageToViewport(msg) {
    const isOutgoing = msg.user_id === state.user.id;
    const card = document.createElement('div');
    card.className = `message-card ${isOutgoing ? 'outgoing' : 'incoming'}`;
    
    const senderName = msg.user ? msg.user.username : `User ${msg.user_id}`;
    const timestampStr = formatTimestamp(msg.created_at);
    
    let bubbleContent = '';
    
    if (msg.message_type === 'text') {
        bubbleContent = `<div class="message-bubble">${escapeHTML(msg.content)}</div>`;
    } else {
        // Parse metadata JSON
        try {
            const meta = JSON.parse(msg.content);
            const textHTML = meta.text ? `<p style="margin-bottom: 8px; color: inherit;">${escapeHTML(meta.text)}</p>` : '';
            const downloadUrl = `${API_URL}${meta.file_url}`;
            
            let fileAttachmentHTML = '';
            
            if (msg.message_type === 'image') {
                fileAttachmentHTML = `
                    <div class="message-file-container">
                        <img src="${downloadUrl}" class="image-attachment-img" alt="${escapeHTML(meta.file_name)}" onclick="window.open('${downloadUrl}', '_blank')">
                    </div>
                `;
            } else if (msg.message_type === 'video') {
                fileAttachmentHTML = `
                    <div class="message-file-container">
                        <video controls class="media-attachment-player">
                            <source src="${downloadUrl}" type="${meta.mime_type}">
                            Your browser does not support video.
                        </video>
                    </div>
                `;
            } else if (msg.message_type === 'audio') {
                fileAttachmentHTML = `
                    <div class="message-file-container">
                        <audio controls class="media-attachment-player" style="width: 100%;">
                            <source src="${downloadUrl}" type="${meta.mime_type}">
                        </audio>
                    </div>
                `;
            } else {
                fileAttachmentHTML = `
                    <div class="message-file-container">
                        <div class="file-attachment-box">
                            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>
                            <div class="file-attachment-info">
                                <span class="file-attachment-name" title="${escapeHTML(meta.file_name)}">${escapeHTML(meta.file_name)}</span>
                                <span class="file-attachment-size">${formatBytes(meta.file_size)}</span>
                            </div>
                            <a href="${downloadUrl}" target="_blank" download class="btn-icon btn-download-file" title="Download File">
                                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
                            </a>
                        </div>
                    </div>
                `;
            }
            
            bubbleContent = `
                <div class="message-bubble">
                    ${textHTML}
                    ${fileAttachmentHTML}
                </div>
            `;
        } catch (e) {
            // Fallback to text
            bubbleContent = `<div class="message-bubble">${escapeHTML(msg.content)}</div>`;
        }
    }
    
    card.innerHTML = `
        <span class="message-sender">${escapeHTML(senderName)}</span>
        ${bubbleContent}
        <span class="message-time">${timestampStr}</span>
    `;
    
    dom.messagesViewport.appendChild(card);
}

function appendSystemMessage(msgText) {
    const div = document.createElement('div');
    div.className = 'message-system';
    div.textContent = msgText;
    dom.messagesViewport.appendChild(div);
}

function scrollToBottom() {
    dom.messagesViewport.scrollTop = dom.messagesViewport.scrollHeight;
}

// --- UTILITY CODE ---
function formatTimestamp(isoString) {
    try {
        const date = new Date(isoString);
        return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } catch (e) {
        return '';
    }
}

function formatBytes(bytes, decimals = 1) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
}

function escapeHTML(str) {
    if (!str) return '';
    return str.replace(/[&<>'"]/g, 
        tag => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[tag] || tag)
    );
}

// --- VIDEO CALL FLOWS ---
function startVideoCall() {
    if (!state.activeRoom) {
        showToast('Please join a chat channel first.', 'error');
        return;
    }
    
    if (dom.videoCallPanel) dom.videoCallPanel.classList.add('active');
    if (dom.videoCallBtn) dom.videoCallBtn.style.display = 'none';
    
    showToast('Initializing camera stream...', 'info');
    if (dom.videoStream) dom.videoStream.src = `${API_URL}/kvm-stream/?t=${Date.now()}`;
}

function stopVideoCall() {
    if (!dom.videoCallPanel) return;
    const wasActive = dom.videoCallPanel.classList.contains('active');
    
    dom.videoCallPanel.classList.remove('active');
    if (dom.videoCallBtn) dom.videoCallBtn.style.display = 'flex';
    
    if (dom.videoStream) dom.videoStream.src = '';
    
    if (wasActive) {
        showToast('Video call ended.', 'info');
    }
}

// --- WebRTC CALLING LOGIC ---

async function fetchIceServers() {
    try {
        const response = await fetch(`${API_URL}/webrtc/ice-servers`, {
            headers: { 'Authorization': `Bearer ${state.token}` }
        });
        if (response.ok) {
            const data = await response.json();
            state.iceServers = data.iceServers;
            console.log('WebRTC ICE Servers cached:', state.iceServers);
        } else {
            state.iceServers = [{ urls: "stun:stun.l.google.com:19302" }];
        }
    } catch (e) {
        console.error('Failed to fetch ICE servers:', e);
        state.iceServers = [{ urls: "stun:stun.l.google.com:19302" }];
    }
}

function openCallSelector(callType) {
    if (!state.activeRoom) {
        showToast('Please join a chat channel first.', 'error');
        return;
    }
    state.pendingCallType = callType;
    renderCallUsersList();
    dom.callSelectorModal.classList.add('active');
}

function renderCallUsersList() {
    dom.callUsersList.innerHTML = '';
    
    if (state.roomUsers.length === 0) {
        dom.callUsersList.innerHTML = `
            <div style="text-align: center; color: var(--text-secondary); padding: 20px;">
                No other online users in this room
            </div>
        `;
        return;
    }
    
    state.roomUsers.forEach(user => {
        const li = document.createElement('li');
        li.className = 'room-item';
        li.style.display = 'flex';
        li.style.alignItems = 'center';
        li.style.justifyContent = 'space-between';
        
        li.innerHTML = `
            <div class="room-item-details" style="flex-direction: row; align-items: center; gap: 12px;">
                <span class="status-indicator online"></span>
                <span class="room-title" style="font-weight: 600; color: white;">${escapeHTML(user.username)}</span>
            </div>
            <button class="btn btn-primary" style="padding: 6px 12px; font-size: 0.8rem;">Call</button>
        `;
        
        li.addEventListener('click', () => {
            dom.callSelectorModal.classList.remove('active');
            startCallFlow(user.user_id, state.pendingCallType);
        });
        
        dom.callUsersList.appendChild(li);
    });
}

function startCallFlow(targetUserId, callType) {
    if (state.currentCall) {
        showToast('You are already in an active call session.', 'error');
        return;
    }
    
    state.currentCall = {
        status: 'ringing',
        role: 'caller',
        targetUserId: targetUserId,
        callType: callType
    };
    
    // Prepare Call Overlay
    dom.callStatusText.textContent = 'Calling peer...';
    dom.callStatusOverlay.classList.remove('hidden');
    dom.webrtcCallOverlay.classList.add('active');
    
    // Show/hide elements based on callType
    if (callType === 'audio') {
        dom.localVideo.style.display = 'none';
        dom.remoteVideo.style.display = 'none';
        dom.audioCallPlaceholder.style.display = 'flex';
    } else {
        dom.localVideo.style.display = 'block';
        dom.remoteVideo.style.display = 'block';
        dom.audioCallPlaceholder.style.display = 'none';
    }
    
    // Send invitation over WS
    if (state.ws && state.ws.readyState === WebSocket.OPEN) {
        state.ws.send(jsonStr({
            type: 'call_invite',
            target_user_id: targetUserId,
            call_type: callType
        }));
    }
    
    console.log(`Initiated ${callType} call to user ${targetUserId}`);
}

function handleIncomingCallInvite(data) {
    if (state.currentCall) {
        if (state.ws && state.ws.readyState === WebSocket.OPEN) {
            state.ws.send(jsonStr({
                type: 'call_busy',
                target_user_id: data.from_user_id
            }));
        }
        return;
    }
    
    state.currentCall = {
        status: 'ringing',
        role: 'callee',
        targetUserId: data.from_user_id,
        callerName: data.from_username,
        callType: data.call_type
    };
    
    dom.callerName.textContent = data.from_username;
    dom.callTypeLabel.textContent = `is inviting you to a ${data.call_type} call...`;
    dom.incomingCallModal.classList.add('active');
}

async function acceptIncomingCall() {
    dom.incomingCallModal.classList.remove('active');
    
    if (!state.currentCall) return;
    
    state.currentCall.status = 'active';
    dom.callStatusText.textContent = 'Connecting...';
    dom.callStatusOverlay.classList.remove('hidden');
    dom.webrtcCallOverlay.classList.add('active');
    
    // Show/hide elements based on callType
    if (state.currentCall.callType === 'audio') {
        dom.localVideo.style.display = 'none';
        dom.remoteVideo.style.display = 'none';
        dom.audioCallPlaceholder.style.display = 'flex';
    } else {
        dom.localVideo.style.display = 'block';
        dom.remoteVideo.style.display = 'block';
        dom.audioCallPlaceholder.style.display = 'none';
    }
    
    // Send acceptance to signaling server
    if (state.ws && state.ws.readyState === WebSocket.OPEN) {
        state.ws.send(jsonStr({
            type: 'call_accept',
            target_user_id: state.currentCall.targetUserId
        }));
    }
    
    await initWebRTCPeer('callee', state.currentCall.targetUserId, state.currentCall.callType);
}

function rejectIncomingCall() {
    dom.incomingCallModal.classList.remove('active');
    if (!state.currentCall) return;
    
    if (state.ws && state.ws.readyState === WebSocket.OPEN) {
        state.ws.send(jsonStr({
            type: 'call_reject',
            target_user_id: state.currentCall.targetUserId
        }));
    }
    cleanupCall();
}

async function handleIncomingCallOffer(data) {
    if (!state.currentCall || state.currentCall.role !== 'callee') return;
    
    console.log('Received SDP offer from peer');
    
    try {
        await state.peerConnection.setRemoteDescription(new RTCSessionDescription(data.sdp));
        
        while (state.bufferedIceCandidates.length > 0) {
            const candidate = state.bufferedIceCandidates.shift();
            await state.peerConnection.addIceCandidate(new RTCIceCandidate(candidate));
        }
        
        const answer = await state.peerConnection.createAnswer();
        await state.peerConnection.setLocalDescription(answer);
        
        if (state.ws && state.ws.readyState === WebSocket.OPEN) {
            state.ws.send(jsonStr({
                type: 'call_answer',
                target_user_id: state.currentCall.targetUserId,
                sdp: answer
            }));
        }
    } catch (e) {
        console.error('Failed to handle incoming SDP offer:', e);
        hangupCall();
    }
}

async function handleIncomingCallAnswer(data) {
    if (!state.currentCall || state.currentCall.role !== 'caller') return;
    
    console.log('Received SDP answer from peer');
    
    try {
        await state.peerConnection.setRemoteDescription(new RTCSessionDescription(data.sdp));
        
        while (state.bufferedIceCandidates.length > 0) {
            const candidate = state.bufferedIceCandidates.shift();
            await state.peerConnection.addIceCandidate(new RTCIceCandidate(candidate));
        }
        
        state.currentCall.status = 'active';
    } catch (e) {
        console.error('Failed to set remote SDP answer:', e);
        hangupCall();
    }
}

async function handleIncomingIceCandidate(data) {
    if (!state.peerConnection) return;
    
    try {
        if (state.peerConnection.remoteDescription) {
            await state.peerConnection.addIceCandidate(new RTCIceCandidate(data.candidate));
        } else {
            state.bufferedIceCandidates.push(data.candidate);
        }
    } catch (e) {
        console.error('Error adding ICE candidate:', e);
    }
}

function handleCallRejected(data) {
    showToast('Call was rejected by peer.', 'info');
    cleanupCall();
}

function handleCallBusy(data) {
    showToast('User is busy on another call.', 'info');
    cleanupCall();
}

function handleCallEnded(data) {
    showToast('Call ended by peer.', 'info');
    cleanupCall();
}

async function initWebRTCPeer(role, targetUserId, callType) {
    console.log(`Setting up peer connection as ${role} for ${callType} call`);
    
    state.bufferedIceCandidates = [];
    
    try {
        const constraints = {
            audio: true,
            video: callType === 'video'
        };
        state.localStream = await navigator.mediaDevices.getUserMedia(constraints);
        
        if (callType === 'video') {
            dom.localVideo.srcObject = state.localStream;
        }
    } catch (e) {
        console.error('Failed to acquire mic/camera permissions:', e);
        showToast('Camera/Microphone access denied.', 'error');
        hangupCall();
        return;
    }
    
    state.peerConnection = new RTCPeerConnection({ iceServers: state.iceServers });
    
    state.localStream.getTracks().forEach(track => {
        state.peerConnection.addTrack(track, state.localStream);
    });
    
    state.peerConnection.ontrack = (event) => {
        console.log('Received remote media track');
        state.remoteStream = event.streams[0];
        if (callType === 'video') {
            dom.remoteVideo.srcObject = state.remoteStream;
        }
        dom.callStatusOverlay.classList.add('hidden');
    };
    
    state.peerConnection.onicecandidate = (event) => {
        if (event.candidate && state.ws && state.ws.readyState === WebSocket.OPEN) {
            state.ws.send(jsonStr({
                type: 'ice_candidate',
                target_user_id: targetUserId,
                candidate: event.candidate
            }));
        }
    };
    
    state.peerConnection.oniceconnectionstatechange = () => {
        console.log('ICE Connection State changed to:', state.peerConnection.iceConnectionState);
        if (state.peerConnection.iceConnectionState === 'disconnected' || 
            state.peerConnection.iceConnectionState === 'failed') {
            showToast('ICE Connection failed, closing call', 'error');
            cleanupCall();
        }
    };
    
    if (role === 'caller') {
        try {
            const offer = await state.peerConnection.createOffer();
            await state.peerConnection.setLocalDescription(offer);
            
            if (state.ws && state.ws.readyState === WebSocket.OPEN) {
                state.ws.send(jsonStr({
                    type: 'call_offer',
                    target_user_id: targetUserId,
                    sdp: offer
                }));
            }
        } catch (e) {
            console.error('Error creating local offer description:', e);
            hangupCall();
        }
    }
}

function hangupCall() {
    if (!state.currentCall) return;
    
    if (state.ws && state.ws.readyState === WebSocket.OPEN) {
        state.ws.send(jsonStr({
            type: 'call_end',
            target_user_id: state.currentCall.targetUserId
        }));
    }
    cleanupCall();
}

function cleanupCall() {
    state.currentCall = null;
    
    if (state.peerConnection) {
        state.peerConnection.close();
        state.peerConnection = null;
    }
    
    if (state.localStream) {
        state.localStream.getTracks().forEach(track => track.stop());
        state.localStream = null;
    }
    
    state.remoteStream = null;
    state.bufferedIceCandidates = [];
    
    dom.localVideo.srcObject = null;
    dom.remoteVideo.srcObject = null;
    
    dom.webrtcCallOverlay.classList.remove('active');
    dom.incomingCallModal.classList.remove('active');
    dom.callSelectorModal.classList.remove('active');
    dom.callStatusOverlay.classList.remove('hidden');
    
    dom.toggleMicBtn.classList.remove('muted');
    dom.toggleVideoBtn.classList.remove('muted');
}

function toggleMuteMic() {
    if (!state.localStream) return;
    
    const audioTrack = state.localStream.getAudioTracks()[0];
    if (audioTrack) {
        audioTrack.enabled = !audioTrack.enabled;
        dom.toggleMicBtn.classList.toggle('muted', !audioTrack.enabled);
        showToast(audioTrack.enabled ? 'Microphone unmuted' : 'Microphone muted', 'info');
    }
}

function toggleMuteVideo() {
    if (!state.localStream || !state.currentCall || state.currentCall.callType !== 'video') return;
    
    const videoTrack = state.localStream.getVideoTracks()[0];
    if (videoTrack) {
        videoTrack.enabled = !videoTrack.enabled;
        dom.toggleVideoBtn.classList.toggle('muted', !videoTrack.enabled);
        showToast(videoTrack.enabled ? 'Camera turned on' : 'Camera turned off', 'info');
    }
}

async function handleCallAccepted(data) {
    if (!state.currentCall || state.currentCall.role !== 'caller') return;
    
    console.log('Call invite accepted by peer');
    state.currentCall.status = 'active';
    dom.callStatusText.textContent = 'Connecting...';
    
    await initWebRTCPeer('caller', state.currentCall.targetUserId, state.currentCall.callType);
}

function jsonStr(obj) {
    return JSON.stringify(obj);
}


