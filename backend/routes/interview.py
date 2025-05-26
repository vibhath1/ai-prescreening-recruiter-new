from fastapi import (
    APIRouter,
    WebSocket,
    WebSocketDisconnect,
    HTTPException,
    Depends,
    status,
)
from sqlalchemy.orm import Session
import asyncio
from datetime import datetime, timedelta
import os
import uuid
import collections
import io
import json
import webrtcvad
from pydub import AudioSegment
import time

# Import only necessary modules at top-level
from backend.utils.speech import transcribe_audio_bytes, text_to_audio_bytes
from backend.database import get_db
from backend.models import (
    InterviewSession,
    Resume,
    InterviewQuestion,
    UserResponse,
    User,
)
from backend.routes.auth import get_current_user
from fastapi.responses import StreamingResponse

router = APIRouter()

AUDIO_SAMPLE_RATE = 16000
AUDIO_CHANNELS = 1
AUDIO_WIDTH = 2
VAD_AGGRESSIVENESS = 3
VAD_FRAME_MS = 30
VAD_FRAME_BYTES = (
    AUDIO_SAMPLE_RATE * VAD_FRAME_MS // 1000
) * AUDIO_WIDTH * AUDIO_CHANNELS

MAX_INTERVIEW_MINUTES = 30
MAX_QUESTION_EXCHANGES = 10

RECORDINGS_DIR = "recordings/user_audio"
os.makedirs(RECORDINGS_DIR, exist_ok=True)

active_sessions: dict[int, dict] = {}

os.makedirs("./backend/media/audio", exist_ok=True)

