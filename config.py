import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env", override=True)

ASSEMBLYAI_API_KEY = os.getenv("ASSEMBLYAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
AI_PROVIDER = os.getenv("AI_PROVIDER", "anthropic")  # "anthropic" or "openai"

OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

CLAUDE_MODEL = "claude-sonnet-4-6"
OPENAI_MODEL = "gpt-4o"

if not ASSEMBLYAI_API_KEY:
    raise EnvironmentError("ASSEMBLYAI_API_KEY not set in .env")

if AI_PROVIDER == "anthropic" and not ANTHROPIC_API_KEY:
    raise EnvironmentError(
        "ANTHROPIC_API_KEY not set in .env\n"
        "Get one at: https://platform.claude.com/settings/api-keys"
    )

if AI_PROVIDER == "openai" and not OPENAI_API_KEY:
    raise EnvironmentError("OPENAI_API_KEY not set in .env")
