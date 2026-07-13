"""应用配置：从环境变量 / .env 读取。"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # 应用
    app_name: str = "JavaDoctor"
    debug: bool = True
    api_prefix: str = "/api"

    # 安全 / JWT
    secret_key: str = "change-me"
    access_token_expire_minutes: int = 1440
    algorithm: str = "HS256"

    # 数据库
    database_url: str = "sqlite:///./data/javadoctor.db"

    # Redis (可选)
    redis_url: str = ""

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    llm_model: str = "qwen3.5:4b"

    # 嵌入 (走 Ollama, 与 LLM 共用服务)
    embedding_model: str = "bge-m3"

    # ChromaDB
    chroma_dir: str = "./data/chroma"
    chroma_collection: str = "java_interview"

    # 上传
    upload_dir: str = "./data/uploads"
    max_upload_mb: int = 50

    # 管理员
    admin_username: str = "admin"
    admin_password: str = "123456"

    # CORS
    cors_origins: str = "http://localhost:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
