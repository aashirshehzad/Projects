from typing import List, Optional

from pydantic import BaseModel, Field


class Message(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str = "llama-3.1-8b-instant"
    messages: List[Message]
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = None
    # OpenAI's standard end-user field doubles as the cache tenant key.
    user: Optional[str] = None


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ProxyResponse(BaseModel):
    source: str = Field(description='"CACHE_HIT" or "UPSTREAM_LLM"')
    latency_ms: float
    similarity_score: Optional[float] = None
    matched_query: Optional[str] = None
    response: str
    usage: Usage = Usage()
    # Tokens the caller did not pay for because the answer came from cache.
    tokens_saved: int = 0
