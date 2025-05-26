# backend/database.py
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# 1. Correct import for Base from your models.py
# Assuming your models.py is at `backend/models/models.py`
from backend.models import Base # Corrected import path

# REMOVE THESE LINES - THEY ARE THE PROBLEM:
# from sqlalchemy.ext.declarative import declarative_base # Redundant
# from .database import engine    # Circular import
# Base.metadata.create_all(bind=engine) # Misplaced, uses 'engine' before defined

# --- Database Configuration for PostgreSQL ---
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "1234")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_DB = os.getenv("POSTGRES_DB", "ai_recruiter_db")

print(f"DEBUG: POSTGRES_USER from env: '{POSTGRES_USER}'")
print(f"DEBUG: POSTGRES_PASSWORD from env: '{POSTGRES_PASSWORD}' (masked for security)")
print(f"DEBUG: POSTGRES_HOST from env: '{POSTGRES_HOST}'")
print(f"DEBUG: POSTGRES_DB from env: '{POSTGRES_DB}'")

# Construct the SQLAlchemy database URL for PostgreSQL
SQLALCHEMY_DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"

# 2. Define the engine *after* SQLALCHEMY_DATABASE_URL is constructed
engine = create_engine(
    SQLALCHEMY_DATABASE_URL
    # Optional: Add connection pooling for production readiness
    # pool_size=10, max_overflow=20
)

# --- Create a SessionLocal class ---
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# --- Dependency for FastAPI routes ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Function to Create All Tables ---
# 3. Call Base.metadata.create_all(bind=engine) within this function
def create_db_and_tables():
    """
    Creates all database tables defined in models.py based on the Base metadata.
    Call this function once when your application starts to set up the database schema.
    """
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine) # This is now correctly placed
    print("Database tables created (or already exist).")