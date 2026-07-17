import os
import sys

# Add the directory containing main.py to sys.path to allow sibling imports (models, schemas, etc.)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, Depends, HTTPException, status, WebSocket, WebSocketDisconnect, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse, Response
from sqlalchemy.orm import Session
from typing import List, Optional, Generator, Union, Pattern
import models
import schemas
from models import SessionLocal, engine, Message
from auth import get_current_user, create_access_token, create_refresh_token, get_password_hash, verify_password, authenticate_websocket
from datetime import timedelta
import json
import time
import logging
import asyncio
import subprocess
import re

try:
    import cv2
except ImportError:
    cv2 = None

from websocket_manager import manager
from upload_file import handle_file_upload

models.Base.metadata.create_all(bind=engine)
app = FastAPI(
    title="Chat API",
    description="A real-time chat application built with FastAPI",
    version="1.0.0"
)
# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # React app
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Authentication endpoints
@app.post("/auth/register", response_model=schemas.UserResponse)
async def register(user_data: schemas.UserCreate, db: Session = Depends(get_db)):
    # Check if user exists
    db_user = db.query(models.User).filter(
        (models.User.email == user_data.email) | 
        (models.User.username == user_data.username)
    ).first()
    
    if db_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username or email already registered"
        )
    
    # Create new user
    hashed_password = get_password_hash(user_data.password)
    db_user = models.User(
        username=user_data.username,
        email=user_data.email,
        hashed_password=hashed_password
    )
    
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    return db_user

@app.post("/auth/login")
async def login(login_data: schemas.UserLogin, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.username == login_data.username).first()
    
    if not user or not verify_password(login_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password"
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    
    access_token = create_access_token(data={"sub": user.username})
    refresh_token = create_refresh_token(data={"sub": user.username})
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email
        }
    }
