# SoMeet — Architecture Overview

![SoMeet Architecture Overview](file:///C:/AgentSpace/Projects/SoMeet/SoMeet%20v2/static/someet_ascii_architecture_overview.png)

---

### Updated ASCII Architecture Diagram

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                        LAYER 1: CLIENT RUNTIME                              │
│       Modern Web Audio SPA (Vanilla JS · HTML5 AudioContext · WSS)          │
│                                                                             │
│ • Ingestion: AudioContext → 16kHz PCM16 Downsampling (AudioWorklet Thread) │
│ • Clean Speech: Smart Typography & Automated Disfluency / Filler Filtering  │
│ • Local Export: RIFF/WAV in-browser · Word (.docx) via /api/export/docx     │
│ • Companion UI: Mascot avatar record button & Almond Mochi responsive theme │
│ • Instant Auth: 0ms Synchronous Head Firebase Init & Persistent Session     │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ WSS / HTTPS (PCM16 Audio & WAV)
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    LAYER 2: FASTAPI BACKEND GATEWAY                         │
│                      Uvicorn · Python 3.12 Runtime                          │
├──────────────────────────────┬──────────────────────────────┬───────────────┤
│    WebSocket & Gemini STT    │     Executive Summary API    │ Identity &    │
│    (/api/transcribe & /ws)   │      (/api/summarize)        │ Admin Inbox   │
│  Gemini Multimodal Primary   │  Text-only transcript input  │ 120-min quota │
│  Faster-Whisper int8 Fallback│  Zero server audio storage   │ Founder Inbox │
└──────────────┬───────────────┴──────────────┬───────────────┴───────┬───────┘
               │                              │                       │
      Sub-second live audio          Post-speech transcript     Auth & Admin
               │                              │                       │
               ▼                              ▼                       ▼
┌──────────────────────────────┐┌──────────────────────────────┐┌─────────────┐
│      ACOUSTIC & STT PIPELINE ││     AI EXECUTIVE SUMMARY     ││  FIREBASE   │
│ Gemini 3.5 Flash-Lite Primary││    Google Gemini Flash-Lite  ││    AUTH     │
│  + Faster-Whisper int8 backup││                              ││             │
│ • Real-time live captioning  ││ • Executive Overview & Points││ • User Auth │
│ • Pristine speech STT decode ││ • Decisions & Action Items   ││ • Quota sync│
│ • Vocal filler word filtering││ • Strict zero-data retention ││ • Whitelist │
└──────────────────────────────┘└──────────────────────────────┘└─────────────┘
```

---

### Visual Card & Graphic Links

* **Visual HTML Card**: [static/architecture_card.html](file:///C:/AgentSpace/Projects/SoMeet/SoMeet%20v2/static/architecture_card.html)
* **High-Res Graphic PNG**: [static/someet_architecture_overview.png](file:///C:/AgentSpace/Projects/SoMeet/SoMeet%20v2/static/someet_architecture_overview.png)
* **ASCII Graphic PNG**: [static/someet_ascii_architecture_overview.png](file:///C:/AgentSpace/Projects/SoMeet/SoMeet%20v2/static/someet_ascii_architecture_overview.png)
