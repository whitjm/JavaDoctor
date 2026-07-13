# JavaDoctor 压力测试方案 — 100 并发用户模拟

## 1. 系统架构梳理

| 组件 | 技术 | 关键特征 |
|------|------|----------|
| Web 框架 | FastAPI + uvicorn | 单进程，无 workers 配置 |
| 数据库 | SQLite | 单文件，`check_same_thread=False`，未开 WAL |
| 向量库 | ChromaDB 嵌入式 | 本地持久化，底层也是 SQLite |
| LLM | Ollama qwen3.5:4b | 本地 GPU，单卡串行推理 |
| Embedding | Ollama bge-m3 | 与 LLM 共用 GPU，检索时调用 |
| 混合检索 | BM25 (内存) | 进程内单例，有锁 |
| 缓存 | 内存 dict | 无 Redis，仅用于 JWT 黑名单 |
| 认证 | JWT HS256 + bcrypt | 每次请求验签 |

## 2. 瓶颈预判（按严重程度排序）

### 🔴 P0 — Ollama LLM（致命瓶颈）
- qwen3.5:4b 在单 GPU 上一次只能推理 **1 条** 请求
- 每条技术问答耗时 **5~30 秒**（检索 + prompt 编码 + 生成 2048 token）
- **100 人同时提问 = 第 100 人排队等 500~3000 秒**
- Ollama 内部有请求队列，但无超时机制，排到一半断开就白排

### 🔴 P1 — Ollama Embeddings（重度瓶颈）
- 每次检索调用 `bge-m3` 做 1 次 query embedding
- 100 并发检索 → 100 个 embedding 请求同时打到 Ollama
- 与 LLM 抢同一张 GPU，互相拖慢

### 🟡 P2 — SQLite 写锁争用
- `/chat/{id}` 每次落库 **2 条 INSERT**（user message + assistant message）
- SQLite 同一时刻只允许一个写事务，其余排队
- 100 并发 = 200 条 INSERT 串行化

### 🟡 P3 — BM25 索引锁
- 首次检索触发全量重建（`build()` 查全表 + jieba 分词），有 `threading.Lock`
- 一旦建完就是纯读，影响小

### 🟢 P4 — JWT 黑名单内存缓存
- 登出时写入，验签时查一次。压力测试期间不登出就无影响

## 3. 测试工具选型

**推荐: Locust**（Python 生态，写脚本灵活，Web UI 实时看曲线）

```bash
pip install locust
```

备选：k6（性能更好但 Go 脚本，不适合模拟 SSE 流式场景）

## 4. 测试场景设计

### 场景 A：健康检查（基准吞吐）
```
GET /api/health
```
- 目的：测裸 FastAPI 极限 QPS（无 DB/LLM）
- 预期：500~2000 QPS（单进程 uvicorn）

### 场景 B：登录（认证链）
```
POST /api/auth/login  → bcrypt 验密 + JWT 签发
```
- 目的：测 bcrypt CPU 开销 + SQLite 读
- 预期：50~150 QPS

### 场景 C：会话 CRUD（纯 DB 读写）
```
GET    /api/conversations         列表查询
POST   /api/conversations         新建会话
GET    /api/conversations/{id}/messages  历史消息
DELETE /api/conversations/{id}    删除会话
```
- 目的：测 SQLite 并发读写极限
- 预期：200~500 QPS（读），100~200 QPS（写）

### 场景 D：闲聊问答（Intent Router 直答，不走检索）
```
POST /api/chat/{id}  {"question": "你好"}
```
- 路径：意图路由 → chitchat → 纯 LLM 流式生成
- **耗时 = LLM 推理时间**（5~10 秒/条）
- 目的：测纯 LLM 排队长度

### 场景 E：技术问答（完整 RAG 链路）⭐ 核心
```
POST /api/chat/{id}  {"question": "Java 双亲委派模型是什么"}
```
- 完整链路：检索(Chroma+BM25+RRF) → prompt 组装 → LLM 流式生成 → 落库
- **耗时 = 检索(~2s) + LLM(~15~25s)**
- 这是 100 人真实使用场景

### 场景 F：混合负载（模拟真实）
```
70% 场景E (技术问答) + 20% 场景D (闲聊) + 10% 场景C (会话操作)
```
- 最接近真实 100 人在线

## 5. 测试策略

> ⚠️ **重要前提**：当前架构 **不可能** 100 人同时按下发送键并在合理时间内得到回复。真实场景中 100 在线 ≠ 100 同时提问。

| 阶段 | 策略 | 并发数 | 持续时间 |
|------|------|--------|----------|
| **预热** | 1 用户循环发 10 条技术问题 | 1 | 5 min |
| **低负载** | 5 用户逐步启动（每秒 +1），每人随机间隔 15~30s 提问 | 5 | 5 min |
| **中负载** | 20 用户逐步启动（每秒 +2），每人间隔 10~25s | 20 | 10 min |
| **高负载** | 50 用户逐步启动（每秒 +3），每人间隔 8~20s | 50 | 10 min |
| **极限** | 100 用户逐步启动（每秒 +5），每人间隔 5~15s | 100 | 10 min |

