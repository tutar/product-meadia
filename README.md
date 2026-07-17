# Product Meadia

**Product Meadia** is a self-hostable platform for generating product videos with AI. It turns product information and media into a repeatable workflow for scripts, images, voiceovers, and final videos, with task progress and execution logs visible in the web UI.

[中文文档 / Chinese documentation](README.zh-CN.md)

## What it provides

- Product and category management
- AI-assisted product image generation
- Asynchronous video-generation tasks with step-by-step progress
- Script, image, voiceover, and video generation stages
- Task details, execution logs, retry support, and media preview
- A FastAPI backend, React frontend, and Celery task workers

The workflow is designed for products in any category; it is not limited to perfume or cosmetics.

## Architecture

```text
React + Vite  ->  FastAPI  ->  PostgreSQL
                     |
                     +---- Redis -> Celery worker / beat
                     +---- LiteLLM and media-generation providers
                     +---- S3-compatible object storage
```

PostgreSQL, Redis, LiteLLM, and an S3-compatible object store are deployment prerequisites. The repository does not bundle those infrastructure services. RustFS is one possible S3-compatible implementation, not a hard requirement.

Generated images, audio, and video should be persisted in private object storage. Application records keep durable object identifiers; clients receive short-lived, read-only presigned URLs when media needs to be viewed or downloaded.

## Prerequisites

- Python 3.11+
- Node.js 22+
- HyperFrames CLI (`npm install -g hyperframes`) for final video rendering
- PostgreSQL
- Redis
- LiteLLM (or another compatible model gateway)
- An S3-compatible object storage service

You must also provide credentials and endpoints for the AI/media providers enabled in your environment. Some generation stages are provider-specific and may require additional services.

## Quick start

1. Prepare the external services above and make sure the local API and Celery worker can reach them.

2. Configure the environment:

   ```bash
   cp .env.example .env
   # Edit .env: database, Redis, model gateway, provider, and storage settings
   ```

3. Start the API:

   ```bash
   conda activate perfume-video  # or use another Python 3.11 environment
   pip install -r requirements.txt
   uvicorn src.main:app --host 0.0.0.0 --port 8000 --log-level info
   ```

4. Start the frontend in another terminal:

   ```bash
   cd frontend
   npm install
   npm run dev -- --host 0.0.0.0 --port 5173
   ```

   Open <http://localhost:5173>.

5. Start the local Celery worker from the `perfume-video` conda environment:

   ```bash
   ./start-worker.sh
   ```

   The worker consumes the `perfume-video` queue and uses the host HyperFrames CLI to render final videos. Start scheduled cleanup separately when needed:

   ```bash
   ./start-beat.sh
   ```

For local development, `./start.sh` starts the API, frontend, and worker together. The scripts use `conda run -n perfume-video`; install Python dependencies in that environment and install HyperFrames on the host:

```bash
conda activate perfume-video
pip install -r requirements.txt
npm install -g hyperframes
```

## Configuration

`.env.example` documents the available settings. At minimum, configure the PostgreSQL URL, Redis broker URL, LiteLLM endpoint/key, provider credentials, and the endpoint and credentials required by your S3-compatible storage integration. The sample currently includes a RustFS endpoint as a development example; adapt it for your chosen provider. Keep secrets out of Git and never commit `.env`.

## Development and tests

Backend tests:

```bash
pytest -q
```

Frontend checks:

```bash
cd frontend
npm run build
npm run lint
```

Integration tests that require external media or model services are marked separately. Read the test module and service configuration before running them.

## Current status

This project is under active development. Provider adapters, media-storage integration, authentication, and UI behavior may evolve. Before deploying to production, review the configuration, secure the API, configure private buckets and lifecycle policies, and validate every generation provider in your environment.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the GitHub Flow, testing, pull-request, and security-reporting guidelines.

## License

Licensed under the [Apache License 2.0](LICENSE).
