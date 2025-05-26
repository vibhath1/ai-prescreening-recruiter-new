import logging
from fastapi import APIRouter, File, UploadFile, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import Dict, Any
from backend.utils.resume_parser import parse_resume
from backend.database import get_db # Assuming get_db function
from backend.models import Resume # Assuming Resume model
from backend.routes.auth import get_current_user   # << NEW

router = APIRouter()
logger = logging.getLogger(__name__) # Add this line

@router.post("/upload-resume/") # Added trailing slash for consistency
async def upload_resume(
    file: UploadFile = File(...),
    db: Session = Depends(get_db), # Inject database session
    current_user = Depends(get_current_user)        # << user injected
):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed.")
    
    try:
        content = await file.read()
        
        # Parse the resume to get both raw text and structured data
        raw_text, parsed_data = parse_resume(content)
        
        # Debug: Print parsed data for troubleshooting
        print(f"Parsed resume raw text sample: {raw_text[:100]}...")
        print(f"Parsed resume structured data: {parsed_data}")

        # --- Store resume data in the database ---
        # Assuming a user_id is available from authentication (placeholder for now)
        # In a real app, you'd get this from a JWT token or session.
        # For demonstration, let's use a dummy user_id or remove if not applicable yet.
        user_id_placeholder = 1 # Replace with actual user ID from authentication
        
        new_resume = Resume(
            user_id=current_user.id,               # << real FK!
            original_filename=file.filename,
            raw_text_content=raw_text,
            parsed_data_json=parsed_data
        )
          

        db.add(new_resume)
        db.commit()
        db.refresh(new_resume) # Refresh to get the generated ID

        return {
            "message": "Resume uploaded and parsed successfully!",
            "resume_id": new_resume.id,
            "parsed_data": parsed_data # Optionally return parsed data to frontend
        }
    except Exception as e:
        db.rollback() # <--- IMPORTANT: Rollback the transaction on error!
        logger.exception("Failed to process resume in upload_resume route.") # <--- THIS IS THE FIX for TypeError
        raise HTTPException(status_code=500, detail=f"Error processing resume: {str(e)}")