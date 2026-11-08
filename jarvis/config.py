"""Settings: environment variables, optionally loaded from .env in the project root."""
import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("JARVIS_HOME", str(Path.home() / ".jarvis")))
DATA_DIR.mkdir(parents=True, exist_ok=True)


def _load_env():
    f = ROOT / ".env"
    if not f.exists():
        return
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip().strip('"').strip("'")
        if v:
            os.environ.setdefault(k.strip(), v)


_load_env()


def env(name, default=None):
    return os.environ.get(name, default)


# CLI table for run_coding_agent. Adjust to the versions you have installed.
CODING_CLIS = {
    "claude": {"headless": ["claude", "-p"], "interactive": ["claude"]},
    "codex": {"headless": ["codex", "exec"], "interactive": ["codex"]},
    "gemini": {"headless": ["gemini", "-p"], "interactive": ["gemini", "-i"]},
    "opencode": {"headless": ["opencode", "run"], "interactive": ["opencode", "--prompt"]},
}


@dataclass
class Settings:
    provider: str = env("JARVIS_PROVIDER", "anthropic").lower()
    anthropic_model: str = env("JARVIS_ANTHROPIC_MODEL", "claude-sonnet-5-5")
    ollama_url: str = env("OLLAMA_URL", "http://localhost:11434")
    ollama_model: str = env("JARVIS_OLLAMA_MODEL", "qwen2.5:7b")
    ollama_vision_model: str = env("JARVIS_OLLAMA_VISION_MODEL", "llava")
    # Any OpenAI-compatible endpoint (OmniRoute, LM Studio, vLLM, OpenAI...). Base URL includes /v1.
    openai_base_url: str = env("JARVIS_OPENAI_BASE_URL", "http://localhost:20128/v1")
    openai_key: str = env("JARVIS_OPENAI_KEY", "")
    openai_model: str = env("JARVIS_OPENAI_MODEL", "")
    openai_vision_model: str = env("JARVIS_OPENAI_VISION_MODEL", "")
    lite: str = env("JARVIS_LITE", "auto")  # auto = on for ollama/openai (small models cope badly with 50 tools)
    max_tokens: int = 700
    max_steps: int = 12
    history_limit: int = 30

    listen_mode: str = env("JARVIS_LISTEN_MODE", "wake").lower()  # wake | neural | always | hotkey
    wake_words: tuple = tuple(w.strip().lower() for w in env("JARVIS_WAKE_WORD", "jarvis,hey jarvis").split(",") if w.strip())
    wake_aliases: tuple = tuple(w.strip().lower() for w in env("JARVIS_WAKE_ALIASES", "garbage,gervais,जार्विस,जारविस,जर्विस,जारवि").split(",") if w.strip())
    wake_sensitivity: float = float(env("JARVIS_WAKE_SENSITIVITY", "0.6"))  # lower = more forgiving
    hotkey: str = env("JARVIS_HOTKEY", "f9")
    session_seconds: int = int(env("JARVIS_SESSION_SECONDS", "25"))
    whisper_model: str = env("JARVIS_WHISPER_MODEL", "small.en")
    whisper_device: str = env("JARVIS_WHISPER_DEVICE", "cpu")
    whisper_threads: int = int(env("JARVIS_WHISPER_THREADS", "0"))  # 0 = all CPU cores
    whisper_compute: str = env("JARVIS_WHISPER_COMPUTE", "int8")
    language: str = env("JARVIS_LANGUAGE", "en")
    mic_threshold: float = float(env("JARVIS_MIC_THRESHOLD", "0.012"))
    silence_seconds: float = float(env("JARVIS_SILENCE_SECONDS", "0.6"))
    tts_rate: int = int(env("JARVIS_TTS_RATE", "185"))
    tts_voice: str = env("JARVIS_TTS_VOICE", "")  # part of a voice name, see `python main.py --voices`
    stop_key: str = env("JARVIS_STOP_KEY", "f8")  # press to cut Jarvis off mid-sentence
    neural_model: str = env("JARVIS_NEURAL_MODEL", "hey_jarvis")  # openWakeWord model (listen mode "neural")
    neural_threshold: float = float(env("JARVIS_NEURAL_THRESHOLD", "0.5"))
    stream: bool = env("JARVIS_STREAM", "1") == "1"  # speak sentence by sentence while the model is still writing
    dashboard_port: int = int(env("JARVIS_DASHBOARD_PORT", "8765"))
    # --- languages ("en", "hi", or "auto" to detect English/Hindi/Hinglish per sentence) ---
    edge_voice_hi: str = env("JARVIS_EDGE_VOICE_HI", "hi-IN-MadhurNeural")
    # --- owner check: off | face | voice | either | both ---
    auth_mode: str = env("JARVIS_AUTH", "off").lower()
    auth_ttl: int = int(env("JARVIS_AUTH_TTL", "120"))  # seconds a successful check stays valid
    face_threshold: float = float(env("JARVIS_FACE_THRESHOLD", "0.363"))
    voice_threshold: float = float(env("JARVIS_VOICE_THRESHOLD", "0.75"))
    # --- screen vision ---
    vision_width: int = int(env("JARVIS_VISION_WIDTH", "0"))  # 0 = 1024 for local models, 1280 for cloud
    tts_enabled: bool = True

    workspace: Path = Path(env("JARVIS_WORKSPACE", str(Path.home())))
    auto_approve: set = field(default_factory=lambda: {
        x.strip() for x in env("JARVIS_AUTO_APPROVE", "").split(",") if x.strip()})
    browser_headless: bool = env("JARVIS_BROWSER_HEADLESS", "0") == "1"


SETTINGS = Settings()
