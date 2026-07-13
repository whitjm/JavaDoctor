"""SQLAlchemy 引擎、会话、Base。"""
import os
from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import NullPool

from app.config import settings


class Base(DeclarativeBase):
    pass


# SQLite 需要 check_same_thread=False 以配合 FastAPI 多线程
connect_args = (
    {"check_same_thread": False}
    if settings.database_url.startswith("sqlite")
    else {}
)

# 确保 SQLite 文件所在目录存在
if settings.database_url.startswith("sqlite"):
    db_path = settings.database_url.replace("sqlite:///", "")
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)

# SQLite 多线程场景使用 NullPool：每次请求新建连接，避免 QueuePool 竞争。
# WAL 模式下建连极快（<1ms），NullPool 反而比连接池更适合写密集的嵌入式数据库。
engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    poolclass=NullPool,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


@event.listens_for(engine, "connect")
def _set_wal(dbapi_conn, _connection_record):
    """每个新连接自动开启 WAL + 优化同步级别 + 设置忙等待超时。"""
    dbapi_conn.execute("PRAGMA journal_mode=WAL")
    dbapi_conn.execute("PRAGMA synchronous=NORMAL")
    dbapi_conn.execute("PRAGMA busy_timeout=5000")


def get_db() -> Generator:
    """FastAPI 依赖：请求级数据库会话。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
