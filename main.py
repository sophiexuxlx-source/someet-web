"""
SoMeet Web - FastAPI Server Application
Features:
- Sub-second real-time streaming speech-to-text over WebSocket (Faster-Whisper engine)
- Gemini Multimodal Fallback & Post-Meeting Structured Intelligence (/api/summarize)
- Firebase Auth Guarded endpoints & Early Adopter Perks
"""
import asyncio
from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from pathlib import Path
from auth import get_current_user
from asr_engine import transcribe_audio_base64, transcribe_pcm, summarize_meeting, get_whisper_model, polish_speech_transcript, format_smart_typography
from usage_service import get_user_usage, add_user_usage, save_capacity_request
from config import BASE_DIR

app = FastAPI(
    title="SoMeet",
    description="Real-Time Streaming Speech Studio with Local Acoustic Engine & Gemini Speech Intelligence",
    version="2.0.0"
)

STATIC_DIR = BASE_DIR / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class TranscribeRequest(BaseModel):
    audio_base64: str
    mime_type: str = "audio/webm"
    context: str = ""


class SummarizeRequest(BaseModel):
    transcript: str
    context_prompt: str = ""


class PolishRequest(BaseModel):
    transcript: str
    context_prompt: str = ""
    terms: str = ""


class RecordUsageRequest(BaseModel):
    seconds: int


class CapacityRequestModel(BaseModel):
    message: str = ""


@app.on_event("startup")
async def startup_warmup():
    """Pre-warms the local Whisper ASR model on startup so the first user interaction has zero lag."""
    try:
        asyncio.create_task(asyncio.to_thread(get_whisper_model))
    except Exception as e:
        print(f"[Startup] Prewarm failed: {e}")


@app.api_route("/", methods=["GET", "HEAD"])
async def get_index():
    """Serves the main SoMeet web interface."""
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/config")
async def get_public_config():
    """Returns safe public client configuration for Firebase Authentication."""
    from config import FIREBASE_PROJECT_ID, FIREBASE_WEB_API_KEY
    return {
        "firebase": {
            "apiKey": FIREBASE_WEB_API_KEY,
            "authDomain": f"{FIREBASE_PROJECT_ID}.firebaseapp.com",
            "projectId": FIREBASE_PROJECT_ID
        }
    }


@app.get("/api/user/me")
async def get_user_profile(user: dict = Depends(get_current_user)):
    """Returns the authenticated user details, quota, and remaining seconds."""
    uid = user.get("uid") or "guest"
    email = user.get("email") or ""
    usage_info = get_user_usage(uid, email)
    return {
        "status": "authenticated",
        "uid": uid,
        "email": email,
        "display_name": user.get("name") or user.get("display_name") or email.split("@")[0],
        **usage_info
    }


@app.post("/api/user/usage")
async def record_user_usage_endpoint(req: RecordUsageRequest, user: dict = Depends(get_current_user)):
    """Records consumed recording seconds and returns updated quota balance."""
    uid = user.get("uid") or "guest"
    email = user.get("email") or ""
    result = add_user_usage(uid, email, req.seconds)
    return result


@app.post("/api/user/request_capacity")
async def request_capacity_endpoint(req: CapacityRequestModel, user: dict = Depends(get_current_user)):
    """Stores a user's request for additional recording capacity."""
    uid = user.get("uid") or "guest"
    email = user.get("email") or ""
    return save_capacity_request(uid, email, req.message)


@app.get("/api/admin/requests")
async def get_admin_requests_endpoint(user: dict = Depends(get_current_user)):
    """Protected admin endpoint: returns all tester requests."""
    email = (user.get("email") or "").lower()
    if not (user.get("is_unlimited") or email == "sophiexuxlx@gmail.com"):
        raise HTTPException(status_code=403, detail="Founder access required")
    from usage_service import get_all_capacity_requests
    return {
        "success": True,
        "requests": get_all_capacity_requests()
    }


@app.delete("/api/admin/requests")
async def delete_admin_request_endpoint(timestamp: str, user: dict = Depends(get_current_user)):
    """Protected admin endpoint: deletes a processed tester request."""
    email = (user.get("email") or "").lower()
    if not (user.get("is_unlimited") or email == "sophiexuxlx@gmail.com"):
        raise HTTPException(status_code=403, detail="Founder access required")
    from usage_service import delete_capacity_request
    return delete_capacity_request(timestamp)



