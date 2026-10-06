"""
SoMeet Web - Speech Recognition & Meeting Intelligence Engine
Provides:
1. Real-time sub-second local streaming ASR using Faster-Whisper (Int8 acoustic engine)
2. Post-meeting AI intelligence & summarization using Google Gemini
"""
import numpy as np
import requests
import json
from pathlib import Path
from typing import Optional
from config import GEMINI_API_KEY

_whisper_model = None


def get_whisper_model():
    """Lazy-loads the Faster-Whisper multilingual model on CPU with Int8 quantization."""
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel
        print("[ASR Engine] Loading Faster-Whisper Small (int8) into memory...")
        _whisper_model = WhisperModel("small", device="cpu", compute_type="int8")
        print("[ASR Engine] Faster-Whisper model ready for real-time streaming.")
    return _whisper_model


def transcribe_pcm(pcm_bytes: bytes, language: Optional[str] = None) -> str:
    """
    Transcribes raw 16kHz mono 16-bit PCM audio stream with built-in VAD.
    Returns clean verbatim text with zero chunking artifacts.
    """
    if not pcm_bytes or len(pcm_bytes) < 3200:  # Less than 100ms of 16kHz audio
        return ""

    try:
        model = get_whisper_model()
        # Convert int16 bytes to float32 normalized to [-1.0, 1.0]
        audio_int16 = np.frombuffer(pcm_bytes, dtype=np.int16)
        audio_float32 = audio_int16.astype(np.float32) / 32768.0

        segments, info = model.transcribe(
            audio_float32,
            beam_size=1,
            language=language,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=400)
        )
        texts = [seg.text.strip() for seg in segments if seg.text.strip()]
        if not texts:
            # Fallback without vad filter in case microphone input was soft
            segments, info = model.transcribe(
                audio_float32,
                beam_size=1,
                language=language,
                vad_filter=False
            )
            texts = [seg.text.strip() for seg in segments if seg.text.strip()]
        return " ".join(texts)
    except Exception as e:
        print(f"[ASR Engine] Transcription error: {e}")
        return ""


def transcribe_audio_base64(b64_audio: str, mime_type: str = "audio/webm", context: str = "") -> str:
    """
    Fallback: Transcribes audio payload using Google Gemini Multimodal API.
    """
    if not GEMINI_API_KEY:
        return ""

    models_to_try = ["gemini-flash-lite-latest", "gemini-3.1-flash-lite"]
    
    context_block = ""
    if context.strip():
        context_block = f"Recent context for conversational flow:\n\"\"\"{context.strip()}\"\"\"\n\n"

    prompt = (
        "You are an expert speech-to-text recognition and reasoning engine. "
        "Listen to this audio recording and transcribe the spoken words verbatim.\n\n"
        f"{context_block}"
        "Rules:\n"
        "1. Accurately transcribe what is spoken verbatim.\n"
        "2. Do NOT summarize or invent words.\n"
        "3. Output as a clean, continuous narrative without line breaks.\n"
        "4. If silence or noise, return an empty string.\n"
        "5. Output ONLY the raw transcript."
    )

    payload = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": mime_type, "data": b64_audio}}
            ]
        }],
        "generationConfig": {
            "temperature": 0.0
        }
    }

    for model in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
        try:
            resp = requests.post(url, json=payload, timeout=12)
            if resp.status_code == 200:
                text = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                return text.strip('"\'')
            elif resp.status_code in (429, 503):
                continue
        except Exception:
            continue

    return ""


def summarize_meeting(transcript: str) -> str:
    """
    Uses Google Gemini to generate structured meeting intelligence:
    - Executive Overview
    - Key Discussion Points
    - Decisions & Agreed Outcomes
    - Action Items & Next Steps
    """
    if not transcript.strip():
        return "No transcript content available to summarize."

    if not GEMINI_API_KEY:
        return "Summary unavailable: Missing Google Gemini API key."

    prompt = (
        "You are an executive meeting assistant and chief of staff. "
        "Review the following verbatim meeting transcript and generate a structured, professional meeting summary.\n\n"
        "TRANSCRIPT:\n"
        f"\"\"\"\n{transcript.strip()}\n\"\"\"\n\n"
        "Output format (strict markdown):\n"
        "### 📌 Executive Overview\n"
        "(A crisp 1-2 sentence executive summary of the meeting's primary objective and outcome)\n\n"
        "### 🔑 Key Discussion Points\n"
        "- Bullet points capturing the core topics and arguments\n\n"
        "### 🎯 Decisions & Agreements\n"
        "- Concrete decisions confirmed during the meeting\n\n"
        "### 📋 Action Items & Next Steps\n"
        "- [ ] **[Owner/Task]** Clear, actionable task with intended outcome\n"
    )

    models_to_try = ["gemini-flash-lite-latest", "gemini-3.1-flash-lite"]
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2}
    }

    for model in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
        try:
            resp = requests.post(url, json=payload, timeout=20)
            if resp.status_code == 200:
                text = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                return text
        except Exception as e:
            print(f"[Summary] Gemini error with {model}: {e}")
            continue

    return "Failed to generate meeting summary. Please check connection and try again."
