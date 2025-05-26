from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload
from typing import List, Dict, Any
from datetime import datetime

from backend.database import get_db
from backend.models import InterviewSession, InterviewQuestion, UserResponse, Resume, User # Import all relevant models
from backend.routes.auth import get_current_user # Assuming authentication is required to view reports

router = APIRouter()

@router.get("/sessions/", response_model=List[Dict[str, Any]])
async def get_all_interview_sessions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user) # Only logged-in users can view sessions
):
    """
    Retrieves a list of all interview sessions, optionally filtered by the current user.
    """
    # Fetch all sessions associated with the current user, ordered by start time
    sessions = db.query(InterviewSession)\
                 .filter(InterviewSession.user_id == current_user.id)\
                 .order_by(InterviewSession.start_time.desc())\
                 .all()
    
    if not sessions:
        return [] # Return empty list if no sessions found

    # Prepare response data, including related resume info
    sessions_data = []
    for session in sessions:
        # Load resume information for each session if needed (eager loading is better for performance)
        resume = db.query(Resume).filter(Resume.id == session.resume_id).first()
        
        sessions_data.append({
            "session_id": session.id,
            "resume_filename": resume.original_filename if resume else "N/A",
            "candidate_name": f"Candidate {resume.user_id}" if resume else "N/A", # Placeholder, would get from User/Candidate model
            "start_time": session.start_time.isoformat(),
            "end_time": session.end_time.isoformat() if session.end_time else None,
            "total_questions": len(session.questions) # Count questions in this session
        })
    
    return sessions_data

@router.get("/sessions/{session_id}/report/", response_model=Dict[str, Any])
async def get_interview_report(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Retrieves a detailed report for a specific interview session, including the full conversation.
    """
    # Fetch the interview session with eager loading of questions and user responses
    session = db.query(InterviewSession)\
                .options(joinedload(InterviewSession.questions).joinedload(InterviewQuestion.user_response))\
                .filter(InterviewSession.id == session_id)\
                .first()
    
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Interview session not found."
        )
    
    # Ensure the session belongs to the current user
    if session.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view this report."
        )

    # Prepare conversation history
    conversation_log = []
    for question in session.questions:
        conversation_log.append({
            "role": "ai_recruiter",
            "text": question.question_text,
            "timestamp": question.timestamp.isoformat()
        })
        if question.user_response:
            response = question.user_response
            conversation_log.append({
                "role": "candidate",
                "text": response.response_text,
                "timestamp": response.timestamp.isoformat(),
                "audio_path": response.response_audio_path # Path to the stored audio file
            })
    
    # Sort conversation by timestamp
    conversation_log.sort(key=lambda x: datetime.fromisoformat(x['timestamp']))

    # Get resume details
    resume = db.query(Resume).filter(Resume.id == session.resume_id).first()

    report_data = {
        "session_id": session.id,
        "user_id": session.user_id,
        "resume_id": session.resume_id,
        "resume_filename": resume.original_filename if resume else "N/A",
        "start_time": session.start_time.isoformat(),
        "end_time": session.end_time.isoformat() if session.end_time else None,
        "conversation_log": conversation_log
    }

    return report_data

# You could add more report types here:
# - /sessions/{session_id}/summary: AI-generated summary of the interview.
# - /sessions/{session_id}/sentiment-analysis: Analyze sentiment of candidate responses.
# - /sessions/{session_id}/skill-match: Compare candidate skills to job requirements.