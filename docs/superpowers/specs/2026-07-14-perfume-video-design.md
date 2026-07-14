# 香水短视频生成应用 — 设计文档

## 概述

基于 DeepAgents (LangChain + LangGraph) 构建的香水产品短视频 AI 生成应用。输入产品信息（商品名称、前中后调、适用场景、商品主图），支持三种视频类型自动生成：产品宣传视频、爆款仿拍视频、商品拟人视频。

**目标用户**：内部运营团队 + C 端消费者  
**规模**：日均数百条，单条生成 1–3 分钟  
**部署**：Docker Compose，与 agent-infra 共享中间件

---

## 视频类型与生成流程

### 类型一：产品宣传视频 (promo)

```
输入产品信息
  → LLM 生成脚本 + 生图 prompts
  → 用户审核编辑脚本
  → Agnes Image 批量生图（N 张可配置，默认 4）
  → 用户逐张审核（全部通过才继续）
  → Agnes Video 关键帧模式图生视频
  → VoxCPM2 TTS 配音
  → HyperFrames 合成（拼接片段 + 字幕 + 转场 + BGM）→ MP4
```

### 类型二：爆款仿拍视频 (viral)

```
输入产品信息 + 爆款视频链接
  → 下载视频 → FunASR 转写 → LLM 分析结构（脚本框架/分镜/转场/BGM/字幕风格）
  → 用户确认分析结果（可选覆盖：分镜/时长/转场/BGM 风格/字幕位置）
  → 逐镜：改写脚本 → 生成对应画面 → 图生视频
  → VoxCPM2 TTS 配音
  → HyperFrames 合成（保持原视频风格参数）→ MP4
```

### 类型三：商品拟人视频 (personify)

```
输入产品信息 + 商品主图
  → LLM 设计拟人角色 → Agnes Image 生成角色图
  → 用户审核角色形象
  → LLM 第一人称口播脚本 → 用户审核编辑
  → VoxCPM2 TTS 配音
  → LatentSync 1.6 唇形同步 + 面部动画
  → HyperFrames 合成（说话视频 + 字幕 + 产品信息动画 + BGM）→ MP4
```

---

## 架构

```
┌─────────────────────────────────────────────────────────┐
│                    前端 (Web UI)                         │
│  产品录入 → 视频类型选择 → 审核(脚本/图片) → 预览/下载    │
└──────────────────────┬──────────────────────────────────┘
                       │ REST API + WebSocket (进度推送)
┌──────────────────────▼──────────────────────────────────┐
│                  FastAPI 后端                            │
│  · CRUD API (Product/Task)                              │
│  · Celery 任务调度                                       │
│  · WebSocket 进度推送                                    │
└──────────────────────┬──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│                Agent 编排层 (DeepAgents)                  │
│                                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐      │
│  │ Promo    │  │ Viral    │  │ Personify        │      │
│  │ Graph    │  │ Graph    │  │ Graph            │      │
│  └────┬─────┘  └────┬─────┘  └───────┬──────────┘      │
│       └──────────────┼───────────────┘                  │
│               ┌──────▼──────┐                           │
│               │ Shared Tools│                           │
│               └──────┬──────┘                           │
└──────────────────────┼──────────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────────┐
│                   外部服务层                              │
│  LiteLLM │ Agnes Image/Video │ VoxCPM2 │ LatentSync    │
│  FunASR  │ HyperFrames CLI   │ FFmpeg                  │
└─────────────────────────────────────────────────────────┘
```

三层结构：Web 层 (FastAPI) → Agent 层 (DeepAgents/LangGraph) → 引擎层 (AI 服务 + 合成工具)

---

## API 设计

见 `api/openapi.yaml`

核心端点：
- `POST /api/v1/products` — 创建产品
- `POST /api/v1/tasks` — 创建视频任务
- `GET /api/v1/tasks/{id}` — 任务状态（含子步骤）
- `WS /ws/tasks/{id}` — 实时进度推送
- `PUT /api/v1/tasks/{id}/script` — 审核/编辑脚本
- `PUT /api/v1/tasks/{id}/images/{img_id}` — 审核图片
- `POST /api/v1/tasks/viral/analyze` — 爆款视频分析

---

## 数据模型

见 `db/schema.sql`

核心表：`products`, `video_tasks`, `scripts`, `generated_images`, `viral_analyses`

---

## Agent 架构

每个视频类型对应一个 LangGraph StateGraph，公共能力为 Shared Tools：

