---
name: security-audit
description: 对项目代码做安全审计。当用户说"查安全""安全审计""有没有漏洞""检查敏感信息泄露""看看安全隐患"时使用。检查:敏感信息泄露、注入漏洞、配置文件明文密钥、以及其他安全隐患。
---

# 安全审计

从多个方面检查项目代码的安全隐患,给用户一份说人话的审计报告。用户是编程小白,报告不要堆黑话,要说清楚"有什么风险、会怎样、怎么改"。

## 检查范围

如果用户指定了文件/目录就查它;没指定就查整个项目的源代码和配置文件:
- 后端:`backend/app/`、`backend/.env.example`、根目录配置文件
- 前端:`frontend/src/`、`frontend/vite.config.ts`
- 跳过 `node_modules`、`__pycache__`、`backend/data/`、`dist`、测试文件

## 四个检查方向

### 方向一:敏感信息泄露(硬编码密钥)

在代码里搜有没有直接写死的敏感信息:
- 密码、API key、token、JWT 密钥、证书私钥;
- 数据库连接串里的账号密码;
- 第三方服务的 secret / access key(如 OpenAI API key、云服务);
- 形如 `SECRET_KEY = "xxx"`、`password = "xxx"`、`api_key = "..."` 的硬编码。

搜索关键词参考:`password`、`passwd`、`secret`、`api_key`/`apikey`、`token`、`private_key`、`access_key`、`credential` 等(大小写都查)。.env 文件应该被 .gitignore 排除。找到就指明文件和行号,说明为什么危险。

### 方向二:注入类漏洞(SQL 注入 / 命令注入)

重点查后端数据库操作和命令执行:
- **SQL 注入**:Python 代码里 SQL 语句是不是用字符串拼接/格式化(f-string/`%`/`.format()`)把变量塞进去的。正确做法是用 SQLAlchemy 的参数化查询(ORM 的 `filter()` / `filter_by()` 或原生 SQL 用 `:param` 占位符)。搜索 `db.execute(`、`text(`、`f"SELECT` 等模式。
- **命令注入**:`os.system()`、`subprocess`、`eval()`、`exec()` 是否把外部输入直接拼进去。
- **路径穿越**:`os.path.join()` 或文件读写是否引用了用户可控的路径参数,有没有校验。

### 方向三:配置文件里的明文敏感信息

检查配置类文件:
- `backend/.env`(已被 .gitignore 排除,确认)、`backend/.env.example`(会被提交,不应含真实密钥);
- `frontend/vite.config.ts`、`backend/app/config.py` 等;
- 有没有明文写着密码、密钥、私有仓库凭证等;
- 检查 `.gitignore` 是否覆盖了 `.env`、`data/`、`*.db`、`__pycache__/` 等敏感或生成文件。

### 方向四:FastAPI Web 安全隐患

本项目是 FastAPI + React 的 Web 应用,重点看:
- **CORS 配置**:`backend/app/main.py` 里 `CORSMiddleware` 是否设置了过于宽松的 `allow_origins=["*"]`(生产环境应收紧)。
- **JWT 安全**:Token 过期时间是否合理(`backend/app/core/security.py`)、密钥是否随机、算法是否硬编码。
- **权限校验**:`backend/app/core/deps.py` 的 `require_admin` 依赖是否正确应用于 `/api/admin/*` 路由。
- **密码安全**:密码哈希是否用了 bcrypt(已用,核查)、是否有密码长度/复杂度校验。
- **文件上传安全**:`backend/app/api/admin.py` 是否校验了上传文件类型和大小(已有 `SUPPORTED_TYPES` 和 `max_upload_mb`,核查)。
- **依赖风险**:`backend/requirements.txt` 里有没有明显可疑或过旧的依赖,可提示用 `pip audit` 查已知漏洞。
- **前端 XSS**:React 默认防 XSS,但 Markdown 渲染(`react-markdown`)是否关闭了 HTML 标签。

## 输出:审计报告

给用户一份说人话的报告,包含:

1. **总体结论**:整体安全状况如何(有没有高危问题、大体放心还是需要处理)。
2. **按严重程度列问题**,每条写清:
   - 风险等级:🔴高危 / 🟡中等 / 🔵提示;
   - 在哪个文件第几行(用 `文件:行号` 格式,可点击);
   - 属于哪个方向(敏感信息 / 注入 / 配置明文 / Web 安全);
   - 具体是什么风险、会导致什么后果(用大白话讲,比如"别人拿到这个能干嘛");
   - 建议怎么改。
3. **没问题的地方也说一句**:哪些方面检查过、是安全的,让用户放心。

排序:高危(能直接被利用、泄露密钥、注入)排最前,提示类排后。

## 注意事项

- 默认**只审计、只报告,不自动改代码**。除非用户明确说"帮我修",才动手。
- 读到疑似密钥/密码的内容,报告里用"第几行有一处疑似密钥"指代,**不要把密钥原文完整抄进报告**,避免二次泄露。
- 不确定是不是真漏洞时,如实说明"这里有风险点,需确认",不要夸大也不要漏报。
- 这是防御性的安全检查,目的是帮用户加固自己的项目。
