import pdfplumber
import io
import re
import json # For handling JSON output, though SQLAlchemy's JSONB might not strictly need it here

def parse_resume(pdf_content: bytes) -> tuple[str, dict]:
    """
    Parse a PDF resume, extract text, and then attempt to extract specific fields.
    
    Args:
        pdf_content (bytes): Raw bytes content of the PDF file.
    
    Returns:
        tuple[str, dict]: A tuple containing:
                          - The full extracted raw text from the PDF.
                          - A dictionary with extracted structured data (skills, tools, etc.).
    """
    raw_text = ""
    try:
        with pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
            for page in pdf.pages:
                extracted = page.extract_text()
                if extracted:
                    raw_text += extracted + "\n"
        
        if not raw_text:
            return "No text could be extracted from the PDF.", {}

        # --- Post-processing and Structured Data Extraction ---
        
        # 1. Normalize text: Lowercase, remove extra whitespace, split into lines
        normalized_text = raw_text.lower().strip()
        lines = [line.strip() for line in normalized_text.split('\n') if line.strip()]

        parsed_data = {
            "skills": [],
            "tools": [],
            "languages": [],
            "experience": "",
            "job_description_summary": "" # Will be a summary of experience
        }

        # --- Simple Section-Based Extraction ---
        # Define common section headers (case-insensitive)
        # Add more as needed for different resume layouts
        sections = {
            "education": ["education"],
            "experience": ["experience", "work experience", "professional experience", "employment history"],
            "skills": ["skills", "technical skills", "core competencies", "proficiencies"],
            "languages_known": ["languages", "spoken languages"],
            "tools": ["tools", "technologies", "software", "platforms"],
            # Add other sections you might want to extract later
        }

        current_section = None
        section_content = {key: [] for key in sections.keys()} # Store content for each section

        # Attempt to split text into sections based on headers
        # This is a very basic approach; more robust parsers use fuzzy matching or ML.
        for line in lines:
            found_header = False
            for section_name, header_keywords in sections.items():
                # Check if the line matches a header (e.g., "SKILLS" or "Experience")
                # Using regex to look for the header at the start of a line, optionally followed by non-alphanumeric chars
                # and ensuring it's not just part of a longer word.
                for keyword in header_keywords:
                    # Regex to match the keyword at the start of a line or after a line break, followed by optional punctuation
                    if re.match(r'^\s*' + re.escape(keyword) + r'\s*[:\-]*\s*$', line, re.IGNORECASE):
                        current_section = section_name
                        found_header = True
                        break # Found a header for this section, move to next line
                if found_header:
                    break
            
            if not found_header and current_section:
                section_content[current_section].append(line)
        
        # --- Populate parsed_data from extracted sections ---

        # Skills, Tools, Languages: Often in lists, or comma-separated.
        # We'll just take the content of the relevant section.
        # Further parsing (e.g., splitting into individual skills) would be needed for more detail.
        
        if "skills" in section_content and section_content["skills"]:
            # For simplicity, combine lines from the skills section.
            # You might need smarter parsing (e.g., splitting by bullet points, commas)
            # and potentially filtering out non-skill keywords.
            parsed_data["skills"] = [s.strip() for s in " ".join(section_content["skills"]).split(',') if s.strip()]
            # A more sophisticated approach would be to use an NLP model for skill extraction.

        if "tools" in section_content and section_content["tools"]:
            parsed_data["tools"] = [t.strip() for t in " ".join(section_content["tools"]).split(',') if t.strip()]

        if "languages_known" in section_content and section_content["languages_known"]:
            parsed_data["languages"] = [l.strip() for l in " ".join(section_content["languages_known"]).split(',') if l.strip()]

        if "experience" in section_content and section_content["experience"]:
            # For experience, just combine all lines into a single block of text.
            # This captures the "job description" from their past roles.
            parsed_data["experience"] = "\n".join(section_content["experience"])
            parsed_data["job_description_summary"] = parsed_data["experience"] # Use experience as job_description_summary

        # You can add more specific logic here to refine the extraction,
        # e.g., using spaCy to identify entities, or a small LLM for summarization.

        return raw_text, parsed_data

    except Exception as e:
        print(f"Error parsing PDF in resume_parser: {e}", exc_info=True)
        # Return empty data on parsing failure
        return raw_text, {"skills": [], "tools": [], "languages": [], "experience": "", "job_description_summary": ""}