@app.websocket("/api/realtime/ws")
async def realtime_ws_endpoint(websocket: WebSocket):
    """
    Bidirectional real-time audio streaming endpoint with incremental O(1) sliding-window decoding.
    Receives raw 16kHz 16-bit PCM binary audio frames from browser Web Audio API / AudioWorklet.
    Streams back transcript deltas incrementally without re-transcribing historical audio.
    """
    await websocket.accept()
    await websocket.send_json({
        "type": "session_ready",
        "session_id": "someet-stream-live",
        "message": "Connected to real-time acoustic engine"
    })

    # Incremental sliding-window buffers (prevents O(n^2) computational explosion)
    committed_sentences: list[str] = []
    active_window_buffer = bytearray()
    full_session_buffer = bytearray()
    current_interim_text = ""
    is_transcribing = False
    session_initial_prompt = ""

    # Decode trigger: 1.5 seconds of new audio (48,000 bytes at 16kHz 16-bit mono)
    MIN_CHUNK_BYTES = 48000
    # Window cap: 6 seconds of audio (192,000 bytes). If buffer reaches this, commit and slide.
    MAX_WINDOW_BYTES = 192000
    # Overlap tail: 0.3s (9,600 bytes) preserved when sliding to avoid clipping phonemes across window boundary
    OVERLAP_BYTES = 9600

    def get_effective_prompt() -> str:
        recent_context = " ".join(committed_sentences[-3:]) if committed_sentences else ""
        if session_initial_prompt and recent_context:
            return f"{session_initial_prompt}. Context: {recent_context}"[-300:]
        return (session_initial_prompt or recent_context)[-300:]

    async def run_incremental_decode():
        nonlocal is_transcribing, current_interim_text
        if is_transcribing or len(active_window_buffer) < MIN_CHUNK_BYTES:
            return
        is_transcribing = True
        try:
            snapshot = bytes(active_window_buffer)
            prompt = get_effective_prompt()
            text = await asyncio.to_thread(transcribe_pcm, snapshot, None, prompt)
            clean_text = text.strip()

            if clean_text:
                current_interim_text = clean_text
                # If decoded text ends with sentence boundary (. ? !) or buffer exceeds MAX_WINDOW_BYTES
                is_sentence_end = clean_text[-1] in {'.', '?', '!', '。', '？', '！'}
                if is_sentence_end or len(active_window_buffer) >= MAX_WINDOW_BYTES:
                    committed_sentences.append(clean_text)
                    current_interim_text = ""
                    # Slide window forward, keeping a tiny overlap to protect phonemes
                    if len(active_window_buffer) > OVERLAP_BYTES:
                        tail = active_window_buffer[-OVERLAP_BYTES:]
                        active_window_buffer.clear()
                        active_window_buffer.extend(tail)
                    else:
                        active_window_buffer.clear()

                # Build full cumulative transcript to stream back to client
                full_parts = committed_sentences + ([current_interim_text] if current_interim_text else [])
                cumulative_text = " ".join(part for part in full_parts if part).strip()

                if cumulative_text:
                    clean_cum = format_smart_typography(cumulative_text)
                    await websocket.send_json({
                        "type": "transcript_delta",
                        "text": clean_cum
                    })
        except Exception as e:
            print(f"[WS Incremental Decode Error] {e}")
        finally:
            is_transcribing = False

    try:
        while True:
            message = await websocket.receive()
            if "bytes" in message and message["bytes"]:
                pcm_data = message["bytes"]
                active_window_buffer.extend(pcm_data)
                full_session_buffer.extend(pcm_data)
                # Trigger incremental decode when threshold is reached
                if not is_transcribing and len(active_window_buffer) >= MIN_CHUNK_BYTES:
                    asyncio.create_task(run_incremental_decode())

            elif "text" in message and message["text"]:
                import json
                try:
                    payload = json.loads(message["text"])
                    msg_type = payload.get("type")
                    if msg_type in ("commit", "stop"):
                        # Wait for any in-flight incremental decode to finish
                        while is_transcribing:
                            await asyncio.sleep(0.04)

                        final_full_text = ""
                        # Primary: seamless full session acoustic pass for unbroken sentence structure
                        if len(full_session_buffer) >= 3200:
                            prompt = get_effective_prompt()
                            full_pass_text = await asyncio.to_thread(transcribe_pcm, bytes(full_session_buffer), None, prompt)
                            if full_pass_text.strip():
                                final_full_text = full_pass_text.strip()

                        # Fallback to incremental committed sentences if full pass was empty
                        if not final_full_text:
                            if len(active_window_buffer) >= 3200:
                                prompt = get_effective_prompt()
                                final_slice_text = await asyncio.to_thread(transcribe_pcm, bytes(active_window_buffer), None, prompt)
                                if final_slice_text.strip():
                                    committed_sentences.append(final_slice_text.strip())
                            final_full_text = " ".join(committed_sentences).strip()

                        print(f"[WS Stop] Final session transcript: '{final_full_text}'")

                        if final_full_text:
                            final_full_text = format_smart_typography(final_full_text)
                            await websocket.send_json({
                                "type": "transcript_completed",
                                "text": final_full_text
                            })

                        await websocket.send_json({
                            "type": "turn_completed",
                            "text": final_full_text
                        })

                        # Reset session buffers cleanly
                        committed_sentences.clear()
                        active_window_buffer.clear()
                        full_session_buffer.clear()
                        current_interim_text = ""

                    elif msg_type == "start":
                        committed_sentences.clear()
                        active_window_buffer.clear()
                        full_session_buffer.clear()
                        current_interim_text = ""
                        c_prompt = payload.get("context_prompt", "") or ""
                        c_terms = payload.get("terms", "") or ""
                        session_initial_prompt = f"{c_prompt} {c_terms}".strip()
                        print(f"[WS Start] Audio stream initiated. Context prompt: '{session_initial_prompt}'")
                except Exception as e:
                    print(f"[WS Control] Error parsing control payload: {e}")
    except WebSocketDisconnect:
        print("[WS Info] Client disconnected normally")
    except Exception as e:
        print(f"[WS Error] {e}")


