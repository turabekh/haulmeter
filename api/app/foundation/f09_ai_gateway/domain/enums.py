import enum


class AiTask(enum.Enum):
    document_parse = "document_parse"
    drafting = "drafting"
    embedding = "embedding"
    stt = "stt"
    tts = "tts"
    classify = "classify"