@router.post("/start-interview/", status_code=status.HTTP_201_CREATED)
async def start_interview_session(
    resume_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from backend.utils.ai import get_ai_interview_response  # Local import to avoid circular dependency

    resume = db.query(Resume).filter(Resume.id == resume_id).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found.")

    if resume.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Permission denied.")

    new_session = InterviewSession(
        user_id=current_user.id,
        resume_id=resume.id,
        start_time=datetime.utcnow(),
    )
    db.add(new_session)
    db.commit()
    db.refresh(new_session)

    parsed_resume_data = resume.parsed_data_json

    first_question_text = get_ai_interview_response(
        parsed_resume_data=parsed_resume_data,
        conversation_history=[],
        current_user_response="",
    )

    first_question_audio_bytes = await asyncio.to_thread(
        text_to_audio_bytes, first_question_text
    )

    if not first_question_audio_bytes:
        raise HTTPException(
            status_code=500,
            detail="Failed to synthesize first question audio.",
        )

    db_question = InterviewQuestion(
        session_id=new_session.id,
        question_text=first_question_text,
        timestamp=datetime.utcnow(),
    )
    db.add(db_question)
    db.commit()
    db.refresh(db_question)

    timestamp = int(time.time())
    filename = f"interview_{resume_id}_{timestamp}.mp3"
    audio_file_path = f"./backend/media/audio/{filename}"
    
    audio_bytes = text_to_audio_bytes(first_question_text, save_path=audio_file_path)
    
    active_sessions[new_session.id] = {
        "audio_buffer_raw": collections.deque(),
        "conversation_history": [
            {"role": "assistant", "content": first_question_text}
        ],
        "current_question_db_id": db_question.id,
        "vad": webrtcvad.Vad(VAD_AGGRESSIVENESS),
        "last_speech_frame_time": datetime.utcnow(),
        "start_time": datetime.utcnow(),
        "question_count": 1,
    }

    return StreamingResponse(
        io.BytesIO(audio_bytes),
        media_type="audio/mpeg",
        headers={"X-Audio-Filename": filename}
    )

@router.post("/end-interview/{session_id}")
async def end_interview(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    db_session = db.query(InterviewSession).filter(InterviewSession.id == session_id).first()
    if not db_session:
        raise HTTPException(status_code=404, detail="Interview session not found")
    
    if db_session.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Permission denied")
    
    if not db_session.end_time:
        db_session.end_time = datetime.utcnow()
        db.commit()
    
    active_sessions.pop(session_id, None)
    
    return {"message": "Interview ended successfully"}

@router.websocket("/ws/interview/{session_id}")
async def interview_websocket(
    websocket: WebSocket,
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from backend.utils.ai import get_ai_interview_response  # Local import to avoid circular dependency

    await websocket.accept()
    print(f"WebSocket connected for session {session_id}")

    state = active_sessions.get(session_id)
    if not state:
        print(f"No state cached for session {session_id}")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    db_session = db.query(InterviewSession).filter(InterviewSession.id == session_id).first()
    if not db_session or db_session.user_id != current_user.id:
        print("User mismatch – closing WS")
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    resume = db.query(Resume).filter(Resume.id == db_session.resume_id).first()
    parsed_resume_data = resume.parsed_data_json

    audio_buffer_raw = state["audio_buffer_raw"]
    conversation_history = state["conversation_history"]
    current_question_db_id = state["current_question_db_id"]
    vad = state["vad"]
    last_speech_frame_time = state["last_speech_frame_time"]
    start_time = state["start_time"]
    question_count = state["question_count"]
    
    session_end_time = start_time + timedelta(minutes=MAX_INTERVIEW_MINUTES)

    speech_detected = False
    processing = False
    silence_timeout_ms = 1000

    async def query_ai(latest_user_text: str) -> str:
        return await asyncio.to_thread(
            get_ai_interview_response,
            parsed_resume_data,
            conversation_history,
            latest_user_text,
        )
    
    async def end_session(reason: str):
        if not db_session.end_time:
            db_session.end_time = datetime.utcnow()
            db.add(db_session)
            db.commit()
        
        end_message = f"Interview ended: {reason}"
        end_audio = await asyncio.to_thread(text_to_audio_bytes, end_message)
        
        if end_audio:
            await websocket.send_bytes(end_audio)
        
        await websocket.send_json({"action": "end", "reason": reason})
        active_sessions.pop(session_id, None)

    try:
        while True:
            # Check if max interview time reached
            if datetime.utcnow() > session_end_time:
                await end_session("Maximum interview time reached")
                break
            
            # Check if max questions reached
            if question_count >= MAX_QUESTION_EXCHANGES:
                await end_session("Maximum number of questions reached")
                break
            
            # Use select to handle both binary messages and text messages
            message = await websocket.receive()
            
            # Handle client commands (text messages)
            if "text" in message:
                try:
                    cmd = json.loads(message["text"])
                    if cmd.get("action") == "end":
                        await end_session("User requested to end interview")
                        break
                except json.JSONDecodeError:
                    pass
                continue
            
            # Handle audio data (binary messages)
            if "bytes" not in message:
                continue
                
            message_bytes = message["bytes"]

            if processing:
                audio_buffer_raw.append(message_bytes)
                continue

            try:
                segment = AudioSegment.from_file(io.BytesIO(message_bytes))
                pcm = (
                    segment.set_frame_rate(AUDIO_SAMPLE_RATE)
                    .set_channels(AUDIO_CHANNELS)
                    .set_sample_width(AUDIO_WIDTH)
                    .raw_data
                )
            except Exception as e:
                print("Audio decode error:", e)
                continue

            audio_buffer_raw.append(pcm)

            if len(b"".join(audio_buffer_raw)) < VAD_FRAME_BYTES:
                continue

            while len(b"".join(audio_buffer_raw)) >= VAD_FRAME_BYTES:
                buf = b"".join(audio_buffer_raw)
                frame, remainder = buf[:VAD_FRAME_BYTES], buf[VAD_FRAME_BYTES:]
                audio_buffer_raw.clear()
                audio_buffer_raw.append(remainder)

                if vad.is_speech(frame, AUDIO_SAMPLE_RATE):
                    speech_detected = True
                    last_speech_frame_time = datetime.utcnow()

                if speech_detected and (
                    (datetime.utcnow() - last_speech_frame_time).total_seconds()
                    * 1000
                    > silence_timeout_ms
                ):
                    processing = True
                    full_audio = b"".join(audio_buffer_raw)
                    audio_buffer_raw.clear()

                    audio_path = None
                    try:
                        seg = AudioSegment(
                            data=full_audio,
                            sample_width=AUDIO_WIDTH,
                            frame_rate=AUDIO_SAMPLE_RATE,
                            channels=AUDIO_CHANNELS,
                        )
                        file_name = f"user_response_{uuid.uuid4()}.mp3"
                        audio_path = os.path.join(RECORDINGS_DIR, file_name)
                        seg.export(audio_path, format="mp3")
                        print(f"User audio saved: {audio_path}")
                    except Exception as e:
                        print("Audio save error:", e)

                    user_text = await asyncio.to_thread(
                        transcribe_audio_bytes, full_audio
                    )
                    print("User said:", user_text)

                    if current_question_db_id:
                        db.add(
                            UserResponse(
                                question_id=current_question_db_id,
                                response_text=user_text,
                                timestamp=datetime.utcnow(),
                                response_audio_path=audio_path,
                            )
                        )
                        db.commit()

                    conversation_history.append({"role": "user", "content": user_text})

                    ack_text = "Okay."
                    ack_audio = await asyncio.to_thread(
                        text_to_audio_bytes, ack_text
                    )
                    if ack_audio:
                        await websocket.send_bytes(ack_audio)

                    ai_text = await query_ai(user_text)
                    print("AI:", ai_text)

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

                    conversation_history.append(
                        {"role": "assistant", "content": ai_text}
                    )

                    ai_audio = await asyncio.to_thread(
                        text_to_audio_bytes, ai_text
                    )
                    if ai_audio:
                        await websocket.send_bytes(ai_audio)
                    else:
                        await websocket.send_text("AI audio generation failed.")

                    # Check if this was the last allowed question
                    if question_count >= MAX_QUESTION_EXCHANGES:
                        await asyncio.sleep(1)  # Give time for the last answer to be heard
                        await end_session("Maximum number of questions reached")
                        break
                        
                    speech_detected = False
                    last_speech_frame_time = datetime.utcnow()
                    processing = False

            await asyncio.sleep(0.01)

    except WebSocketDisconnect:
        print("WebSocket disconnected", session_id)
        db_session.end_time = datetime.utcnow()
        db.add(db_session)
        db.commit()
        active_sessions.pop(session_id, None)

    except Exception as e:
        print("WS error:", e)
        await websocket.send_text(f"ERROR: {e}")
        
        # Also update end_time on error
        if not db_session.end_time:
            db_session.end_time = datetime.utcnow()
            db.add(db_session)
            db.commit()

    finally:
        active_sessions.pop(session_id, None)