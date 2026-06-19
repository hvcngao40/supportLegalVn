from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional

class Citation(BaseModel):
    source: str = Field(..., description="Document number or title of the legal source")
    text: str = Field(..., description="Excerpt or snippet from the legal document")
    score: float = Field(..., description="Relevance score (RRF)")
    article_uuid: Optional[str] = Field(None, description="UUID of the canonical article")

class ChatMessage(BaseModel):
    role: str
    content: str

class AskRequest(BaseModel):
    query: str = Field(..., examples=["Thủ tục thành lập công ty TNHH"])
    chat_history: Optional[List[ChatMessage]] = Field(default_factory=list, description="Recent conversation history")

class AskResponse(BaseModel):
    answer: Optional[str] = Field(None, description="IRAC formatted response from the AI")
    citations: List[Citation] = Field(default_factory=list)
    retrievals: List[Citation] = Field(default_factory=list, description="Retrievals returned when LLM generation is disabled")
    status: Optional[str] = Field(None, description="Pipeline execution status")
    prompt: Optional[str] = Field(None, description="Pre-built prompt returned when LLM generation is disabled")
    metadata: Dict[str, Any] = Field(default_factory=dict)
    detected_domains: List[str] = Field(default_factory=list)
    confidence_score: float = 0.0

class HealthResponse(BaseModel):
    status: str
    service: str = "legal-api"
    version: str
    db_connected: bool
    qdrant_connected: bool


class ArticleResult(BaseModel):
    article_uuid: str
    doc_id: Optional[str] = None
    so_ky_hieu: Optional[str] = None
    title: Optional[str] = None
    score: float = 0.0
    full_content: str = ""
    doc_type: Optional[str] = None
    highlighted_content: Optional[str] = None


class SearchArticlesRequest(BaseModel):
    query: Optional[str] = None
    article_uuid: Optional[str] = None
    doc_type: Optional[str] = None
    top_k: Optional[int] = 10


class SearchArticlesResponse(BaseModel):
    query: str
    top_results_count: int
    results: List[ArticleResult]
    status: str