class ExportDocxRequest(BaseModel):
    title: str = "SoMeet Meeting Intelligence"
    date_str: str = ""
    speaker: str = ""
    summary_markdown: str = ""
    transcript_text: str = ""
    filename: str = "SoMeet_Summary.docx"


@app.post("/api/export/docx")
async def export_docx_endpoint(req: ExportDocxRequest):
    """
    Generates a professionally styled Microsoft Word (.docx) document for local download.
    """
    from fastapi.responses import StreamingResponse
    from export_service import generate_meeting_docx
    import io

    docx_bytes = generate_meeting_docx(
        title=req.title,
        date_str=req.date_str,
        speaker=req.speaker,
        summary_markdown=req.summary_markdown,
        transcript_text=req.transcript_text
    )

    return StreamingResponse(
        io.BytesIO(docx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{req.filename}"'}
    )


@app.post("/api/summarize")
async def summarize_endpoint(req: SummarizeRequest):
    """
    Generates structured executive meeting intelligence from raw transcript using Gemini.
    """
    if not req.transcript.strip():
        raise HTTPException(status_code=400, detail="Missing transcript")

    summary = await asyncio.to_thread(summarize_meeting, req.transcript, req.context_prompt)
    return {
        "success": True,
        "summary": summary
    }


@app.post("/api/polish")
async def polish_endpoint(req: PolishRequest):
    """
    Sub-second Gemini speech intelligence pass: restores punctuation, capitalization, and acoustic slips.
    """
    tmp_dir = BASE_DIR / "tmp"
    tmp_dir.mkdir(exist_ok=True)
    with open(tmp_dir / "polish_debug.log", "a", encoding="utf-8") as f:
        f.write(f"\n--- POLISH REQUEST ---\nINPUT: {req.transcript}\n")

    if not req.transcript.strip():
        return {"success": True, "polished_transcript": ""}

    polished = await asyncio.to_thread(polish_speech_transcript, req.transcript, req.context_prompt, req.terms)
    
    with open(tmp_dir / "polish_debug.log", "a", encoding="utf-8") as f:
        f.write(f"OUTPUT: {polished}\n")

    return {
        "success": True,
        "polished_transcript": polished
    }


@app.post("/api/transcribe")
async def transcribe_endpoint(
    req: TranscribeRequest,
    user: dict = Depends(get_current_user)
):
    """
    Protected REST Speech-to-Text endpoint fallback. Requires valid Firebase ID Token.
    Dual-engine: Gemini Multimodal primary + Faster-Whisper local acoustic fallback.
    """
    if not req.audio_base64:
        raise HTTPException(status_code=400, detail="Missing audio payload")

    import base64

    # 1. Primary: Gemini Multimodal STT
    transcript = await asyncio.to_thread(
        transcribe_audio_base64,
        b64_audio=req.audio_base64,
        mime_type=req.mime_type,
        context=req.context
    )

    # 2. Resilient Fallback: Local Faster-Whisper if Gemini returned empty
    engine_used = "Gemini Multimodal STT"
    if not transcript:
        try:
            raw_bytes = base64.b64decode(req.audio_base64)
            data_idx = raw_bytes.find(b"data")
            pcm_data = raw_bytes[data_idx + 8:] if data_idx != -1 else raw_bytes[44:]
            if len(pcm_data) >= 3200:
                print(f"[Transcribe Fallback] Falling back to local Faster-Whisper ({len(pcm_data)} bytes)...")
                transcript = await asyncio.to_thread(transcribe_pcm, pcm_data)
                engine_used = "Faster-Whisper Fallback"
        except Exception as e:
            print(f"[Transcribe Fallback Error] {e}")

    try:
        tmp_dir = BASE_DIR / "tmp"
        tmp_dir.mkdir(exist_ok=True)
        raw_wav = base64.b64decode(req.audio_base64)
        with open(tmp_dir / "last_recording.wav", "wb") as f:
            f.write(raw_wav)
        with open(tmp_dir / "transcribe_debug.log", "a", encoding="utf-8") as f:
            f.write(f"\n--- TRANSCRIBE REQUEST ({len(req.audio_base64)} b64 bytes) ---\n")
            f.write(f"ENGINE: {engine_used}\n")
            f.write(f"CONTEXT: {req.context}\n")
            f.write(f"RESULT: {transcript}\n")
    except Exception as log_err:
        print(f"[Log Error] {log_err}")

    return {
        "success": True,
        "transcript": transcript,
        "user_email": user.get("email")
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
