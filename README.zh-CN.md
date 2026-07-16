# Product Meadia

**Product Meadia** 是一个支持自行部署的 AI 商品视频生成平台。它将商品信息和媒体素材组织成可重复执行的工作流，用于生成脚本、图片、配音和最终视频，并在 Web 界面中展示任务进度与执行日志。

[English documentation / 英文文档](README.md)

## 核心能力

- 品类和商品管理
- 使用 AI 辅助生成商品主图
- 具备分步骤进度的异步视频生成任务
- 脚本、图片、配音和视频生成流程
- 任务详情、执行日志、重试和媒体预览
- FastAPI 后端、React 前端和 Celery 任务 worker

平台面向任意商品品类，并不限定香水或化妆品。

## 系统架构

```text
React + Vite  ->  FastAPI  ->  PostgreSQL
                     |
                     +---- Redis -> Celery worker / beat
                     +---- LiteLLM 和媒体生成服务
                     +---- S3 兼容对象存储
```

PostgreSQL、Redis、LiteLLM 和符合 S3 API 规范的对象存储是部署前置条件。本仓库不包含这些基础服务的编排。RustFS 只是可选的 S3 兼容实现，并非硬性依赖。

生成的图片、音频和视频应持久化到私有对象存储。数据库保存持久化的对象标识；需要查看或下载媒体时，再为客户端生成短时、只读的预签名 URL。

## 环境要求

- Python 3.11+
- Node.js 22+
- PostgreSQL
- Redis
- LiteLLM（或兼容的模型网关）
- 一个符合 S3 API 规范的对象存储服务

还需要为当前启用的 AI/媒体服务配置凭据和地址。部分生成步骤依赖特定服务，可能需要额外组件。

## 快速开始

1. 准备上述外部服务，并确保 API 进程可以访问它们。使用本项目提供的 worker Compose 文件时，需要让 worker 与这些服务处于同一个 Docker 网络。

2. 配置环境变量：

   ```bash
   cp .env.example .env
   # 编辑 .env，填写数据库、Redis、模型网关、供应商和存储配置
   ```

3. 启动 API：

   ```bash
   conda activate perfume-video  # 或使用其他 Python 3.11 环境
   pip install -r requirements.txt
   uvicorn src.main:app --host 0.0.0.0 --port 8000 --log-level info
   ```

4. 在另一个终端启动前端：

   ```bash
   cd frontend
   npm install
   npm run dev -- --host 0.0.0.0 --port 5173
   ```

   打开 <http://localhost:5173>。

5. 启动 Celery worker 和 beat。本项目的 `docker-compose.yml` 只启动这两个服务，外部基础服务需要提前运行：

   ```bash
   docker compose up -d --build worker beat
   ```

   worker 消费 `perfume-video` 队列。可使用以下命令查看日志：

   ```bash
   docker compose logs -f worker
   ```

如果不使用 Docker，也可以在本地使用相同环境变量启动：

```bash
celery -A src.tasks.celery_app worker --loglevel=info --concurrency=2 -Q perfume-video
celery -A src.tasks.celery_app beat --loglevel=info
```

## 配置说明

`.env.example` 列出了可用配置。至少需要配置 PostgreSQL URL、Redis broker URL、LiteLLM 地址和密钥、媒体供应商凭据，以及 S3 兼容对象存储集成所需的地址和凭据。示例目前包含 RustFS 开发环境地址，请根据实际使用的对象存储调整。请勿将密钥写入 Git，也不要提交 `.env`。

## 开发与测试

后端测试：

```bash
pytest -q
```

前端检查：

```bash
cd frontend
npm run build
npm run lint
```

依赖外部媒体或模型服务的集成测试会单独标记。运行前请先阅读对应测试模块和服务配置。

## 当前状态

项目仍在积极开发中。供应商适配器、媒体存储集成、认证和界面行为可能持续变化。用于生产环境前，请检查配置、保护 API、配置私有 bucket 和生命周期策略，并在实际环境验证每个生成服务。

## 参与贡献

请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)，了解 GitHub Flow、测试、Pull Request 和安全问题报告流程。

## 许可证

本项目采用 [Apache License 2.0](LICENSE) 许可。
