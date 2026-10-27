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
from asr_engine import transcribe_audio_base64, transcribe_pcm, summarize_meeting, get_whisper_model, polish_speech_transcript
from usage_service import get_user_usage, add_user_usage, save_capacity_request
from config import BASE_DIR

app = FastAPI(
    title="SoMeet",
    description="Real-Time Streaming Speech Studio with Local Acoustic Engine & Gemini Meeting Intelligence",
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


@app.websocket("/api/realtime/ws")
async def realtime_ws_endpoint(websocket: WebSocket):
    """
    Bidirectional real-time audio streaming endpoint.
    Receives raw 16kHz 16-bit PCM binary audio frames from browser Web Audio API.
    Streams back transcript deltas cleanly without queuing latency.
    """
    await websocket.accept()
    await websocket.send_json({
        "type": "session_ready",
        "session_id": "someet-stream-live",
        "message": "Connected to real-time acoustic engine"
    })

    pcm_buffer = bytearray()
    last_transcribed_text = ""
    is_transcribing = False
    last_transcribe_len = 0
    session_initial_prompt = ""
    # Transcribe when we accumulate at least 1.5 seconds of new audio (48000 bytes)
    MIN_CHUNK_BYTES = 48000

    async def run_live_decode():
        nonlocal is_transcribing, last_transcribed_text, last_transcribe_len
        if is_transcribing or len(pcm_buffer) - last_transcribe_len < MIN_CHUNK_BYTES:
            return
        is_transcribing = True
        try:
            snapshot = bytes(pcm_buffer)
            last_transcribe_len = len(snapshot)
            text = await asyncio.to_thread(transcribe_pcm, snapshot, None, session_initial_prompt)
            if text and text != last_transcribed_text:
                last_transcribed_text = text
                await websocket.send_json({
                    "type": "transcript_delta",
                    "text": text
                })
        except Exception as e:
            print(f"[WS Decode Error] {e}")
        finally:
            is_transcribing = False

    try:
        while True:
            message = await websocket.receive()
            if "bytes" in message and message["bytes"]:
                pcm_data = message["bytes"]
                pcm_buffer.extend(pcm_data)
                # Periodically trigger background transcription
                if not is_transcribing and (len(pcm_buffer) - last_transcribe_len) >= MIN_CHUNK_BYTES:
                    asyncio.create_task(run_live_decode())

            elif "text" in message and message["text"]:
                import json
                try:
                    payload = json.loads(message["text"])
                    msg_type = payload.get("type")
                    if msg_type in ("commit", "stop"):
                        # Wait for any in-flight decode to finish, then decode final audio
                        while is_transcribing:
                            await asyncio.sleep(0.05)
                        
                        final_text = ""
                        if len(pcm_buffer) >= 3200: # at least 100ms
                            print(f"[WS Stop] Final decoding of {len(pcm_buffer)} audio bytes...")
                            final_text = await asyncio.to_thread(transcribe_pcm, bytes(pcm_buffer), None, session_initial_prompt)
                            print(f"[WS Stop] Final transcribed text: '{final_text}'")

                        if len(final_text) < len(last_transcribed_text):
                            final_text = last_transcribed_text
                            print(f"[WS Stop] Using last_transcribed_text (longer): '{final_text}'")

                        if final_text:
                            await websocket.send_json({
                                "type": "transcript_completed",
                                "text": final_text
                            })
                        
                        await websocket.send_json({
                            "type": "turn_completed",
                            "text": final_text
                        })
                        pcm_buffer.clear()
                        last_transcribe_len = 0
                        last_transcribed_text = ""
                    elif msg_type == "start":
                        pcm_buffer.clear()
                        last_transcribe_len = 0
                        last_transcribed_text = ""
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
    if not req.transcript.strip():
        return {"success": True, "polished_transcript": ""}

    polished = await asyncio.to_thread(polish_speech_transcript, req.transcript, req.context_prompt, req.terms)
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
    if not transcript:
        try:
            raw_bytes = base64.b64decode(req.audio_base64)
            data_idx = raw_bytes.find(b"data")
            pcm_data = raw_bytes[data_idx + 8:] if data_idx != -1 else raw_bytes[44:]
            if len(pcm_data) >= 3200:
                print(f"[Transcribe Fallback] Falling back to local Faster-Whisper ({len(pcm_data)} bytes)...")
                transcript = await asyncio.to_thread(transcribe_pcm, pcm_data)
        except Exception as e:
            print(f"[Transcribe Fallback Error] {e}")

    return {
        "success": True,
        "transcript": transcript,
        "user_email": user.get("email")
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
