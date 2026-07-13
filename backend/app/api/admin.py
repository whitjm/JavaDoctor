"""知识库管理接口(仅 admin)。M3: 文档入库、删除、分段预览、向量统计。"""
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from app.config import settings
from app.core.deps import require_admin
from app.db.base import SessionLocal, get_db
from app.models.document import Document, DocumentStatus
from app.models.user import User
from app.rag import splitter, vectorstore
from app.schemas.document import (
    ChunkPreview,
    DocumentOut,
    PreviewChunksRequest,
    VectorStats,
)
from app.services import document as doc_service

router = APIRouter(prefix="/admin", tags=["admin"])


def _run_ingest(document_id: int) -> None:
    """后台任务:独立 DB 会话执行入库。"""
    db = SessionLocal()
    try:
        doc_service.ingest_document(db, document_id)
    except Exception:
        pass  # 状态已在 service 内置为 failed
    finally:
        db.close()


@router.get("/documents", response_model=list[DocumentOut])
def list_documents(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    return db.query(Document).order_by(Document.created_at.desc()).all()


@router.post("/documents", status_code=202, response_model=DocumentOut)
async def upload_document(
    background: BackgroundTasks,
    file: UploadFile,
    doc_type: str = Form("未分类"),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """上传文档 → 登记 → 后台异步入库(解析/分段/嵌入/写库)。"""
    content = await file.read()
    max_bytes = settings.max_upload_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"文件超过 {settings.max_upload_mb}MB 限制",
        )
    try:
        path, ext = doc_service.save_upload(content, file.filename)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))

    doc = Document(
        filename=file.filename,
        file_path=path,
        file_type=ext,
        doc_type=doc_type,
        status=DocumentStatus.parsing,
        uploaded_by=admin.id,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    background.add_task(_run_ingest, doc.id)
    return doc


@router.get("/documents/{document_id}", response_model=DocumentOut)
def get_document(
    document_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "文档不存在")
    return doc


@router.post("/documents/{document_id}/reindex", status_code=202, response_model=DocumentOut)
def reindex_document(
    document_id: int,
    background: BackgroundTasks,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """重新入库:先删旧向量,再重跑管线。"""
    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "文档不存在")
    vectorstore.delete_by_document(document_id)
    doc.status = DocumentStatus.parsing
    doc.error_msg = None
    db.commit()
    db.refresh(doc)
    background.add_task(_run_ingest, document_id)
    return doc


@router.delete("/documents/{document_id}", status_code=204)
def delete_document(
    document_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """删除文档 → 级联删向量 + 磁盘文件 + 关系库记录。"""
    ok = doc_service.delete_document(db, document_id)
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "文档不存在")


@router.post("/documents/preview-chunks", response_model=list[ChunkPreview])
def preview_chunks(
    req: PreviewChunksRequest,
    _: User = Depends(require_admin),
):
    """分段预览调参:对给定文本按参数分段并返回结果。"""
    subs = splitter.preview_split(req.text, req.chunk_size, req.chunk_overlap)
    return [
        ChunkPreview(index=i, content=s, length=len(s))
        for i, s in enumerate(subs)
    ]


@router.get("/vector/stats", response_model=VectorStats)
def vector_stats(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """向量库统计。"""
    doc_count = db.query(Document).count()
    return VectorStats(
        collection=settings.chroma_collection,
        vector_count=vectorstore.count_vectors(),
        document_count=doc_count,
    )
