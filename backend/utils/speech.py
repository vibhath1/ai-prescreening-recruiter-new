import os
from pydub import AudioSegment
from dotenv import load_dotenv
import tempfile
from gtts import gTTS
import io
import whisper
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Load Whisper Model
try:
    logger.info("Loading OpenAI Whisper 'base.en' model...")
    whisper_model = whisper.load_model("base.en")
    logger.info("Whisper model loaded successfully.")
except Exception as e:
    logger.error(f"Error loading Whisper model: {e}")
    whisper_model = None

def transcribe_audio_bytes(audio_bytes: bytes) -> str:
    if whisper_model is None:
        return "Speech-to-Text service unavailable."

    temp_audio_file = None
    try:
        temp_audio_file = tempfile.NamedTemporaryFile(delete=False, suffix=".webm").name
        with open(temp_audio_file, 'wb') as f:
            f.write(audio_bytes)

        logger.info(f"Transcribing {len(audio_bytes)} bytes using Whisper...")
        result = whisper_model.transcribe(temp_audio_file)
        transcribed_text = result["text"]
        logger.info("Transcription complete.")
        return transcribed_text
    except Exception as e:
        logger.error(f"Error in speech-to-text conversion with Whisper: {str(e)}")
        return f"Error: Could not transcribe audio. {str(e)}"
    finally:
        if temp_audio_file and os.path.exists(temp_audio_file):
            try:
                os.unlink(temp_audio_file)
                logger.info(f"Cleaned up temporary audio file: {temp_audio_file}")
            except Exception as e:
                logger.error(f"Failed to clean up temporary audio file {temp_audio_file}: {str(e)}")

def text_to_audio_bytes(text: str, save_path=None) -> bytes:
    try:
        audio_buffer = io.BytesIO()
        tts = gTTS(text=text, lang='en')
        tts.write_to_fp(audio_buffer)
        audio_buffer.seek(0)
        audio_bytes = audio_buffer.getvalue()

        if save_path:
            os.makedirs(os.path.dirname(os.path.abspath(save_path)), exist_ok=True)
            with open(save_path, 'wb') as f:
                f.write(audio_bytes)
            logger.info(f"Audio saved to: {save_path}")

        logger.info(f"Generated {len(audio_bytes)} bytes of audio for text: {text[:50]}...")
        return audio_bytes
    except Exception as e:
        logger.error(f"Error in text-to-speech conversion with gTTS: {str(e)}")
        return b""