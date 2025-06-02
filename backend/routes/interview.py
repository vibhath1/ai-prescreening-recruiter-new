# Updated interview.py with real-time WebSocket audio fix and AI integration
import wsgiref.headers
import sys
if hasattr(wsgiref.headers, 'Headers'):
    pass
import base64
import tempfile
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Depends, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
import os
import uuid
import collections
import io
import json
import subprocess
from typing import Optional

import webrtcvad
from pydub import AudioSegment

from backend.utils.speech import transcribe_audio_bytes, text_to_audio_bytes
from backend.database import get_db
from backend.models import InterviewSession, Resume, InterviewQuestion, UserResponse, User
from backend.routes.auth import get_current_user, oauth2_scheme
from backend.core.config import settings
from backend.utils.ai import get_ai_interview_response

router = APIRouter(prefix="/api")

SECRET_KEY = settings.SECRET_KEY
ALGORITHM = settings.ALGORITHM

AUDIO_SAMPLE_RATE = 16000
AUDIO_CHANNELS = 1
AUDIO_WIDTH = 2
VAD_AGGRESSIVENESS = 3
VAD_FRAME_MS = 30
VAD_FRAME_BYTES = (AUDIO_SAMPLE_RATE * VAD_FRAME_MS // 1000) * AUDIO_WIDTH * AUDIO_CHANNELS
MAX_INTERVIEW_MINUTES = 30
MAX_QUESTION_EXCHANGES = 10
RECORDINGS_DIR = "recordings/user_audio"
os.makedirs(RECORDINGS_DIR, exist_ok=True)
os.makedirs("./backend/media/audio", exist_ok=True)

active_sessions: dict[int, dict] = {}

def convert_webm_to_pcm(data: bytes) -> bytes:
    # Create temporary files for input and output
    with tempfile.NamedTemporaryFile(suffix='.webm', delete=False) as input_file:
        input_file.write(data)
        input_path = input_file.name
    
    output_path = input_path + '.pcm'
    
    try:
        # Run FFmpeg with more detailed parameters and error handling
        process = subprocess.Popen(
            [
                "ffmpeg", 
                "-y",  # Overwrite output files
                "-loglevel", "warning",
                "-i", input_path,
                "-vn",  # No video
                "-acodec", "pcm_s16le",  # PCM signed 16-bit little-endian
                "-ar", "16000",  # Sample rate
                "-ac", "1",  # Mono
                "-f", "s16le",  # Format
                output_path
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        stdout, stderr = process.communicate()
        
        if process.returncode != 0:
            raise RuntimeError(f"FFmpeg decode failed: {stderr.decode()}")
        
        # Read the output file
        with open(output_path, 'rb') as f:
            pcm_data = f.read()
        
        return pcm_data
    
    except Exception as e:
        raise RuntimeError(f"Audio conversion failed: {str(e)}")
    
    finally:
        # Clean up temporary files
        try:
            os.unlink(input_path)
            if os.path.exists(output_path):
                os.unlink(output_path)
        except:
            pass



@router.post("/start-interview/")
async def start_interview(resume_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    resume = db.query(Resume).filter(Resume.id == resume_id, Resume.user_id == current_user.id).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")

    parsed_resume_data = resume.parsed_data_json

    # Create session entry
    session = InterviewSession(user_id=current_user.id, resume_id=resume.id, start_time=datetime.utcnow())
    db.add(session)
    db.commit()
    db.refresh(session)

    # Generate first question
    conversation = []
    first_question = await asyncio.to_thread(get_ai_interview_response, parsed_resume_data, conversation)

    db_question = InterviewQuestion(session_id=session.id, question_text=first_question, timestamp=datetime.utcnow())
    db.add(db_question)
    db.commit()
    db.refresh(db_question)

    # Save session state in memory
    active_sessions[session.id] = {
        "conversation_history": [{"role": "assistant", "content": first_question}],
        "audio_buffer_raw": collections.deque(),
        "vad": webrtcvad.Vad(VAD_AGGRESSIVENESS),
        "last_speech_frame_time": datetime.utcnow(),
        "current_question_db_id": db_question.id,
        "start_time": session.start_time,
        "question_count": 1
    }

    # Generate audio and encode as base64
    try:
        audio_bytes = await asyncio.to_thread(text_to_audio_bytes, first_question)
        audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')
    except Exception as e:
        audio_base64 = None
        print(f"Error generating audio: {e}")

    return {
        "session_id": session.id,
        "first_question": first_question,
        "audio_base64": audio_base64
    }
@router.post("/end-interview/{session_id}")
async def end_interview(session_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    session = db.query(InterviewSession).filter(InterviewSession.id == session_id, InterviewSession.user_id == current_user.id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if not session.end_time:
        session.end_time = datetime.utcnow()
        db.commit()

    # Cleanup session from memory
    active_sessions.pop(session_id, None)

    return {"message": "Interview ended"}


...
...
...
@router.websocket("/ws/interview/{session_id}")
async def interview_websocket(websocket: WebSocket, session_id: int, db: Session = Depends(get_db)):
    await websocket.accept()
    current_user = await get_current_user_ws(websocket, db)
    if not current_user:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    state = active_sessions.get(session_id)
    if not state:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    db_session = db.query(InterviewSession).filter(InterviewSession.id == session_id).first()
    if not db_session or db_session.user_id != current_user.id:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    resume = db.query(Resume).filter(Resume.id == db_session.resume_id).first()
    parsed_resume_data = resume.parsed_data_json

    import wave

    audio_buffer_raw = state["audio_buffer_raw"]
    conversation_history = state["conversation_history"]
    current_question_db_id = state["current_question_db_id"]
    vad = state["vad"]
    start_time = state["start_time"]
    question_count = state["question_count"]

    session_end_time = start_time + timedelta(minutes=MAX_INTERVIEW_MINUTES)
    max_silence_sec = 60
    silence_start = None
    processing = False
    awaiting_response = False
    speech_detected = False
    last_speech_frame_time = datetime.utcnow()

    async def end_session(reason: str):
        if not db_session.end_time:
            db_session.end_time = datetime.utcnow()
            db.commit()
        thank_you_text = "Thank you for participating in the interview. Have a great day!"
        thank_you_audio = await asyncio.to_thread(text_to_audio_bytes, thank_you_text)
        await websocket.send_bytes(thank_you_audio)
        await websocket.send_json({"action": "end", "reason": reason})
        active_sessions.pop(session_id, None)

    async def ask_question(text):
        ai_audio = await asyncio.to_thread(text_to_audio_bytes, text)
        if ai_audio:
            await websocket.send_bytes(ai_audio)
            await websocket.send_json({"question": text, "type": "question"})

    async def acknowledge_response():
        text = "Thank you for your response."
        ai_audio = await asyncio.to_thread(text_to_audio_bytes, text)
        if ai_audio:
            await websocket.send_bytes(ai_audio)

    async def handle_no_response():
        reminder = "I didn't hear anything. Please respond if you're ready."
        ai_audio = await asyncio.to_thread(text_to_audio_bytes, reminder)
        if ai_audio:
            await websocket.send_bytes(ai_audio)
            await websocket.send_json({"question": reminder, "type": "reminder"})

    try:
        # Initial greeting and first question
        greeting = "Hello, and thank you for joining the interview. Let's begin."
        await ask_question(greeting)

        initial_q = await asyncio.to_thread(
            get_ai_interview_response, parsed_resume_data, conversation_history, ""
        )
        conversation_history.append({"role": "assistant", "content": initial_q})
        db_q = InterviewQuestion(session_id=db_session.id, question_text=initial_q, timestamp=datetime.utcnow())
        db.add(db_q)
        db.commit()
        db.refresh(db_q)
        current_question_db_id = db_q.id
        question_count += 1
        state["question_count"] = question_count
        await ask_question(initial_q)
        awaiting_response = True

        while True:
            if datetime.utcnow() > session_end_time or question_count >= MAX_QUESTION_EXCHANGES:
                await end_session("Interview complete")
                break

            message = await websocket.receive()

            if "text" in message:
                try:
                    cmd = json.loads(message["text"])
                    if cmd.get("action") == "end":
                        await end_session("User ended interview")
                        break
                except json.JSONDecodeError:
                    pass
                continue

            if "bytes" not in message:
                continue

            message_bytes = message["bytes"]
            audio_buffer_raw.append(message_bytes)

            if len(b"".join(audio_buffer_raw)) < VAD_FRAME_BYTES:
                continue

            buf = b"".join(audio_buffer_raw)
            frame, remainder = buf[:VAD_FRAME_BYTES], buf[VAD_FRAME_BYTES:]
            audio_buffer_raw.clear()
            audio_buffer_raw.append(remainder)

            if vad.is_speech(frame, AUDIO_SAMPLE_RATE):
                speech_detected = True
                last_speech_frame_time = datetime.utcnow()
                silence_start = None

            # If 60 seconds of silence after a question
            if awaiting_response and not speech_detected:
                if silence_start is None:
                    silence_start = datetime.utcnow()
                elif (datetime.utcnow() - silence_start).total_seconds() >= max_silence_sec:
                    await handle_no_response()
                    silence_start = None
                    continue

            # If speech ends and silence timeout is reached
            if speech_detected and (datetime.utcnow() - last_speech_frame_time).total_seconds() * 1000 > 1000:
                full_audio = b"".join(audio_buffer_raw)
                audio_buffer_raw.clear()
                speech_detected = False
                awaiting_response = False
                processing = True

                # Save to .wav file
                file_name = f"user_response_{uuid.uuid4()}.wav"
                audio_path = os.path.join(RECORDINGS_DIR, file_name)
                with wave.open(audio_path, 'wb') as wf:
                    wf.setnchannels(AUDIO_CHANNELS)
                    wf.setsampwidth(AUDIO_WIDTH)
                    wf.setframerate(AUDIO_SAMPLE_RATE)
                    wf.writeframes(full_audio)

                with open(audio_path, "rb") as f:
                    wav_bytes = f.read()

                user_text = await asyncio.to_thread(transcribe_audio_bytes, wav_bytes)
                print(f"User said: {user_text}")
                await websocket.send_json({"transcript": user_text, "type": "transcript"})

                if not user_text.strip() or user_text.startswith("Error"):
                    await handle_no_response()
                    processing = False
                    continue

                db.add(UserResponse(
                    question_id=current_question_db_id,
                    response_text=user_text,
                    timestamp=datetime.utcnow(),
                    response_audio_path=audio_path,
                ))
                db.commit()

                conversation_history.append({"role": "user", "content": user_text})
                await acknowledge_response()

                ai_text = await asyncio.to_thread(
                    get_ai_interview_response, parsed_resume_data, conversation_history, user_text
                )
                print(f"AI: {ai_text}")

                db_q = InterviewQuestion(
                    session_id=db_session.id,
                    question_text=ai_text,
                    timestamp=datetime.utcnow(),
                )
                db.add(db_q)
                db.commit()
                db.refresh(db_q)

                current_question_db_id = db_q.id
                question_count += 1
                state["question_count"] = question_count

                conversation_history.append({"role": "assistant", "content": ai_text})
                await ask_question(ai_text)

                awaiting_response = True
                processing = False

            await asyncio.sleep(0.01)

    except WebSocketDisconnect:
        db_session.end_time = datetime.utcnow()
        db.commit()
        active_sessions.pop(session_id, None)

    except Exception as e:
        print(f"WebSocket error: {e}")
        await websocket.send_text(f"ERROR: {e}")
        if not db_session.end_time:
            db_session.end_time = datetime.utcnow()
            db.commit()
        active_sessions.pop(session_id, None)

async def get_current_user_ws(websocket: WebSocket, db: Session) -> Optional[User]:
    try:
        token = websocket.query_params.get("token")
        if not token:
            return None

        from backend.utils.security import decode_access_token
        payload = decode_access_token(token)
        user_id = int(payload.get("sub"))
        user = db.query(User).filter(User.id == user_id).first()
        return user
    except Exception as e:
        print(f"WebSocket auth error: {e}")
        return None
