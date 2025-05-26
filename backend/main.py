# backend/main.py
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv())                     # loads .env no matter where uvicorn starts
import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import logging
from backend.routes import auth, resume, interview, report
from backend.database import create_db_and_tables

app = FastAPI(title="AI Prescreening Recruiter API")

# ──────────────────────────────────────────────────────────────────────
# CORS  –  add any frontend URL(s) you need; "*" is OK during local dev
# ──────────────────────────────────────────────────────────────────────
origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ──────────────────────────────────────────────────────────────────────
# Routers
# Each router already defines   prefix="/api"
# so we do NOT add another prefix here (avoids “/api/api/…” paths)
# ──────────────────────────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(resume.router)
app.include_router(interview.router)
app.include_router(report.router)

# ──────────────────────────────────────────────────────────────────────
# Health-check
# ──────────────────────────────────────────────────────────────────────
@app.get("/")
async def root():
    return {"message": "AI Prescreening Recruiter API is running"}

# ──────────────────────────────────────────────────────────────────────
# Startup – ensure DB schema exists
# ──────────────────────────────────────────────────────────────────────
@app.on_event("startup")
def on_startup() -> None:
    create_db_and_tables()

@app.get("/audio-files/")
async def list_audio_files():
    """List all available audio files."""
    audio_dir = "./backend/media/audio"
    
    if not os.path.exists(audio_dir):
        return {"files": []}
    
    files = [f for f in os.listdir(audio_dir) if f.endswith(".mp3")]
    return {
        "files": [
            {
                "filename": file,
                "url": f"/audio/{file}",
                "created": os.path.getctime(os.path.join(audio_dir, file))
            }
            for file in files
        ]
    }
from fastapi.responses import FileResponse

@app.get("/audio/{filename}")
async def get_audio(filename: str):
    """Get a saved audio file by its filename."""
    file_path = f"./backend/media/audio/{filename}"
    
    if not os.path.exists(file_path):
        logging.error(f"Audio file not found: {file_path}")
        raise HTTPException(status_code=404, detail="Audio file not found")
    
    logging.info(f"Serving audio file: {file_path}")
    return FileResponse(
        file_path,
        media_type="audio/mpeg",
        filename=filename
    )