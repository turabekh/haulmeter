"""AI-CONTEXT: Public interface for M11 Voice Copilot & AI Communications.

The ONLY import surface other packages may use to reach M11 (import-linter
enforced). A schema-less serving layer: the intent router over the app's own
data (STT/TTS via F9), the motion-aware interaction policy, the English-out
comms ghostwriter, and the conversational claim assistant. Runs behind the F13
flag m11_voice.
"""

from .domain.service import (
    FLAG_KEY,
    GHOSTWRITER_PROMPT,
    INTENTS,
    MODULE,
    TONES,
    ClaimItem,
    VoiceResponse,
    approve_and_send,
    claim_assistant,
    classify_intent,
    draft_counterparty_message,
    handle_utterance,
    interaction_mode,
    register_module,
    route,
)

__all__ = [
    "FLAG_KEY",
    "GHOSTWRITER_PROMPT",
    "INTENTS",
    "MODULE",
    "TONES",
    "ClaimItem",
    "VoiceResponse",
    "approve_and_send",
    "claim_assistant",
    "classify_intent",
    "draft_counterparty_message",
    "handle_utterance",
    "interaction_mode",
    "register_module",
    "route",
]
