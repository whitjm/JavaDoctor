"""
JavaDoctor 压力测试 — Locust 脚本。
模拟 100 人同时使用的场景，涵盖健康检查/认证/CRUD/闲聊/技术问答/混合负载。

用法：
  cd e:/ItHeima/JavaDoctor
  locust -f tests/locustfile.py --host=http://127.0.0.1:8000

然后打开 http://localhost:8089 配置并发数启动测试。
无头模式：
  locust -f tests/locustfile.py --host=http://127.0.0.1:8000 \
    --headless --users 100 --spawn-rate 5 --run-time 10m \
    --html=docs/loadtest-report.html --csv=docs/loadtest
"""
from __future__ import annotations

import json
import logging
import random
import string
import time
from typing import Any

from locust import HttpUser, between, events, task

# ── 测试题库 ──────────────────────────────────────────────
# 技术问题（完整 RAG 链路：检索 + LLM 生成）
TECH_QUESTIONS = [
    "Java 双亲委派模型是什么？",
    "HashMap 的底层实现原理是什么？",
    "请解释 JVM 内存模型",
    "Spring Boot 自动配置原理",
    "什么是线程安全？如何保证线程安全？",
    "MySQL 索引底层数据结构是什么？",
    "请解释 Redis 的持久化机制 RDB 和 AOF",
    "什么是 Java 的反射机制？有哪些应用场景？",
    "请解释数据库事务的 ACID 特性",
    "Spring 的依赖注入有几种方式？",
    "什么是分布式锁？Redis 如何实现分布式锁？",
    "Java 垃圾回收机制 G1 和 CMS 有什么区别？",
    "请解释 TCP 三次握手和四次挥手",
    "什么是微服务架构？有哪些优缺点？",
    "MyBatis 中 # 和 $ 的区别是什么？",
    "请解释 Java 中的 volatile 关键字",
    "什么是 CAP 理论？分布式系统中如何取舍？",
    "Spring Cloud 的核心组件有哪些？",
    "什么是消息队列？如何保证消息不丢失？",
    "请解释 Java 类加载机制",
]

# 闲聊（意图路由直答，不走检索）
CHITCHAT_QUESTIONS = [
    "你好",
    "你是谁",
    "你能做什么",
    "你好呀",
    "今天天气怎么样",
    "你能帮我什么",
]

# ── 工具函数 ──────────────────────────────────────────────


def uid() -> str:
    """随机 6 位小写字母，用于生成测试用户名。"""
    return "".join(random.choices(string.ascii_lowercase, k=6))


def event_name(scenario: str) -> str:
    """生成 Locust 统计分组名。"""
    return f"[{scenario}]"


# ── 用户行为类 ────────────────────────────────────────────


class JavaDoctorUser(HttpUser):
    """模拟一个真实用户：注册/登录 → 创建会话 → 随机提问。

    使用 wait_time 模拟用户阅读回答后的思考+输入间隔。
    """

    wait_time = between(8, 25)

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.token = ""
        self.headers: dict[str, str] = {}
        self.conv_id: int = 0

    # ── 生命周期 ──────────────────────────────────────

    def on_start(self) -> None:
        """每个虚拟用户启动时执行：注册账号 → 登录 → 创建专属会话。"""
        username = f"loadtest_{uid()}"
        password = "test123456"

        # 1. 注册（忽略"用户名已存在"）
        self.client.post(
            "/api/auth/register",
            json={"username": username, "password": password},
            name=event_name("注册"),
        )

        # 2. 登录
        resp = self.client.post(
            "/api/auth/login",
            json={"username": username, "password": password},
            name=event_name("登录"),
        )
        if resp.status_code == 200:
            data = resp.json()
            self.token = data.get("access_token", "")
        else:
            logging.error("登录失败: %s", resp.text)
            return

        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

        # 3. 创建专属会话
        resp = self.client.post(
            "/api/conversations",
            json={"title": "压测会话"},
            headers=self.headers,
            name=event_name("创建会话"),
        )
        if resp.status_code == 201:
            self.conv_id = resp.json().get("id", 0)

    # ── 任务定义（权重总和 = 10）──────────────────────

    @task(7)
    def ask_technical(self) -> None:
        """技术问答 — 完整 RAG 链路。核心压测场景。"""
        if not self.token or not self.conv_id:
            return
        question = random.choice(TECH_QUESTIONS)
        self._do_chat(question, "技术问答")

    @task(2)
    def ask_chitchat(self) -> None:
        """闲聊 — 意图路由直答，不走检索。"""
        if not self.token or not self.conv_id:
            return
        question = random.choice(CHITCHAT_QUESTIONS)
        self._do_chat(question, "闲聊问答")

    @task(1)
    def list_conversations(self) -> None:
        """会话列表查询 — 纯 DB 读。"""
        if not self.token:
            return
        self.client.get(
            "/api/conversations",
            headers=self.headers,
            name=event_name("会话列表"),
        )

    # ── 核心：SSE 流式问答 ────────────────────────────

    def _do_chat(self, question: str, scenario: str) -> None:
        """发起 SSE 流式问答请求并解析事件流，精确计时。"""
        start = time.monotonic()
        first_token_at: float | None = None
        token_count = 0
        full_text = ""
        has_error = False
        error_msg = ""

        try:
            # 使用 stream=True 获取原始响应流
            with self.client.post(
                f"/api/chat/{self.conv_id}",
                json={"question": question},
                headers=self.headers,
                name=event_name(scenario),
                catch_response=True,
                stream=True,
            ) as resp:
                if resp.status_code != 200:
                    resp.failure(f"HTTP {resp.status_code}: {resp.text[:200]}")
                    return

                # 手动解析 SSE 流
                buffer = ""
                for raw_bytes in resp.raw.stream(decode_content=False):
                    if raw_bytes:
                        try:
                            buffer += raw_bytes.decode("utf-8")
                        except UnicodeDecodeError:
                            continue

                    # 按空行切分事件
                    while "\n\n" in buffer:
                        sep = buffer.index("\n\n")
                        raw_line = buffer[:sep]
                        buffer = buffer[sep + 2:]

                        line = raw_line.strip()
                        if not line.startswith("data:"):
                            continue
                        payload = line[5:].strip()
                        if not payload:
                            continue

                        try:
                            evt = json.loads(payload)
                        except json.JSONDecodeError:
                            continue

                        etype = evt.get("event", "")

                        if etype == "token":
                            if first_token_at is None:
                                first_token_at = time.monotonic()
                            token_count += 1
                            full_text += evt.get("data", "")

                        elif etype == "done":
                            pass  # 正常结束

                        elif etype == "citations":
                            pass  # 引用信息

                        elif etype == "error":
                            has_error = True
                            error_msg = evt.get("data", "未知错误")

        except Exception as exc:
            has_error = True
            error_msg = str(exc)

        elapsed = time.monotonic() - start
        ttft = (first_token_at - start) if first_token_at else None

        # 向 Locust 报告结果
        events.request.fire(
            request_type="POST",
            name=event_name(scenario),
            response_time=elapsed * 1000,
            response_length=len(full_text),
            exception=Exception(error_msg) if has_error else None,
        )

        # 定期输出关键指标到日志
        if random.random() < 0.05:  # 5% 采样输出
            logging.info(
                "[%s] 总耗时=%.1fs | 首token=%.1fs | tokens=%d | 错误=%s",
                scenario,
                elapsed,
                ttft or -1,
                token_count,
                error_msg[:80] if has_error else "无",
            )


