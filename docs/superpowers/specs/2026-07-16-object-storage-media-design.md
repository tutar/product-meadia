# 生成媒体对象存储设计

## 背景

现有生成流水线会将图片、音频、视频片段和最终 MP4 保存为第三方 URL 或本地 `/tmp` 路径。该表示无法保证跨进程、跨容器和跨部署读取，也无法统一处理用户权限、生命周期、重试和清理。

本设计规定：所有跨工具调用、进入任务状态或数据库的媒体必须成为对象存储中的私有 Media Asset。RustFS 是默认的 S3 兼容实现，但不是业务层契约。

## 媒体边界

以下内容属于持久媒体，必须进入对象存储：

- 用户上传的商品图片和源视频
- AI 生成图片
- AI 生成的视频片段
- TTS 音频
- 口型同步视频
- HyperFrames 最终 MP4

进程本地文件只能作为单次工具调用的临时工作文件。数据库和任务状态不得保存本地路径、第三方 Provider URL 或预签名 URL。

## 架构边界

```text
Agent / Tool / API
        ↓
    MediaService
        ↓
ObjectStorage interface
        ↓
RustFS S3 adapter (default)
```

`ObjectStorage` 提供 `upload`、`download`、`exists`、`delete` 和 `presign_get`。Agent、工具和 API 不直接调用 RustFS SDK，也不自行拼接 bucket 或 object key。

`MediaService` 负责创建资产、媒体校验、上传、鉴权访问、替代关系、不可用状态和清理安排。

## 数据模型

新增统一的 `media_assets` 表：

```text
media_assets
- id
- owner_user_id
- product_id nullable
- task_id nullable
- category
- bucket
- object_key
- content_type
- size_bytes
- checksum
- status
- source_provider nullable
- idempotency_key nullable
- created_at
- superseded_at nullable
- delete_after nullable
```

业务表改为保存资产外键：

- `products.main_image_asset_id`
- `generated_images.asset_id`
- `video_tasks.result_video_asset_id`
- 任务中间状态保存 `asset_id`

Media Asset 不可变；重新生成会产生新的 asset ID。

## Bucket 与对象 key

使用单一私有 bucket，例如 `product-media`：

```text
users/{user_id}/tasks/{task_id}/source/{asset_id}.{ext}
users/{user_id}/tasks/{task_id}/images/{asset_id}.{ext}
users/{user_id}/tasks/{task_id}/audio/{asset_id}.{ext}
users/{user_id}/tasks/{task_id}/clips/{asset_id}.{ext}
users/{user_id}/tasks/{task_id}/lipsync/{asset_id}.{ext}
users/{user_id}/tasks/{task_id}/final/{asset_id}.mp4
users/{user_id}/products/{product_id}/images/{asset_id}.{ext}
```

## 写入语义

生成节点按以下顺序提交：

1. 外部服务生成或下载到本地临时文件。
2. 校验格式、大小和基本可读性。
3. 上传对象存储。
4. 确认对象可读取。
5. 创建 Media Asset 并写入业务引用或任务状态。
6. 节点标记成功。
7. 删除本地临时文件。

对象存储是强依赖。上传或持久引用创建失败时，节点整体失败并重试，不允许降级成本地持久化，也不允许下游消费“上传待处理”的媒体。

上传成功但数据库提交失败的对象由孤儿清理任务处理。

## 权限与访问

对象默认私有。数据库保存 bucket 和 object key，但不会把它们作为前端契约。

授权客户端通过独立端点获取访问 URL：

```text
GET /api/v1/media/{asset_id}/access
→ { "url": "...", "expires_at": "..." }
```

API 根据 `owner_user_id` 校验权限。预签名 URL 默认有效一小时；前端在即将过期或收到 401/403 时重新获取。

外部生成服务每次调用和重试时重新签发只读 URL。如果服务无法访问内网 RustFS，由 MediaService 提供受控临时代理，而不是公开 bucket。

## 完整性与幂等

- 上传时记录 SHA-256、大小和 content type。
- 同一任务节点使用幂等键，避免网络超时重试产生重复资产。
- 同一用户、同一任务内允许按 checksum 复用。
- 不做跨用户全局去重，保持所有权、删除和隐私边界清晰。

## 生命周期

- 最终视频、当前批准图片和产品主图随对应任务或产品保留。
- 被替代图片、视频片段、音频和失败任务媒体保留七天。
- 删除任务时异步删除任务拥有的全部对象。
- 产品级对象在依赖任务完成或删除后清理。
- 工具调用失败留下的本地临时文件在重试窗口结束后删除。
- 每日清理孤儿对象和到期对象。

## 旧数据迁移

迁移脚本必须幂等且可断点续跑：

- 可读取的本地文件上传后替换为 Media Reference。
- 可下载的 Provider URL 下载、校验、上传后替换。
- 已在对象存储中的旧 URL 解析为 bucket/key；无法安全解析时复制到新 key。
- 文件丢失或 URL 失效时将媒体标记为 `unavailable`，允许用户从对应步骤重新生成。

迁移期间兼容读取旧引用；新代码部署后立即禁止写入旧格式。迁移结束后删除兼容读取代码。

## 测试要求

必须覆盖：

- 私有对象上传和读取
- 预签名 URL、过期和刷新
- 不同用户之间的权限隔离
- 上传失败时节点失败且不写入旧格式
- 节点重试的幂等性
- 旧本地路径和 Provider URL 迁移
- `unavailable` 媒体行为
- 七天保留和孤儿清理
- 最终视频跨 API/worker 容器预览

## 落地顺序

1. **基础层**：`media_assets`、ObjectStorage、RustFS adapter、MediaService、私有 bucket 和签名访问 API。
2. **写入切换**：依次迁移图片、音频、视频片段、口型视频和最终 MP4。
3. **读取切换**：前端统一使用 `asset_id → /media/{id}/access`，移除本地路径和第三方 URL 直连。
4. **迁移清理**：幂等迁移旧数据、标记 unavailable、启动保留和孤儿清理，最后删除旧格式兼容代码。

每个阶段必须通过对应集成测试后才能进入下一阶段。架构决策见 `docs/adr/0001-persist-media-in-object-storage.md`。
