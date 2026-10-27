# SoMeet — Architecture Overview

![SoMeet Architecture Overview](file:///C:/AgentSpace/Projects/SoMeet/SoMeet_Web/static/someet_ascii_architecture_overview.png)

---

### Updated ASCII Architecture Diagram

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                        LAYER 1: CLIENT RUNTIME                              │
│       Modern Web Audio SPA (Vanilla JS · HTML5 AudioContext · WSS)          │
│                                                                             │
│ • Ingestion: AudioContext → 16kHz PCM16 Downsampling (AudioWorklet Thread) │
│ • Local Export: RIFF/WAV in-browser · Word (.docx) via /api/export/docx     │
│ • Companion UI: Mascot avatar record button & Almond Mochi responsive theme │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ WSS / HTTPS (PCM16 Audio Chunks)
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    LAYER 2: FASTAPI BACKEND GATEWAY                         │
│                      Uvicorn · Python 3.12 Runtime                          │
├──────────────────────────────┬──────────────────────────────┬───────────────┤
│    WebSocket Live Stream     │     Executive Summary API    │ Identity &    │
│     (/api/realtime/ws)       │      (/api/summarize)        │ Quota Engine  │
│  Incremental sliding-window  │  Text-only transcript input  │ 120-min quota │
│  Zero server audio storage   │  Zero server audio storage   │ Whitelist mode│
└──────────────┬───────────────┴──────────────┬───────────────┴───────┬───────┘
               │                              │                       │
      Sub-second live audio          Post-speech transcript     Auth & Usage
               │                              │                       │
               ▼                              ▼                       ▼
┌──────────────────────────────┐┌──────────────────────────────┐┌─────────────┐
│      ACOUSTIC STREAMING      ││     AI EXECUTIVE SUMMARY     ││  FIREBASE   │
│ Web Speech API + Whisper int8││    Google Gemini Flash-Lite  ││    AUTH     │
│                              ││                              ││             │
│ • Sub-second client captions ││ • Executive Overview & Points││ • User Auth │
│ • Interim text self-correct  ││ • Decisions & Action Items   ││ • Quota sync│
│ • Local Faster-Whisper Tiny  ││ • Strict zero-data retention ││ • Whitelist │
└──────────────────────────────┘└──────────────────────────────┘└─────────────┘
```

---

### Visual Card & Graphic Links

* **Visual HTML Card**: [static/architecture_card.html](file:///C:/AgentSpace/Projects/SoMeet/SoMeet_Web/static/architecture_card.html)
* **High-Res Graphic PNG**: [static/someet_architecture_overview.png](file:///C:/AgentSpace/Projects/SoMeet/SoMeet_Web/static/someet_architecture_overview.png)
