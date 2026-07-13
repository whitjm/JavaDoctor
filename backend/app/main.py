"""FastAPI 应用入口。"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import admin, auth, chat, conversations
from app.config import settings
from app.core.cache import is_redis_available
from app.db.base import Base, engine
from app.seeds import seed_admin


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 开发期直接建表；生产用 Alembic 迁移
    Base.metadata.create_all(bind=engine)
    seed_admin()
    print(f"[startup] Redis: {'可用' if is_redis_available() else '降级为内存缓存'}")
    yield


app = FastAPI(
    title=settings.app_name,
    description="Java 面试企业级 RAG 知识库问答系统",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 路由注册
prefix = settings.api_prefix
app.include_router(auth.router, prefix=prefix)
app.include_router(conversations.router, prefix=prefix)
app.include_router(chat.router, prefix=prefix)
app.include_router(admin.router, prefix=prefix)


@app.get("/api/health")
def health():
    return {"status": "ok", "app": settings.app_name}
