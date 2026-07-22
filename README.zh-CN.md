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
                     +---- LiteLLM Python SDK -> 用户配置的模型服务
                     +---- S3 兼容对象存储
```

PostgreSQL、Redis 和符合 S3 API 规范的对象存储是部署前置条件。本仓库不包含这些基础服务的编排。视频任务通过 LiteLLM Python SDK 直接调用用户配置的模型服务；该模型选择流程不要求部署 LiteLLM Proxy。RustFS 只是可选的 S3 兼容实现，并非硬性依赖。

生成的图片、音频和视频应持久化到私有对象存储。数据库保存持久化的对象标识；需要查看或下载媒体时，再为客户端生成短时、只读的预签名 URL。

## 环境要求

- Python 3.11+
- Node.js 22+
- HyperFrames CLI（用于最终视频渲染，`npm install -g hyperframes`）
- PostgreSQL
- Redis
- 一个符合 S3 API 规范的对象存储服务

模型服务的地址和凭据在 Web 界面的“偏好设置 → 模型配置”中按用户维护，而不是写入部署环境变量。私有 OpenAI-compatible endpoint 可以没有凭据；云端服务通常需要用户自己的 BYOK。

## 快速开始

1. 准备上述外部服务，并确保本地 API 与 Celery worker 可以访问它们。

2. 配置环境变量：

   ```bash
   cp .env.example .env
   # 编辑 .env，填写数据库、Redis 和对象存储配置
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

5. 登录后打开“偏好设置 → 模型配置”：

   - 从内置模板创建配置，或选择“配置私有模型”填写 OpenAI-compatible endpoint、模型 ID 和支持的阶段。
   - 按模型服务需要填写 BYOK；无鉴权私有 endpoint 可留空。
   - 验证配置并为所需阶段设置默认模型。无法安全探测的服务会在首次真实调用时确认可用性。

6. 使用 `perfume-video` conda 环境启动本地 Celery worker：

   ```bash
   ./start-worker.sh
   ```

   worker 消费 `perfume-video` 队列，并使用宿主机的 HyperFrames CLI 渲染最终视频。需要定时清理时，单独启动 beat：

   ```bash
   ./start-beat.sh
   ```

本地开发可使用 `./start.sh` 一次启动 API、前端和 worker。脚本通过 `conda run -n perfume-video` 运行；请在该环境安装 Python 依赖，并在宿主机安装 HyperFrames：

```bash
conda activate perfume-video
pip install -r requirements.txt
npm install -g hyperframes
```

## 配置说明

`.env.example` 列出了部署级配置。至少需要配置 PostgreSQL URL、Redis broker URL，以及 S3 兼容对象存储集成所需的地址和凭据。模型 endpoint 与 BYOK 属于用户的模型配置，不应写入 `.env` 或提交到 Git。示例目前包含 RustFS 开发环境地址，请根据实际使用的对象存储调整。

当浏览器直接从对象存储读取 Media Access URL 时，必须为对应 bucket 配置 CORS：仅允许前端来源发起 `GET` 和 `HEAD`。本地开发来源是 `http://localhost:5173`；生产环境应替换为自身的 HTTPS 前端来源。私有媒体不要使用通配符来源。

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
