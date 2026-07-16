# Contributing to Product Meadia

Thank you for helping improve Product Meadia. This project uses GitHub Flow: keep changes focused, explain the problem they solve, and include evidence that they work.

## Before you start

- Search existing Issues and Pull Requests before opening a new one.
- For a bug, include reproduction steps, expected behavior, actual behavior, logs, and environment details. Remove secrets and personal data.
- For a feature, describe the user problem and proposed behavior before implementing it.
- Do not commit `.env`, API keys, generated media, database dumps, or provider credentials.

## Development workflow

1. Open or comment on an Issue so the change has a clear scope.
2. Create a short-lived branch from `main`:

   ```bash
   git switch main
   git pull --ff-only
   git switch -c fix/short-description
   ```

3. Make the smallest coherent change. Update tests and documentation when behavior or configuration changes.
4. Use a concise Conventional Commit style, for example:

   ```text
   feat: add product image retry
   fix: prevent duplicate video tasks
   docs: clarify worker setup
   ```

5. Run the relevant checks before opening a Pull Request:

   ```bash
   pytest -q
   cd frontend && npm run build && npm run lint
   ```

6. Open a Pull Request against `main`. Explain the motivation, implementation, tests run, configuration changes, migrations, and any known limitations.
7. Respond to review feedback and keep the branch up to date. Merge only after required checks and review have passed.

## Pull Request checklist

- [ ] The change is linked to an Issue or explains why no Issue is needed.
- [ ] Tests cover the changed behavior, where practical.
- [ ] Documentation and `.env.example` are updated when needed.
- [ ] No secrets, generated artifacts, or unrelated formatting changes are included.
- [ ] API, database, queue, and object-storage compatibility impacts are called out.
- [ ] The test and build commands above pass, or failures are explained.

## Reporting security issues

Do not publish credentials, private media URLs, or an exploitable vulnerability in a public Issue. Contact the repository maintainers privately through the GitHub repository's available contact channel and include enough detail to reproduce the issue safely.

## 中文贡献指南

感谢你帮助改进 Product Meadia。本项目采用 GitHub Flow：保持改动聚焦，说明解决的问题，并提供可验证的结果。

### 开始前

- 提交新 Issue 前先搜索已有 Issue 和 Pull Request。
- 报告 bug 时提供复现步骤、预期行为、实际行为、日志和环境信息；请移除密钥及个人数据。
- 提议功能时先说明用户问题和预期行为，再开始实现。
- 不要提交 `.env`、API 密钥、生成的媒体、数据库 dump 或供应商凭据。

### 开发流程

1. 创建或参与一个 Issue，明确改动范围。
2. 从 `main` 创建短生命周期分支：

   ```bash
   git switch main
   git pull --ff-only
   git switch -c fix/short-description
   ```

3. 完成一个内聚的最小改动；行为或配置变化时同步更新测试和文档。
4. 使用简洁的 Conventional Commit 风格，例如 `feat:`、`fix:`、`docs:`。
5. 创建 Pull Request 前运行相关检查：

   ```bash
   pytest -q
   cd frontend && npm run build && npm run lint
   ```

6. 向 `main` 创建 Pull Request，说明动机、实现、测试、配置变化、数据库迁移和已知限制。
7. 根据 review 意见修改，并在必要时同步最新 `main`。通过必要检查和 review 后再合并。

### Pull Request 检查清单

- [ ] 已关联 Issue，或说明无需 Issue 的原因。
- [ ] 在可行的情况下为改动行为补充测试。
- [ ] 必要时更新文档和 `.env.example`。
- [ ] 不包含密钥、生成物或无关格式化改动。
- [ ] 说明 API、数据库、队列和对象存储的兼容性影响。
- [ ] 上述测试和构建命令通过，或已说明失败原因。

### 安全问题报告

不要在公开 Issue 中发布凭据、私有媒体 URL 或可利用的漏洞。请通过 GitHub 仓库提供的维护者私下联系方式报告，并提供足以安全复现问题的细节。
