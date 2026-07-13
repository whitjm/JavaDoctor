"""文档 / 知识库管理请求响应模型。"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.document import DocumentStatus


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    file_type: str
    doc_type: str
    status: DocumentStatus
    chunk_count: int
    error_msg: str | None = None
    created_at: datetime


class PreviewChunksRequest(BaseModel):
    """分段预览调参。"""
    text: str
    chunk_size: int = Field(default=500, ge=100, le=2000)
    chunk_overlap: int = Field(default=50, ge=0, le=500)


class ChunkPreview(BaseModel):
    index: int
    content: str
    length: int


class VectorStats(BaseModel):
    collection: str
    vector_count: int
    document_count: int