```python
# Shared Tools (每个 Graph 均可调用)
generate_image(prompt: str) → Agnes Image via LiteLLM
generate_video(prompt: str, image_urls: list) → Agnes Video API
generate_tts(text: str) → VoxCPM2
lipsync(image_url: str, audio_url: str) → LatentSync 1.6
render_hyperframes(html: str, assets: dict) → npx hyperframes render
transcribe_audio(url: str) → FunASR
analyze_video_structure(url: str) → LLM (researcher)
```

Human-in-the-Loop 检查点（LangGraph `interrupt` 机制）：
- `script_review` — 等待用户审核脚本
- `image_review` — 等待用户审核所有图片
- `viral_confirm` — 等待用户确认仿拍分析
- `character_review` — 等待用户审核拟人角色

---

## 基础设施依赖

复用 `agent-infra` 已有服务：

| 服务 | 用途 |
|------|------|
| LiteLLM (:4000) | LLM 调用 (scriptwriter/researcher) + Agnes Image 生图 |
| PostgreSQL (:5432) | 主数据库 |
| Redis (:6379) | Celery Broker |
| RustFS (:8001) | 对象存储（图片/视频/音频） |
| FunASR (:8021) | 爆款视频语音转写 |
| Langfuse (:3060) | LLM 可观测性 |
| Flower (:5555) | Celery 监控 |

项目新增依赖：
- **HyperFrames** — Node.js 22+, `npx hyperframes render`
- **VoxCPM2** — TTS 服务（用户自部署）
- **LatentSync 1.6** — 唇形同步
- **Agnes Video API** — 视频生成（直调 `apihub.agnes-ai.com`）

---

## 错误处理 & 可观测性

- **Tool 调用重试**: 3 次指数退避，生视频超时 360s
- **Celery 任务重试**: max_retries=3，审核步骤无限等待
- **LangGraph checkpoint**: 任务中断后从断点恢复
- **Langfuse**: `@observe` 追踪所有 LLM 调用
- **WebSocket**: 步骤级进度实时推送前端

---

## 测试策略

| 层级 | 范围 | 工具 |
|------|------|------|
| 单元测试 | Shared Tools mock、数据模型验证 | pytest |
| Agent 测试 | LangGraph 单步执行、checkpoint 恢复 | pytest + LangGraph test utils |
| 集成测试 | Agnes/VoxCPM2/LatentSync sandbox 调用 | pytest + docker-compose |
| E2E | 完整流程: 输入 → 审核 → MP4 | 手动 / Playwright |

---

## 项目结构

```
product-meadia/
├── api/openapi.yaml                  # API 规范
├── db/schema.sql                     # 数据库 DDL
├── docs/superpowers/specs/           # 设计文档
├── src/
│   ├── api/                          # FastAPI routes
│   ├── agents/                       # DeepAgents graphs
│   │   ├── promo_graph.py
│   │   ├── viral_graph.py
│   │   └── personify_graph.py
│   ├── tools/                        # Shared tools
│   │   ├── image_gen.py
│   │   ├── video_gen.py
│   │   ├── tts.py
│   │   ├── lipsync.py
│   │   └── render.py
│   ├── models/                       # SQLAlchemy models
│   ├── tasks/                        # Celery tasks
│   └── ws/                           # WebSocket handlers
├── frontend/                         # Web UI
├── docker-compose.yml
└── requirements.txt
```

---

## 技术栈

| 层 | 技术 |
|----|------|
| Agent 编排 | DeepAgents (LangChain + LangGraph) |
| LLM 网关 | LiteLLM (DeepSeek v4 Flash/Pro) |
| 后端框架 | FastAPI |
| 任务队列 | Celery (Redis Broker) |
| 数据库 | PostgreSQL |
| 对象存储 | RustFS |
| 图像生成 | Agnes Image 2.1 Flash |
| 视频生成 | Agnes Video V2.0 |
| TTS | VoxCPM2 |
| 唇形同步 | LatentSync 1.6 |
| 视频合成 | FFmpeg + HyperFrames |
| 可观测性 | Langfuse + Flower |
| 前端 | React + Vite (SPA) |

---

## 用户认证

JWT (OAuth2 Password Flow)，所有通道最终签发 JWT access_token + refresh_token。

| grant_type | 适用 | 入参 |
|-----------|------|------|
| `password` | 邮箱登录 | email + password |
| `google_oauth` | Google 第三方登录 | google_code |

- 内部运营: 邮箱 + 密码，或 Google OAuth
- C 端消费者: Google OAuth 首选，邮箱 + 密码备选
- FastAPI `OAuth2PasswordBearer` + `python-jose` + `authlib` 实现
- 用户表 `role` 字段区分内部/C 端，API 层 `Depends(get_current_user)` 做权限校验
- `/api/v1/auth/token` 统一签发，`/api/v1/auth/register` 注册
