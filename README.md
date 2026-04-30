# Tarot AI Backend

A FastAPI + MCP (Model Context Protocol) backend for a Myanmar Tarot reading platform. It exposes a REST/WebSocket API for the frontend and an MCP server for AI agent tool access.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                    server.py                        │
│  FastAPI app (REST + WebSocket)  +  MCP HTTP mount  │
└────────────────┬────────────────────────────────────┘
                 │
    ┌────────────┴────────────┐
    │                         │
┌───▼──────────┐   ┌──────────▼──────────┐
│  bridge.py   │   │  mcp_app/agent/     │
│  REST routes │   │  Anthropic / Google │
│  WebSocket   │   │  Groq / Gemini      │
│  TTS / Voice │   └─────────────────────┘
└──────────────┘
         │
┌────────▼────────────────────────────────────────────┐
│                  mcp_app/mcp_tools/                 │
│  order · discount · coupon · category · package     │
│  report · analyise · admin · logs                   │
└─────────────────────────────────────────────────────┘
         │
┌────────▼──────────┐
│  MySQL (pooled)   │
└───────────────────┘
```

- **`server.py`** — single entry point; mounts the FastAPI app and the MCP HTTP server at `/mcp`.
- **`bridge.py`** — all REST routes and the WebSocket handler (auth, chat, voice, TTS, dashboard, reply).
- **`main.py`** — MCP stdio entry point (for running the MCP server standalone via `stdio` transport).
- **`mcp_app/agent/`** — AI agent implementations (Anthropic Claude primary, Google Gemini fallback).
- **`mcp_app/mcp_tools/`** — MCP tool definitions exposed to the AI agents.
- **`mcp_app/knowledge/`** — ChromaDB vector store for RAG (retrieval-augmented generation).

---

## Requirements

- Python 3.12+
- MySQL database
- `ffmpeg` (for voice transcription PCM conversion)
- AWS credentials (for Amazon Transcribe streaming)
- API keys: Anthropic, Google Gemini, Groq, OpenAI (optional)

---

## Setup

### 1. Install dependencies

```bash
# Using uv (recommended)
uv sync

# Or pip
pip install -e .
```

### 2. Configure environment

Copy and fill in `.env`:

```env
# App
PROJECT_NAME=TarotAI

# Database
DB_HOST=localhost
DB_PORT=3306
DB_USERNAME=root
DB_PASSWORD=secret
DB_DATABASE=tarot_db
DB_POOL_SIZE=15

# Auth
TOKEN_TTL_DAYS=30

# AI providers
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=...
GROQ_API_KEY=...
OPENAI_API_KEY=...

# AWS (for voice transcription)
AWS_REGION=ap-southeast-1
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...

# CORS
ALLOWED_ORIGINS=http://localhost:3000,https://yourdomain.com

# Storage
MAX_UPLOAD_MB=10
VOICE_TTL_DAYS=30

# MCP internal secret (optional)
MCP_INTERNAL_SECRET=
```

### 3. Run the server

```bash
uvicorn server:app --host 0.0.0.0 --port 8000 --reload
```

### 4. Run MCP server standalone (stdio transport)

```bash
python main.py
```

---

## API Reference

All routes are prefixed with `/api`. Protected routes require a Bearer token in the `Authorization` header.

### Authentication

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/api/auth/login` | No | Login with email/password. Returns `token` and `user`. Rate limited: 10/min. |
| `GET` | `/api/auth/me` | Yes | Returns current authenticated user. |
| `POST` | `/api/auth/get-conversation` | Yes | Load chat history for a session. Body: `{ "chat_session_id": int }` |

**Login request:**
```json
{ "email": "user@example.com", "password": "secret" }
```

**Login response:**
```json
{ "token": "1|abc123...", "user": { "id": 1, "name": "Admin" } }
```

---

### WebSocket Chat

**Endpoint:** `ws://host/api/ws`

Connect and send JSON messages.

**Step 1 — Authenticate (first message after connect):**
```json
{ "token": "1|abc123...", "session_id": 42 }
```
Omit `session_id` to start a new session.

**Server response:**
```json
{ "event": "connected", "user_id": 1, "session_id": 42 }
```

**Step 2 — Send a message:**
```json
{ "message": "Show me today's orders", "session_id": 42 }
```

**Server events:**

| Event | Payload | Description |
|-------|---------|-------------|
| `typing` | — | Agent is processing |
| `status` | `{ "content": "..." }` | Tool execution status update |
| `stream` | `{ "content": "..." }` | Streamed response chunk |
| `stream_end` | `{ "content": "...", "session_id": int }` | Full response complete |
| `session_created` | `{ "session_id": int, "title": "..." }` | New session auto-created |
| `session_switched` | `{ "session_id": int }` | Session switch confirmed |
| `file_download` | `{ "filename": "...", "data": "..." }` | Report file ready |
| `error` | `{ "message": "..." }` | Error (e.g. Unauthorized) |

**Special payloads:**
```json
{ "new_chat": true }                        // Start a fresh session
{ "switch_session": 55 }                    // Switch to session 55
{ "message": "...", "voice_stored": true }  // Skip duplicate DB store (voice flow)
```

---

### Voice Transcription

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/api/transcribe` | Yes | Upload audio, transcribe (Myanmar), save to session. Rate limited: 30/min. |

**Form data:**
- `audio` — `.webm` audio file (max `MAX_UPLOAD_MB`)
- `session_id` — (optional) existing session ID; creates new session if 0

**Response:**
```json
{ "text": "transcribed text", "voice_file": "uuid.webm", "session_id": 42 }
```

Voice files are served statically at `/storage/voice/<filename>` and auto-deleted after `VOICE_TTL_DAYS`.

---

### Text-to-Speech

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/api/tts` | Yes | Convert text to MP3 audio using edge-tts. |

