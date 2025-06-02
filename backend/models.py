from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

# --- IMPORTANT CHANGE HERE: Import JSONB from PostgreSQL dialect ---
from sqlalchemy.dialects.postgresql import JSONB # For native PostgreSQL JSONB type

# Base class for declarative models
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    role = Column(String, nullable=False, default="candidate")  # Add this line

    # Relationships
    resumes = relationship("Resume", back_populates="owner")
    interview_sessions = relationship("InterviewSession", back_populates="user")


class Resume(Base):
    """
    Represents an uploaded resume, storing its raw text and parsed structured data.
    """
    __tablename__ = "resumes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False) # Link to the user who uploaded it
    
    original_filename = Column(String, nullable=False)
    upload_timestamp = Column(DateTime, default=datetime.utcnow)
    
    raw_text_content = Column(Text, nullable=False) # Full text content of the resume
    
    # --- IMPORTANT CHANGE HERE: Use JSONB directly ---
    parsed_data_json = Column(JSONB, nullable=False) 

    # Relationships
    owner = relationship("User", back_populates="resumes")
    interview_sessions = relationship("InterviewSession", back_populates="resume")


class InterviewSession(Base):
    """
    Represents a single interview session between the AI and a user/candidate.
    """
    __tablename__ = "interview_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False) # The user (e.g., recruiter) associated with this session
    resume_id = Column(Integer, ForeignKey("resumes.id"), nullable=False) # The resume being discussed

    start_time = Column(DateTime, default=datetime.utcnow)
    end_time = Column(DateTime, nullable=True) # Will be set when interview concludes

    # Relationships
    user = relationship("User", back_populates="interview_sessions")
    resume = relationship("Resume", back_populates="interview_sessions")
    questions = relationship("InterviewQuestion", back_populates="session", order_by="InterviewQuestion.timestamp")


class InterviewQuestion(Base):
    """
    Represents a question asked by the AI during an interview session.
    """
    __tablename__ = "interview_questions"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("interview_sessions.id"), nullable=False)
    
    question_text = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)

    # Relationships
    session = relationship("InterviewSession", back_populates="questions")
    user_response = relationship("UserResponse", uselist=False, back_populates="question") # One-to-one with UserResponse


class UserResponse(Base):
    """
    Represents the user's transcribed response to an AI question.
    """
    __tablename__ = "user_responses"

    id = Column(Integer, primary_key=True, index=True)
    question_id = Column(Integer, ForeignKey("interview_questions.id"), unique=True, nullable=False) # One-to-one link back to question
    
    response_text = Column(Text, nullable=False) # Transcribed text
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    # Optional: Path to the original audio file of the user's response
    response_audio_path = Column(String, nullable=True) 

    # Relationships
    question = relationship("InterviewQuestion", back_populates="user_response")
