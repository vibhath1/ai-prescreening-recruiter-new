"""
ai.py Dynamic prompt builder with Mistral model for interactive interviews
"""
import os
import requests
import logging
import random
from typing import List, Dict, Any, TypedDict
from dotenv import load_dotenv

load_dotenv()

os.environ["HUGGINGFACE_API_TOKEN"] = "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"
HF_TOKEN = os.getenv("HUGGINGFACE_API_TOKEN")

if not HF_TOKEN:
    import warnings
    warnings.warn("HUGGINGFACE_API_TOKEN missing; AI endpoints will not work.", RuntimeWarning)

headers = {
    "Authorization": f"Bearer {HF_TOKEN}",
    "Content-Type": "application/json"
}

DEFAULT_LLM_MODEL = "mistralai/Mistral-7B-Instruct-v0.3"
API_URL = f"https://api-inference.huggingface.co/models/{DEFAULT_LLM_MODEL}"

class ConvTurn(TypedDict):
    role: str
    content: str

def get_ai_interview_response(
    parsed_resume_data: Dict[str, Any],
    conversation_history: List[ConvTurn],
    current_user_response: str = ""
) -> str:
    try:
        system_prompt = build_system_prompt(parsed_resume_data)
        prompt_text = build_prompt(system_prompt, conversation_history, current_user_response)

        payload = {
            "inputs": prompt_text,
            "parameters": {
                "max_new_tokens": 200,
                "temperature": 0.9,
                "top_p": 0.9,
                "repetition_penalty": 1.05,
                "return_full_text": False
            }
        }

        response = requests.post(API_URL, headers=headers, json=payload, timeout=30)

        if response.status_code == 200:
            result = response.json()
            if isinstance(result, list) and result:
                return postprocess(result[0].get("generated_text", ""))
            elif isinstance(result, dict):
                return postprocess(result.get("generated_text", ""))
            else:
                return postprocess(str(result))
        elif response.status_code in [404, 401, 403]:
            logging.error(f"API error: {response.status_code}")
            raise Exception(f"API request failed: {response.status_code}")
        else:
            logging.error(f"API request failed: {response.status_code} - {response.text}")
            raise Exception(f"API request failed: {response.status_code}")

    except Exception as e:
        logging.exception(f"HF generation failed: {str(e)}")
        acknowledgment = "Thank you for sharing that information. " if conversation_history and current_user_response else ""
        question_index = len([t for t in conversation_history if t["role"] == "assistant"])
        fallback_questions = generate_fallback_questions(parsed_resume_data)
        if question_index < len(fallback_questions):
            return acknowledgment + fallback_questions[question_index]
        else:
            return ("Thank you for your time today. We've covered several important aspects "
                    "of your background and experience. We'll review your responses and get "
                    "back to you soon about next steps.")

def build_system_prompt(resume_dict: Dict[str, Any]) -> str:
    skills = ", ".join(resume_dict.get("skills", [])) or "Not specified"
    tools = ", ".join(resume_dict.get("tools", [])) or "Not specified"
    languages = ", ".join(resume_dict.get("languages", [])) or "Not specified"
    summary = resume_dict.get("job_description_summary", "Not specified")

    resume_block = (
        f"Here is the candidate's resume summary:\n"
        f"• Skills: {skills}\n"
        f"• Tools: {tools}\n"
        f"• Languages: {languages}\n"
        f"• Experience summary: {summary}"
    )

    recruiter_rules = (
        "You are an AI recruiter conducting a preliminary interview.\n"
        "• Ask one clear and relevant question at a time based on the resume and prior answers.\n"
        "• Briefly acknowledge the user's previous answer.\n"
        "• Never generate more than one question per prompt.\n"
        "• Conclude politely once enough information is collected."
    )

    return f"<<SYS>>\n{recruiter_rules}\n\n{resume_block}\n<</SYS>>"

def build_prompt(
    system_prompt: str,
    history: List[ConvTurn],
    latest_user: str
) -> str:
    segments = []

    if not history:
        greeting = random.choice([
            "Hello! Welcome to your mock interview.",
            "Hi there! Let's begin your AI-powered interview.",
            "Welcome! I’ll be guiding you through this interview.",
        ])
        segments.append(f"<s>[INST] {system_prompt}\n{greeting} [/INST]")
    else:
        segments.append(f"<s>[INST] {system_prompt}")
        for turn in history:
            if turn["role"] == "user":
                segments.append(f"[INST] {turn['content']} [/INST]")
            elif turn["role"] == "assistant":
                segments.append(f"{turn['content']} </s>")

        if latest_user:
            segments.append(f"[INST] {latest_user} [/INST]")

    full_prompt = "".join(segments)
    return truncate_if_needed(full_prompt, max_tokens=7500)

def truncate_if_needed(prompt: str, max_tokens: int) -> str:
    rough_char_limit = max_tokens * 4
    if len(prompt) <= rough_char_limit:
        return prompt
    sys_end = prompt.find("[/INST]") + len("[/INST]")
    return prompt[:sys_end] + "\n...\n" + prompt[-rough_char_limit:]

def postprocess(raw: str) -> str:
    text = raw.strip()
    if "[INST]" in text:
        text = text.split("[INST]")[-1]
    if "</s>" in text:
        text = text.split("</s>")[0]

    for prefix in ("Certainly,", "Sure,", "Okay,", "Alright,"):
        if text.lower().startswith(prefix.lower()):
            text = text[len(prefix):].strip()

    return text.strip()

def generate_fallback_questions(resume_data: Dict[str, Any]) -> List[str]:
    base_questions = [
        "Can you walk me through your resume?",
        "What role are you most interested in and why?",
        "Tell me about a technical challenge you solved.",
        "Which of your skills do you use most often?",
        "What do you expect from your next job or team?",
        "Why are you looking for new opportunities?",
        "How do you approach problem-solving at work?"
    ]
    random.shuffle(base_questions)
    return base_questions