**Request:**
```json
{ "text": "မင်္ဂလာပါ", "voice": "my-MM-ThihaNeural" }
```

Returns `audio/mpeg` stream. Results are cached in-memory (50 MB cap).

---

### Dashboard

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/api/dashboard` | Yes | KPIs, revenue trend, category breakdown, pending orders. |

**Response shape:**
```json
{
  "kpi": {
    "today_orders": 12,
    "today_revenue": 150000,
    "today_pending": 3,
    "month_revenue": 2400000,
    "month_orders": 85,
    "conversion": 72.5,
    "unreplied": 4,
    "revenue_change": 12.3
  },
  "revenue_trend": [{ "day": "2026-04-01", "revenue": 80000, "orders": 5 }],
  "categories": [{ "category": "Love", "total": 30, "completed": 22, "revenue": 660000 }],
  "pending_list": [{ "ref": "PKTR-001", "customer": "...", "hours": 26 }]
}
```

---

### Reply to Order

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `POST` | `/api/reply` | Yes | Submit a tarot reading reply for a paid order. Marks order as `complete`. |

**Request:**
```json
{ "order_ref": "PKTR-001", "answer": "Your reading result..." }
```

---

### Health Check

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| `GET` | `/health` | No | Returns agent status and loaded MCP tools. |

---

## MCP Tools

The AI agent has access to the following tool modules. Each module registers tools with the FastMCP server.

| Module | Tools |
|--------|-------|
| `order` | List, view, update, and manage tarot orders |
| `discount` | Create, list, and manage discounts |
| `coupon` | Create and manage coupon codes |
| `category` | List and manage reading categories |
| `package` | List reading packages |
| `report` | Generate sales and order reports (downloadable) |
| `analyise` | Analyse order and revenue data |
| `admin` | Admin utilities |
| `logs` | View backend logs |

Tools are permission-gated. The `set_user_context` tool must be called first (in stdio mode) to establish the user identity for permission checks.

---

## AI Agents

| Agent | File | Notes |
|-------|------|-------|
| Anthropic Claude | `mcp_app/agent/antropic.py` | Primary agent, streaming |
| Google Gemini | `mcp_app/agent/google_agent.py` | Fallback when Anthropic is overloaded |
| Groq | `mcp_app/agent/groq_agent.py` | Alternative |
| Gemini (simple) | `mcp_app/agent/gemini_agent.py` | Lightweight Gemini wrapper |
| Claude (simple) | `mcp_app/agent/claude_agent.py` | Lightweight Claude wrapper |

The system automatically falls back from Anthropic to Google Gemini when the response contains the overload indicator (`အလုပ်များနေပါသည်`).

---

## Project Structure

```
tarot-ai-backend/
├── server.py                  # Main entry point (FastAPI + MCP HTTP)
├── main.py                    # MCP stdio entry point
├── bridge.py                  # REST routes, WebSocket, TTS, voice
├── pyproject.toml
├── mcp_app/
│   ├── core.py                # FastMCP instance
│   ├── db.py                  # MySQL connection pool
│   ├── auth.py                # Login, token generation/verification
│   ├── permission.py          # Role/permission checks (per-request context)
│   ├── websocket.py           # WebSocket handler
│   ├── conversation.py        # In-memory LRU session cache + DB persistence
│   ├── logger.py              # Logging setup
│   ├── agent/
│   │   ├── __init__.py        # Agent factory + handle_message_stream
│   │   ├── antropic.py        # Anthropic Claude agent
│   │   ├── google_agent.py    # Google Gemini agent
│   │   ├── groq_agent.py      # Groq agent
│   │   ├── system_prompt.py   # System prompt builder
│   │   ├── myanmar_holidays.py
│   │   └── host.py            # Internal FastAPI agent host
│   ├── mcp_tools/
│   │   ├── order.py
│   │   ├── discount.py
│   │   ├── coupon.py
│   │   ├── category.py
│   │   ├── package.py
│   │   ├── report.py
│   │   ├── analyise.py
│   │   ├── admin.py
│   │   └── logs.py
│   ├── models/
│   │   ├── base_model.py
│   │   ├── order_model.py
│   │   ├── coupon_model.py
│   │   ├── discount_model.py
│   │   ├── category_model.py
│   │   ├── package_model.py
│   │   └── chat_session.py
│   ├── repository/
│   │   ├── category_repository.py
│   │   ├── coupon_repository.py
│   │   └── discount_repository.py
│   └── knowledge/
│       ├── store.py           # ChromaDB vector store
│       ├── content_builder.py
│       └── seed.py            # Knowledge base seeding
└── storage/
    └── voice/                 # Uploaded voice files (auto-cleaned)
```

---

## Notes

- **Permissions** are checked in real-time from the database on every tool call — no stale cache for security-sensitive checks.
- **Token auth** uses a Sanctum-compatible `personal_access_tokens` table. Tokens expire after `TOKEN_TTL_DAYS` days.
- **Conversation history** is cached in an in-memory LRU (200 sessions max) and persisted to `chat_messages` in MySQL.
- **CORS** origins are configured via the `ALLOWED_ORIGINS` environment variable.
- **Rate limiting** is applied via `slowapi`: login (10/min), transcribe (30/min).
