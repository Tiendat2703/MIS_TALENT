"""AI Core Configuration — single source of truth for keys & env vars."""

from __future__ import annotations

import os
from pathlib import Path
from openai import AsyncOpenAI, OpenAI
from dotenv import load_dotenv
_ROOT_DIR = Path(__file__).resolve().parents[2]
_WORKSPACE_DIR = _ROOT_DIR.parent

load_dotenv(_ROOT_DIR / ".env")

AGENT_DOCUMENT_TEXT_LIMIT = int(os.getenv("AGENT_DOCUMENT_TEXT_LIMIT", "12000"))

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.2-2025-12-11")
OPENAI_TEMPERATURE = float(os.getenv("OPENAI_TEMPERATURE", "0.7"))
OPENAI_MAX_TOKENS = int(os.getenv("OPENAI_MAX_TOKENS", "2048"))
OPENAI_CLIENT = AsyncOpenAI(api_key=OPENAI_API_KEY)



