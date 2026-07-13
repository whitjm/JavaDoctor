# JavaDoctor · Java 面试企业级 RAG 知识库问答系统

基于 LangChain 的 RAG 知识库问答系统，面向 Java 面试场景。管理员维护知识库，用户在线问答，回答强制引用知识库原文并展示来源。

详细设计见 [docs/设计文档.md](docs/设计文档.md)。

## 技术栈

| 层 | 选型 |
|---|---|
| 大模型 | Ollama + qwen3:4b |
| 嵌入 | bge-m3 |
| RAG | LangChain + langchain-community |
| 后端 | FastAPI (Python) |
| 前端 | React18 + TypeScript + Vite + Ant Design 5 + Zustand |
| 向量库 | ChromaDB |
| 关系库 | SQLite (可切 PostgreSQL) + SQLAlchemy 2.0 + Alembic |
| 缓存 | Redis (可选，未装自动降级内存) |
| 认证 | JWT + bcrypt |

## 环境准备（一次性）

1. **Python 3.11+**，安装后端依赖：
   ```bash
   cd backend
   pip install -r requirements.txt
   ```
2. **Node.js 18+**，安装前端依赖：
   ```bash
   cd frontend
   npm install
   ```
3. **Ollama**：安装后拉取模型
   ```bash
   ollama pull qwen3:4b
   ```
4. **Redis**（可选）：未安装时后端自动降级为内存缓存。

## 启动

双击项目根目录的 `start.bat`，会依次启动 Ollama、后端(8000)、前端(5173)并打开浏览器。

停止服务运行 `stop.bat`。

- 前端：http://localhost:5173
- 后端 API 文档：http://localhost:8000/docs
- 超级管理员：`admin` / `123456`
