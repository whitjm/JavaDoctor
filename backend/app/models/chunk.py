"""分段模型：关系库与向量库的桥梁。"""
from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)                      # 子块(检索用)
    parent_content: Mapped[str | None] = mapped_column(Text, nullable=True)  # 父块(喂模型)
    vector_id: Mapped[str | None] = mapped_column(String(64), nullable=True)  # 对应 Chroma 向量ID
    page_no: Mapped[int | None] = mapped_column(Integer, nullable=True)

    document: Mapped["Document"] = relationship(back_populates="chunks")
