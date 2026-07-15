import os
import sys

# Add the directory containing main.py to sys.path to allow sibling imports (models, schemas, etc.)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, Depends, HTTPException, status, WebSocket, WebSocketDisconnect, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List, Optional
import models
import schemas
from models import SessionLocal, engine, Message
from auth import get_current_user, create_access_token, create_refresh_token, get_password_hash, verify_password, authenticate_websocket
from datetime import timedelta
import json

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
        await manager.connect(websocket, room_id, user.id)
        
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
                
    except WebSocketDisconnect:
        manager.disconnect(websocket, room_id, user.id)
        await manager.broadcast_to_room(room_id, {
            "type": "user_left",
            "user_id": user.id,
            "message": f"User {user.id} left the room"
        })

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