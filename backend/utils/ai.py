"""
ai.py – Minimal prompt builder with Mistral model
"""

import os
import requests
import logging
from typing import List, Dict, Any, TypedDict
from dotenv import load_dotenv

load_dotenv()


HF_TOKEN = os.getenv("HUGGINGFACE_API_TOKEN")

if not HF_TOKEN:
    import warnings
    warnings.warn("HUGGINGFACE_API_TOKEN missing; AI endpoints will not work.", RuntimeWarning)

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

        headers = {"Authorization": f"Bearer {HF_TOKEN}"}
        payload = {
            "inputs": prompt_text,
            "parameters": {
                "max_new_tokens": 200,
                "temperature": 0.7,
                "top_p": 0.9,
                "repetition_penalty": 1.1,
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
        questions = [
            "Could you tell me about your professional background and experience?",
            "What interests you about this position?",
            "Could you describe a challenging project you've worked on?",
            "What are your key strengths that make you suitable for this role?",
            "How do you handle pressure or tight deadlines?",
            "Where do you see yourself professionally in the next few years?",
            "What questions do you have about the role or our company?"
        ]
        if question_index < len(questions):
            return acknowledgment + questions[question_index]
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
        "• Ask clear, concise, relevant questions.\n"
        "• Briefly acknowledge the candidate's previous answer before asking the next question.\n"
        "• Conclude politely when sufficient information has been gathered.\n"
        "Reply with either one question or a concluding statement—nothing else."
    )

    return f"<<SYS>>\n{recruiter_rules}\n\n{resume_block}\n<</SYS>>"

def build_prompt(
    system_prompt: str,
    history: List[ConvTurn],
    latest_user: str
) -> str:
    segments = []

    if history:
        first_user = history[0]["content"] if history[0]["role"] == "user" else ""
        segments.append(
            f"<s>[INST] {system_prompt}\n{first_user} [/INST]"
        )
        if history[0]["role"] == "assistant":
            segments.append(history[0]["content"] + " </s>")
    else:
        first_user_content = latest_user or "Please start the interview."
        segments.append(
            f"<s>[INST] {system_prompt}\n{first_user_content} [/INST]"
        )
        latest_user = ""

    for turn in history[1:]:
        if turn["role"] == "assistant":
            segments.append(f"{turn['content']} </s>")
        else:
            segments.append(f"[INST] {turn['content']} [/INST]")

    if latest_user:
        segments.append(f"[INST] {latest_user} [/INST]")

    full_prompt = "".join(segments)
    full_prompt = truncate_if_needed(full_prompt, max_tokens=7500)

    logging.debug("Prompt sent to model:\n%s", full_prompt[:2000])
    return full_prompt

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