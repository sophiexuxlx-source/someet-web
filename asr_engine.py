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
        print("[ASR Engine] Loading Faster-Whisper Tiny (int8) into memory...")
        # Free cloud instances have 512MB RAM, tiny takes ~150MB and runs instantly
        _whisper_model = WhisperModel("tiny", device="cpu", compute_type="int8")
        print("[ASR Engine] Faster-Whisper model ready for real-time streaming.")
    return _whisper_model


def transcribe_pcm(pcm_bytes: bytes, language: Optional[str] = None, initial_prompt: Optional[str] = None) -> str:
    """
    Transcribes raw 16kHz mono 16-bit PCM audio stream with built-in VAD.
    Accepts optional initial_prompt (transcription context & terms) to prime Whisper.
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
            initial_prompt=initial_prompt if initial_prompt else None,
            condition_on_previous_text=False,
            repetition_penalty=1.2,
            no_repeat_ngram_size=3,
            hallucination_silence_threshold=1.5,
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=1000, speech_pad_ms=400, threshold=0.35),
            temperature=0.0
        )
        texts = [seg.text.strip() for seg in segments if seg.text.strip()]
        if not texts:
            # Fallback without vad filter in case microphone input was soft
            segments, info = model.transcribe(
                audio_float32,
                beam_size=1,
                language=language,
                initial_prompt=initial_prompt if initial_prompt else None,
                condition_on_previous_text=False,
                repetition_penalty=1.2,
                no_repeat_ngram_size=3,
                hallucination_silence_threshold=1.5,
                vad_filter=False,
                temperature=0.0
            )
            texts = [seg.text.strip() for seg in segments if seg.text.strip()]
        return " ".join(texts)
    except Exception as e:
        print(f"[ASR Engine] Transcription error: {e}")
        return ""


def transcribe_audio_base64(b64_audio: str, mime_type: str = "audio/wav", context: str = "") -> str:
    """
    Fallback: Transcribes audio payload using Google Gemini Multimodal API.
    """
    if not GEMINI_API_KEY:
        return ""

    models_to_try = ["gemini-3.8-flash", "gemini-flash-latest", "gemini-flash-lite-latest", "gemini-2.5-flash"]

    prompt = (
        "You are an expert speech-to-text recognition engine. "
        "Listen to the audio recording and transcribe all spoken words verbatim from start to finish.\n\n"
        "Rules:\n"
        "1. Accurately transcribe everything spoken across all sentences without dropping or truncating any parts.\n"
        "2. Preserve natural speech flow and all sentences.\n"
        "3. Do NOT summarize or invent words.\n"
        "4. If silence or noise, return an empty string.\n"
        "5. Output ONLY the raw transcript text."
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
            resp = requests.post(url, json=payload, timeout=35)
            if resp.status_code == 200:
                text = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                return text.strip('"\'')
            elif resp.status_code in (429, 503):
                continue
        except Exception as e:
            print(f"[Gemini Transcribe Error with {model}]: {e}")
            continue

    return ""


def polish_speech_transcript(raw_text: str, context_prompt: str = "", terms: str = "") -> str:
    """
    Sub-second Gemini speech intelligence pass:
    - Restores natural punctuation (commas, periods, question marks)
    - Fixes phonetic acoustic slips (e.g. 'in any gravity' -> 'in Antigravity', 'Click record' -> 'click Record')
    - Incorporates user-supplied domain context prompt and custom terminology/names
    - Preserves user verbatim words and sentences
    """
    if not raw_text or not raw_text.strip():
        return ""
    if not GEMINI_API_KEY:
        return raw_text

    context_guidance = ""
    if context_prompt.strip():
        context_guidance += f"\nDomain Context:\n{context_prompt.strip()}\n"
    
    # Intrinsic product terms + user-supplied custom terms
    base_terms = "SoMeet, AI Speech Studio, Sub-second, private beta"
    effective_terms = f"{base_terms}, {terms.strip()}" if terms.strip() else base_terms
    context_guidance += f"\nPriority Terminology / Proper Nouns (ensure correct spelling and casing):\n{effective_terms}\n"

    prompt = (
        "You are the speech intelligence and punctuation engine for SoMeet.\n"
        "Below is raw acoustic text recognized from a user microphone:\n"
        f'"""{raw_text.strip()}"""\n'
        f"{context_guidance}\n"
        "Tasks:\n"
        "1. Restore standard punctuation (commas, periods, question marks).\n"
        "2. Fix obvious acoustic phonetic recognition slips (e.g., product names like 'Show me' or 'So meet' -> 'SoMeet', 'better sports' -> 'beta spots', 'Stop sucking' -> 'Sub-second', technical jargon, brand names, or proper nouns) using the domain context and terminology provided above.\n"
        "3. Preserve all words and sentences verbatim—do NOT summarize, truncate, or omit content.\n"
        "4. Output ONLY the clean, polished transcript text without any introductory commentary or quotes."
    )

    models_to_try = ["gemini-flash-lite-latest", "gemini-3.1-flash-lite"]
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.0}
    }

    for model in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
        try:
            resp = requests.post(url, json=payload, timeout=8)
            if resp.status_code == 200:
                text = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                return text.strip('"\'')
        except Exception as e:
            print(f"[Speech Polish Error with {model}]: {e}")
            continue

    return raw_text


def summarize_meeting(transcript: str, context_prompt: str = "") -> str:
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

    context_note = ""
    if context_prompt.strip():
        context_note = f"\nADDITIONAL CONTEXT & DOMAIN BACKGROUND:\n{context_prompt.strip()}\n"

    prompt = (
        "You are an executive intelligence assistant and chief of staff. "
        "Review the following spoken transcript and generate a structured, professional executive brief.\n\n"
        "TRANSCRIPT:\n"
        f"\"\"\"\n{transcript.strip()}\n\"\"\"\n"
        f"{context_note}\n"
        "Output format (strict markdown):\n"
        "### 📌 Executive Overview\n"
        "(A crisp 1-2 sentence executive overview diving directly into the core subject, key findings, and outcome. "
        "STRICT STYLE RULE: Use Subject-First phrasing. Do NOT use filler or meta labels—never start with or include "
        "'This meeting', 'The meeting', 'This session', 'The session', 'This recording', or 'The speaker'. "
        "State the subject and outcome directly, e.g., 'A framework for a 6-week intensive business finance curriculum was established...' "
        "or 'Functional verification of real-time speech transcription and in-place document editing confirmed responsive text manipulation.')\n\n"
        "### 🔑 Key Discussion Points\n"
        "- Bullet points capturing the core topics, points, and insights\n\n"
        "### 🎯 Decisions & Agreements\n"
        "- Concrete decisions, conclusions, or takeaways confirmed\n\n"
        "### 📋 Action Items & Next Steps\n"
        "- [ ] **[Owner/Task]** Clear, actionable task with intended outcome\n\n"
        "CRITICAL WRITING RULE:\n"
        "Do not refer to the interaction as a 'meeting', 'session', or 'call'. Present all information directly and authoritatively."
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