**关键指标**：

| 指标 | 说明 | 健康阈值 |
|------|------|----------|
| **P50 延迟** | 50% 用户在 X 秒内收到首个 token | < 10s |
| **P95 延迟** | 95% 用户的首 token 时间 | < 30s |
| **完整响应 P50** | 从提问到 `done` 事件 | < 25s |
| **完整响应 P95** | 同上 | < 60s |
| **错误率** | 5xx + 连接断开 | < 5% |
| **LLM 队列深度** | Ollama 排队请求数 | < 20 |
| **SQLite 写等待** | 写锁等待时间 | < 1s |
| **GPU 利用率** | nvidia-smi 监控 | 90%+ 说明 GPU 吃满 |

## 6. 测试前必须做的优化

不改直接测 100 并发会全线崩溃。建议先做：

### 必须（否则无法测）
1. **SQLite 开启 WAL 模式** — 读写并发从 1 提升到 N 读 + 1 写
   ```python
   # engine 创建后加
   from sqlalchemy import event
   @event.listens_for(engine, "connect")
   def _set_wal(dbapi_conn, _):
       dbapi_conn.execute("PRAGMA journal_mode=WAL")
   ```
2. **给 `/chat` 的 Ollama 调用加超时**
   ```python
   ChatOllama(..., timeout=120)  # 120秒超时
   ```
3. **uvicorn 多 worker** — 至少利用多核
   ```bash
   uvicorn app.main:app --workers 4
   ```

### 建议（显著改善）
4. **LLM 请求加应用层排队 + 超时熔断**
   - 单 GPU 无法并发推理，不如在前端做一个公平队列
5. **embedding 结果缓存** — 热点问题 `hash(question)` → 检索结果缓存 5 分钟
6. **降低 `num_ctx`** — 6144 → 4096，prompt 处理更快
7. **降低 `num_predict`** — 2048 → 1024，生成更快（压力测试验证吞吐，不是质量）

## 7. Locust 测试脚本框架

```python
# locustfile.py
from locust import HttpUser, task, between, events
import time

class JavaDoctorUser(HttpUser):
    wait_time = between(8, 25)  # 模拟真实用户阅读+输入间隔

    def on_start(self):
        # 注册 + 登录，拿到 token
        resp = self.client.post("/api/auth/login", json={
            "username": f"loadtest_{self._user_id()}",
            "password": "test123"
        })
        # 如果没注册过就先注册
        if resp.status_code == 401:
            self.client.post("/api/auth/register", json={...})
            resp = self.client.post("/api/auth/login", json={...})
        self.token = resp.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
        # 创建一个专属会话
        conv = self.client.post("/api/conversations",
            json={"title": "压力测试"},
            headers=self.headers).json()
        self.conv_id = conv["id"]

    @task(7)  # 70% 技术问答
    def ask_technical(self):
        q = random.choice(TECH_QUESTIONS)  # "什么是Java双亲委派模型？" 等20条
        start = time.time()
        with self.client.post(
            f"/api/chat/{self.conv_id}",
            json={"question": q},
            headers={**self.headers, "Accept": "text/event-stream"},
            catch_response=True,
            stream=True,
        ) as resp:
            first_token = None
            for line in resp.iter_lines():
                if first_token is None:
                    first_token = time.time() - start
                # 解析 SSE...
            total = time.time() - start
            # 上报自定义指标
            events.request.fire(
                request_type="POST",
                name="chat_technical",
                response_time=total * 1000,
                response_length=len(content),
            )

    @task(2)  # 20% 闲聊
    def ask_chitchat(self): ...

    @task(1)  # 10% 会话操作
    def list_conversations(self): ...
```

## 8. 执行步骤

```
第 1 步: 备份 data/javadoctor.db（测完恢复）
第 2 步: 创建 100 个测试账号（脚本批量注册）
第 3 步: 应用 SQLite WAL + uvicorn workers 优化
第 4 步: 预热 LLM 模型（ollama run qwen3.5:4b → 退出）
第 5 步: 启动 locust，先跑场景A确认工具正常
第 6 步: 按 预热→低→中→高→极限 逐级跑
第 7 步: 收集 locust 报告 + Ollama 日志 + SQLite 统计
第 8 步: 根据数据判断哪些组件需要优先优化
```

---

**一句话总结**：当前单 GPU + 单进程架构的瓶颈在 Ollama LLM 推理，100 人同时提问不可能实时响应。压力测试的目标应该是 **测出系统在不同并发层级的降级曲线**，找到可接受的最大并发数（预计 5~15 人同时提问），而不是追求 100 并发全部通过。