# ── 独立场景类（用于纯 API 压力测试，不涉及 SSE 长连接）──


class ApiBaselineUser(HttpUser):
    """基准性能测试：健康检查、登录、CRUD。短请求、高吞吐。"""

    wait_time = between(0.5, 2)

    def on_start(self) -> None:
        self.username = f"api_{uid()}"
        self.password = "test123456"
        self.client.post(
            "/api/auth/register",
            json={"username": self.username, "password": self.password},
            name=event_name("API-注册"),
        )
        resp = self.client.post(
            "/api/auth/login",
            json={"username": self.username, "password": self.password},
            name=event_name("API-登录"),
        )
        if resp.status_code == 200:
            self.token = resp.json().get("access_token", "")
            self.headers = {"Authorization": f"Bearer {self.token}"}
        else:
            self.token = ""
            self.headers = {}

    @task(5)
    def health_check(self) -> None:
        """GET /api/health — 裸 FastAPI 极限 QPS。"""
        self.client.get("/api/health", name=event_name("健康检查"))

    @task(3)
    def login(self) -> None:
        """POST /api/auth/login — bcrypt 验密 + JWT 签发。"""
        self.client.post(
            "/api/auth/login",
            json={"username": self.username, "password": self.password},
            name=event_name("API-登录"),
        )

    @task(2)
    def get_me(self) -> None:
        """GET /api/auth/me — JWT 验签 + 单行查库。"""
        if not self.token:
            return
        self.client.get(
            "/api/auth/me",
            headers=self.headers,
            name=event_name("当前用户"),
        )

    @task(1)
    def crud_cycle(self) -> None:
        """会话 CRUD：创建 → 查列表 → 删除。"""
        if not self.token:
            return
        # 创建
        resp = self.client.post(
            "/api/conversations",
            json={"title": "API基准测试"},
            headers=self.headers,
            name=event_name("CRUD-创建"),
        )
        cid = resp.json().get("id") if resp.status_code == 201 else None
        # 列表
        self.client.get(
            "/api/conversations",
            headers=self.headers,
            name=event_name("CRUD-列表"),
        )
        # 删除
        if cid:
            self.client.delete(
                f"/api/conversations/{cid}",
                headers=self.headers,
                name=event_name("CRUD-删除"),
            )


# ── 自定义 Locust 事件 ────────────────────────────────────


@events.init.add_listener
def on_locust_init(environment, **kwargs):
    """测试启动时的初始化日志。"""
    if environment.web_ui:
        logging.info("Locust Web UI 已启动 → http://localhost:8089")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """测试结束时的汇总日志。"""
    stats = environment.stats
    logging.info("=" * 60)
    logging.info("压力测试结束 — 汇总统计")
    logging.info("=" * 60)
    logging.info("总请求数: %d", stats.total.num_requests)
    logging.info("失败请求: %d", stats.total.num_failures)
    logging.info("平均响应: %.0f ms", stats.total.avg_response_time)
    logging.info("P50 响应: %.0f ms", stats.total.get_response_time_percentile(0.5))
    logging.info("P95 响应: %.0f ms", stats.total.get_response_time_percentile(0.95))
    logging.info("P99 响应: %.0f ms", stats.total.get_response_time_percentile(0.99))
    logging.info("最大响应: %.0f ms", stats.total.max_response_time)
    logging.info("RPS (总): %.1f", stats.total.total_rps)
    logging.info("=" * 60)
