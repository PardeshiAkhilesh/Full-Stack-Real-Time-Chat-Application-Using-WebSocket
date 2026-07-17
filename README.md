# Nexus - Real-Time Chat & Video Calling Workspace

Nexus is a full-stack real-time chat application featuring text messaging, typing indicators, file uploads (images, audio, video), and high-performance, low-latency 1:1 voice and video calling.

## Technology Stack
- **Backend**: FastAPI, SQLAlchemy (SQLite), JWT Authentication, WebSocket (`ConnectionManager`)
- **Frontend**: Vanilla HTML5 / CSS3 (glassmorphic styling) / JavaScript (native WebRTC & WebSockets)

---

## Features
- **Real-Time Workspace Chat**: Group rooms, typing indicators, join/leave logs.
- **Rich Media Attachments**: Upload and preview photos, voice clips, video files, or document attachments.
- **WhatsApp-Style Video/Audio Calls**: Low-latency browser-to-browser calling utilizing WebRTC.

---

## Running the Application Locally

1. **Start the backend server**:
   From the repository root, start the FastAPI application:
   ```bash
   venv\Scripts\python backend/main.py
   ```
2. **Access the web workspace**:
   Open your browser and navigate to:
   ```
   http://localhost:8000
   ```
   *(FastAPI automatically serves the static frontend files located in the `frontend` folder at the root path `/`)*

---

## How Video & Audio Calling Works

Nexus implements calling using the industry-standard **WebRTC (Web Real-Time Communication)** architecture:

### 1. Peer-to-Peer Media Path
- Audio and video packet streams do **not** route through the FastAPI server.
- The browsers establish a direct media path (`RTCPeerConnection`) with each other to send and receive encrypted media frames via `getUserMedia()` stream captures.

### 2. WebSocket Signaling Path
- The existing chat WebSocket connection (`/ws/chat/{room_id}`) is used to exchange WebRTC signaling handshakes:
  - **SDP Offers & Answers** (Session Description Protocol) containing audio/video codecs and settings.
  - **ICE Candidates** (Interactive Connectivity Establishment) containing local IP addresses and ports.
  - **Call Lifecycle Signals**: `call_invite`, `call_reject`, `call_end`, and `call_busy`.
- The backend `ConnectionManager` acts as a targeted signal proxy, ensuring WebRTC handshakes are routed strictly 1:1 using the new `send_to_user()` method.

---

## NAT Traversal & Production Configuration

Direct peer-to-peer WebRTC connections succeed on local networks and straightforward internet topologies. However, firewalls, symmetric NATs, or Carrier-Grade NATs (CGNAT) often block direct P2P connections.

### STUN Server (Development)
By default, the application uses Google's public STUN server (`stun:stun.l.google.com:19302`) to discover external IP addresses.

### TURN Server (Production Relay)
To guarantee 100% call reliability in production across symmetric firewalls, you must run or rent a **TURN relay server** (e.g., self-hosted `coturn`, or cloud services like Twilio or Metered).
- The REST endpoint `GET /webrtc/ice-servers` (defined in `backend/main.py`) serves the list of ICE servers.
- To use a TURN server, simply add its configuration parameters inside `get_ice_servers()`:
  ```python
  @app.get("/webrtc/ice-servers")
  async def get_ice_servers(current_user: models.User = Depends(get_current_user)):
      return {
          "iceServers": [
              { "urls": ["stun:stun.l.google.com:19302"] },
              {
                  "urls": ["turn:your-turn-server-domain.com:3478"],
                  "username": "authorized_username",
                  "credential": "secure_password"
              }
          ]
      }
  ```

---

## HTTPS/WSS Production Requirement

For security reasons, web browsers restrict camera/microphone access (`navigator.mediaDevices.getUserMedia`) strictly to **Secure Origins**:
- `localhost` (for local development)
- Domains served over **HTTPS** (production)

When deploying to production, ensure that the application is served over HTTPS and the WebSocket connection uses **WSS** (`wss://`). Serving the app over plain HTTP in production will cause calling to fail with a `DOMException: Permission Denied` error.