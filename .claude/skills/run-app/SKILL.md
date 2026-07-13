---
name: run-app
description: 启动 JavaDoctor 项目(一键启动后端 + 前端)。当用户想打开/运行项目、查看网页效果、或说"启动项目""跑起来看看""运行一下"时使用。
---

# 启动 JavaDoctor

帮用户把 JavaDoctor 跑起来(开发模式),方便随时打开浏览器看效果。

## 前提检查

启动前先确认:
1. **Ollama 在跑**:`curl -s http://localhost:11434/api/tags` 应返回模型列表。如果返回空或连接失败,用后台启动:`ollama serve > /dev/null 2>&1 &`,等几秒再确认。
2. **本机两个模型已拉取**:`qwen3.5:4b`(对话)和 `bge-m3`(嵌入)。如果 `ollama list` 里缺哪个,先 `ollama pull <模型名>`。
3. **Python 依赖已装**:`cd backend && pip install -r requirements.txt`(首次或更新后)。

## 操作步骤

### 方式一:一键启动(推荐)

直接用项目根目录的启动脚本:

```
cd e:/ItHeima/JavaDoctor && cmd //c start.bat
```

这个脚本会:
1. 检查并启动 Ollama
2. 在独立窗口启动后端(FastAPI uvicorn,端口 8000)
3. 在独立窗口启动前端(Vite dev server,端口 5173)
4. 自动打开浏览器 `http://localhost:5173`

### 方式二:手动启动(排查问题时用)

1. 启动后端(后台):
   ```
   cd e:/ItHeima/JavaDoctor/backend && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
   ```

2. 启动前端(另一个终端):
   ```
   cd e:/ItHeima/JavaDoctor/frontend && npm run dev
   ```

3. 打开浏览器访问 `http://localhost:5173`

### 方式三:调试模式下分别启动

如果需要调试后端日志:
```
cd e:/ItHeima/JavaDoctor/backend && PYTHONIOENCODING=utf-8 python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 > _server.log 2>&1 &
```

确认后端起来:
```
curl -s http://127.0.0.1:8000/api/health
```

## 关闭项目 / 清理进程

当用户说"关掉""停掉""清理端口"时:

1. 用项目根目录的停止脚本:`cmd //c stop.bat`
2. 或手动清理:
   - 杀掉占用 8000 端口的进程:`netstat -ano | grep ':8000' | grep LISTENING | awk '{print $NF}' | xargs -r taskkill //F //PID`
   - 杀掉占用 5173 端口的进程:`netstat -ano | grep ':5173' | grep LISTENING | awk '{print $NF}' | xargs -r taskkill //F //PID`
   - 停止 Ollama(可选):`ollama stop`

## 注意事项

- **首次启动较慢**:后端会加载 bge-m3 和 qwen3.5:4b 两个模型到内存,首次问答延迟约 7-15 秒。
- **Windows 编码坑**:`start.bat` 和 `stop.bat` 脚本**全是 ASCII 英文**,不能有中文(GBK 控制台会乱码),已按要求处理。
- **端口冲突**:如果 8000/5173 被占用,先按上面清理进程的方法杀掉旧进程。
- **向量库数据**:首次 clone 项目后,`backend/data/` 下已有预置的 Chroma 向量库和 SQLite 数据库,无需重新入库。