# Chat room endpoints
@app.post("/rooms/", response_model=schemas.ChatRoomResponse)
async def create_room(
    room_data: schemas.ChatRoomCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    db_room = models.ChatRoom(
        name=room_data.name,
        description=room_data.description,
        created_by_id=current_user.id,
        max_participants=room_data.max_participants
    )
    
    db.add(db_room)
    db.commit()
    db.refresh(db_room)
    
    return db_room
@app.get("/rooms/", response_model=List[schemas.ChatRoomResponse])
async def get_rooms(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    rooms = db.query(models.ChatRoom).filter(models.ChatRoom.is_active == True)\
        .offset(skip).limit(limit).all()
    return rooms
# Message endpoints
@app.get("/rooms/{room_id}/messages", response_model=List[schemas.MessageResponse])
async def get_room_messages(
    room_id: int,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    messages = db.query(models.Message).filter(models.Message.room_id == room_id)\
        .order_by(models.Message.created_at.desc())\
        .offset(skip).limit(limit).all()
    
    return messages[::-1]  # Return in chronological order

# File upload endpoint
@app.post("/upload-file/")
async def upload_file(
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        file_info = await handle_file_upload(file, current_user.id)
        
        # We can also save the file info to database or create a message if needed
        return {
            "success": True,
            "file_info": file_info,
            "message": "File uploaded successfully"
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error uploading file: {str(e)}"
        )

# WebSocket endpoint
@app.websocket("/ws/chat/{room_id}")
async def websocket_endpoint(
    websocket: WebSocket, 
    room_id: int, 
    token: str,
    db: Session = Depends(get_db)
):
    # Authenticate user from token
    try:
        user = await authenticate_websocket(token, db)
    except HTTPException:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    
    try:
        await manager.connect(websocket, room_id, user.id, user.username)
        
        while True:
            data = await websocket.receive_text()
            message_data = json.loads(data)
            
            # Handle different message types
            if message_data["type"] == "chat_message":
                # Save message to database
                db_message = Message(
                    room_id=room_id,
                    user_id=user.id,
                    content=message_data["content"],
                    message_type=message_data.get("message_type", "text")
                )
                db.add(db_message)
                db.commit()
                db.refresh(db_message)
                
                # Broadcast to room
                await manager.broadcast_to_room(room_id, {
                    "type": "new_message",
                    "message_id": db_message.uuid,
                    "user_id": user.id,
                    "username": user.username,
                    "content": message_data["content"],
                    "timestamp": db_message.created_at.isoformat(),
                    "message_type": message_data.get("message_type", "text")
                })
            
            elif message_data["type"] == "typing_start":
                await manager.broadcast_to_room(room_id, {
                    "type": "user_typing",
                    "user_id": user.id,
                    "username": user.username,
                    "typing": True
                })
            
            elif message_data["type"] == "typing_stop":
                await manager.broadcast_to_room(room_id, {
                    "type": "user_typing",
                    "user_id": user.id,
                    "username": user.username,
                    "typing": False
                })
            
            elif message_data["type"] in ["call_invite", "call_accept", "call_offer", "call_answer", "ice_candidate", "call_reject", "call_end", "call_busy"]:
                target_user_id = message_data.get("target_user_id")
                if target_user_id is not None:
                    try:
                        target_user_id = int(target_user_id)
                    except ValueError:
                        pass
                    # Construct signaling payload with verified sender info
                    payload = {
                        **message_data,
                        "from_user_id": user.id,
                        "from_username": user.username
                    }
                    await manager.send_to_user(target_user_id, payload)
                
    except WebSocketDisconnect:
        manager.disconnect(websocket, room_id, user.id)
        await manager.broadcast_to_room(room_id, {
            "type": "user_left",
            "user_id": user.id,
            "username": user.username,
            "message": f"User {user.username} left the room"
        })

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
logger = logging.getLogger("chat_api")

def get_fallback_image() -> bytes:
    """Returns a fallback image when the camera is not connected or cv2 is missing."""
    assets_dir = os.path.join(BASE_DIR, "assets")
    fallback_path = os.path.join(assets_dir, "kvm_not_connected.jpg")
    
    if os.path.exists(fallback_path):
        try:
            with open(fallback_path, "rb") as file_object:
                return file_object.read()
        except Exception as e:
            logger.error(f"Failed to read fallback image from file: {e}")
            
    # Generate in-memory fallback image if cv2 is available
    if cv2 is not None:
        try:
            import numpy as np
            # Create a 640x480 black image
            img = np.zeros((480, 640, 3), dtype=np.uint8)
            # Add text warning
            cv2.putText(
                img, 
                "Camera Not Connected", 
                (120, 240), 
                cv2.FONT_HERSHEY_SIMPLEX, 
                1.0, 
                (255, 255, 255), 
                2, 
                cv2.LINE_AA
            )
            _, encoded_image = cv2.imencode(".jpg", img)
            return encoded_image.tobytes()
        except Exception as e:
            logger.error(f"Failed to generate fallback image dynamically: {e}")
            
    # Hardcoded 1x1 black JPEG image as absolute backup
    return b'\xff\xd8\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c\x1c $.\' ",#\x1c\x1c(7),01444\x1f\'9=82<.342\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xbf\x00\xff\xd9'

def read_kvm_video_frames(video_interface) -> Generator[bytes, None, None]:
    """Reads frames from the video interface and yields them as JPEG bytes."""
    frame_count = 0
    start_time = time.time()
    fallback_img = get_fallback_image()
    
    try:
        while True:
            if video_interface is None or not video_interface.isOpened():
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + fallback_img + b'\r\n')
                yield b'--frame--\r\n'
                logger.info("The video interface is not open, closing the stream.")
                break

            read_status, frame = video_interface.read()
            if not read_status:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + fallback_img + b'\r\n')
                yield b'--frame--\r\n'
                logger.info("Failed to read frame, closing stream.")
                break
            else:
                _, encoded_image = cv2.imencode(".jpeg", frame)
                image_bytes = encoded_image.tobytes()
                yield b"--frame\r\n" b"Content-Type: image/jpeg\r\n\r\n" + image_bytes + b"\r\n"

            frame_count += 1
            if time.time() - start_time > 1:
                fps = frame_count / (time.time() - start_time)
                logger.info(f"Video Call FPS: {int(fps)}.")
                frame_count = 0
                start_time = time.time()
    except GeneratorExit:
        logger.error("Exiting the generator for video stream.")
    except Exception as e:
        logger.error(f"Exiting generator due to exception: {e}")
    finally:
        logger.info("Closing connection and releasing video interface.")
        if video_interface is not None:
            video_interface.release()

@app.get("/kvm-stream/", response_model=None)
async def open_kvm_stream() -> Union[StreamingResponse, Response]:
    """Streaming endpoint to capture frames from the connected camera."""
    if cv2 is None:
        logger.error("cv2 is not installed. Returning fallback image.")
        return Response(content=get_fallback_image(), media_type="image/jpeg")

    video_index = 0
    import sys
    backend_api = cv2.CAP_ANY
    if sys.platform == 'win32':
        backend_api = cv2.CAP_MSMF
        
    video_interface = cv2.VideoCapture(video_index, backend_api)
    video_interface.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    video_interface.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    video_interface.set(cv2.CAP_PROP_FPS, 30)

    try:
        read_status, frame = video_interface.read()
        if not read_status:
            video_interface.release()
            return Response(content=get_fallback_image(), media_type="image/jpeg")
    except Exception as e:
        logger.error(f"Error checking camera status: {e}")
        if video_interface is not None:
            video_interface.release()
        return Response(content=get_fallback_image(), media_type="image/jpeg")

    try:
        return StreamingResponse(
            read_kvm_video_frames(video_interface),
            media_type="multipart/x-mixed-replace;boundary=frame"
        )
    except Exception as e:
        logger.error(f"Failed to start stream: {e}")
        if video_interface is not None:
            video_interface.release()
        return Response(content=get_fallback_image(), media_type="image/jpeg")

@app.websocket("/websocket/kvm-stream")
async def stream_kvm(websocket: WebSocket) -> Optional[bytes]:
    """KVM streamer with h264 encoding.

    This function will create an FFMPEG pipeline to read kvm frame from the usb, encode it
    to h264 annexure b format, and read the output bytes using subprocess pipe
    and parse them to create individual nal data and sends them to the client.

    Args:
        websocket (WebSocket): The WebSocket object to establish the connection.

    Returns:
        Optional[bytes]: The encoded video data.
    """
    await websocket.accept()

    kvm_device_name = "video_capture_device"

    if not kvm_device_name:
        logger.error("KVM not found, closing the connection.")
        await websocket.close()
        return

    ffmpeg_executable_location = os.path.join("D:", "my_software",
                                              "ffmpeg", "ffmpeg-static-win64-gpl",
                                              "bin", "ffmpeg.exe")

    if not os.path.exists(ffmpeg_executable_location):
        logger.info(f"FFMPEG static binary not found at {ffmpeg_executable_location}. Falling back to system 'ffmpeg'.")
        ffmpeg_executable_location = "ffmpeg"

    ffmpeg_command = [
        ffmpeg_executable_location,
        '-f', 'dshow',
        '-i', 'video=' + kvm_device_name,
        '-s', '1920x1080',
        '-c:v', 'libx264',
        '-preset', 'ultrafast',
        '-tune', 'zerolatency',
        '-profile:v', 'high',
        '-level', '4',
        '-pix_fmt', 'yuv420p',
        '-f', 'h264',
        '-'
    ]

    # Start the FFMPEG process.
    try:
        encoder_process_interface = await asyncio.create_subprocess_exec(
            *ffmpeg_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=0)
    except FileNotFoundError:
        logger.error(f"The FFMPEG executable is not found at: {ffmpeg_executable_location}")
        logger.error("Exiting the KVM stream process.")
        await websocket.close()
        return
    except Exception as error:
        logger.error(f"An unexpected error occurred: {error}")
        logger.error("Exiting the KVM stream process.")
        await websocket.close()
        return

    logger.info(f"FFMPEG Process to Encode KVM stream has been started with process id: {encoder_process_interface.pid}")

    complete_frame_data: bytes = b""

    # Define the regex pattern.
    nal_start_code_pattern: Pattern[bytes] = re.compile(b'(?:\x00\x00\x00\x01)')

    while True:
        try:
            # Read 300 KB (307200 bytes) of data, this will read at most 300KB, if less data
            # is available it will return only those available data, and will not wait
            # for complete 300KB. This number is based on trial and error
            # the maximum IDR frame size was around 280KB.
            new_encoded_data: bytes = await encoder_process_interface.stdout.read(307200)
        except Exception as error:
            logger.error("Error while reading from FFMPEG process pipeline.")
            logger.error(error)
            logger.error("Exiting from the KVM Stream.")
            break

        if not new_encoded_data:
            logger.error("There is no data from FFMPEG process, exiting the stream.")
            break

        # Find all non-overlapping matches.
        nal_matches_info: list = list(nal_start_code_pattern.finditer(new_encoded_data))

        no_of_nal_units: int = len(nal_matches_info)

        # If there were no matches, it means the current chunk of data has intermediary
        # Bytes which continues from previous data, hence they should simply be added to the
        # Existing nal data and skip the remaining code.
        if not nal_matches_info:
            complete_frame_data += new_encoded_data
            continue

        for match_index, match in enumerate(nal_matches_info):
            nal_type: int = new_encoded_data[match.end()] & 0x1F

            # If the first match in the list of matches occurs somewhere not in the first index
            # Then first few bytes (before the start index of the first match) would correspond
            # To the data from the previous nal unit, hence we need to add them to the
            # Existing nal data and then send to the client and then clear the buffer.
            if match_index == 0 and match.start() != 0:
                complete_frame_data += new_encoded_data[: match.start()]

            if complete_frame_data:
                # We send only if the current nal is Non-Idr, since other data such as SPS, PPS,
                # SEI, IDR would actually come as separate chunks, we need to combine them before
                # sending. The implementation takes care of combining them, but happens only if a
                # Non-Idr frame comes After the Key Frame (which is a combination of SPS, PPS,
                # SEI, IDR).
                if nal_type == 1:
                    try:
                        await websocket.send_bytes(complete_frame_data)
                    except WebSocketDisconnect:
                        logger.error("The Client has disconnected, exiting from the KVM stream.")
                        logger.info("Closing the websocket connection.")
                        await websocket.close()
                        logger.info("closed.")
                        logger.info("Terminating the FFMPEG process pipeline.")
                        try:
                            encoder_process_interface.terminate()
                            logger.info("Terminated.")
                        except Exception:
                            logger.warning("Couldn't terminate the process.")
                        return
                    except Exception as error:
                        logger.error("Error while sending data to the client.")
                        logger.error(error)
                        logger.error("Exiting from the KVM Stream.")
                        logger.info("Closing the websocket connection.")
                        await websocket.close()
                        logger.info("closed.")
                        logger.info("Terminating the FFMPEG process pipeline.")
                        try:
                            encoder_process_interface.terminate()
                            logger.info("Terminated.")
                        except Exception:
                            logger.warning("Couldn't terminate the process.")
                        return

                    # Yield control back to the event loop to prevent buffer overflow and ensure
                    # consistent frame rate.
                    await asyncio.sleep(0)
                    complete_frame_data = b''

            # If this is the last item in the list of matches, then we add all the data
            # From the start of its index till the end.
            if match_index == no_of_nal_units - 1:
                complete_frame_data += new_encoded_data[match.start():]
            else:
                # If this is not the last item in the list of matches, then we add all the data
                # From the start of the index, till (but not including) the start of the next
                # Match.
                next_nal_index = match_index + 1
                next_nal_start = nal_matches_info[next_nal_index].start()
                complete_frame_data += new_encoded_data[match.start():next_nal_start]

    logger.info("Closing the websocket connection.")
    await websocket.close()
    logger.info("closed.")
    logger.info("Terminating the FFMPEG process pipeline.")
    try:
        encoder_process_interface.terminate()
        logger.info("Terminated.")
    except Exception:
        logger.warning("Couldn't terminate the process.")

@app.get("/webrtc/ice-servers")
async def get_ice_servers(current_user: models.User = Depends(get_current_user)):
    return {
        "iceServers": [
            {
                "urls": ["stun:stun.l.google.com:19302"]
            }
        ]
    }

# Serve static files for frontend and uploads
from fastapi.staticfiles import StaticFiles
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
FRONTEND_DIR = os.path.join(BASE_DIR, "..", "frontend")

if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")