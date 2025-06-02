import subprocess
import tempfile
import os
import whisper
import logging
from gtts import gTTS
import io

logger = logging.getLogger(__name__)

load_dotenv()

# Load Whisper model globally
whisper_model = whisper.load_model("tiny")

def text_to_audio_bytes(text: str, save_path: str = None) -> bytes:
    """
    Converts a text string to spoken audio (MP3) and returns the byte content.
    """
    try:
        tts = gTTS(text)
        buf = io.BytesIO()
        tts.write_to_fp(buf)
        buf.seek(0)
        return buf.read()
    except Exception as e:
        logger.error(f"Text-to-Speech failed: {e}")
        raise RuntimeError("Text-to-Speech generation failed")

def transcribe_audio_bytes(audio_bytes: bytes) -> str:
    """
    Takes raw audio bytes (e.g. PCM/WAV) and transcribes using Whisper.
    """
    if whisper_model is None:
        return "Speech-to-Text service unavailable."

    temp_audio_path = None
    try:
        # Save audio to a temporary .wav file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_audio:
            temp_audio.write(audio_bytes)
            temp_audio.flush()
            temp_audio_path = temp_audio.name

        logger.info(f"Transcribing {len(audio_bytes)} bytes using Whisper from {temp_audio_path}...")
        result = whisper_model.transcribe(temp_audio_path)
        logger.info("Transcription complete.")
        return result["text"]

    except Exception as e:
        logger.error(f"Error in speech-to-text conversion with Whisper: {str(e)}")
        return f"Error: Could not transcribe audio. {str(e)}"

    finally:
        if temp_audio_path and os.path.exists(temp_audio_path):
            try:
                os.unlink(temp_audio_path)
                logger.info(f"Cleaned up temporary audio file: {temp_audio_path}")
            except Exception as e:
                logger.warning(f"Failed to remove temp file: {e}")
