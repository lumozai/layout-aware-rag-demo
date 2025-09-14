from pydantic import BaseModel
from typing import List, Optional, Dict, Any


class ChunkData(BaseModel):
    id: str
    text: str
    page_num: int
    bbox: List[float]  # [x0, y0, x1, y1] as per article
    headings: List[str]
    embedding: Optional[List[float]] = None  # 768 dimensions


class DocumentMeta(BaseModel):
    id: str
    title: str
    source_uri: str
    family: str = "general"


class PageMeta(BaseModel):
    docId: str  # matches article schema
    page_num: int
    width: float
    height: float


class QueryRequest(BaseModel):
    query: str
    doc_type: Optional[str] = "general"
    k: int = 10
    limit: int = 5


class QueryResult(BaseModel):
    chunk: Dict[str, Any]
    doc: Dict[str, Any]
    page: int
    score: float


class QueryResponse(BaseModel):
    answer: str
    chunks: List[QueryResult]
    cited_chunks: Dict[str, Dict[str, Any]]