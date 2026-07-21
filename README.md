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
                     +---- LiteLLM Python SDK -> user-configured model services
                     +---- S3-compatible object storage
```

PostgreSQL, Redis, and an S3-compatible object store are deployment prerequisites. The repository does not bundle those infrastructure services. Video Tasks call user-configured model services directly through the LiteLLM Python SDK; this model-selection flow does not require a LiteLLM Proxy. RustFS is one possible S3-compatible implementation, not a hard requirement.

Generated images, audio, and video should be persisted in private object storage. Application records keep durable object identifiers; clients receive short-lived, read-only presigned URLs when media needs to be viewed or downloaded.

## Prerequisites

- Python 3.11+
- Node.js 22+
- HyperFrames CLI (`npm install -g hyperframes`) for final video rendering
- PostgreSQL
- Redis
- An S3-compatible object storage service

Each user maintains model endpoints and credentials in **Preferences → Model configurations**, rather than deployment environment variables. A private OpenAI-compatible endpoint may need no credential; cloud providers normally use the user's BYOK.

## Quick start

1. Prepare the external services above and make sure the local API and Celery worker can reach them.

2. Configure the environment:

   ```bash
   cp .env.example .env
   # Edit .env: database, Redis, and object-storage settings
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

5. After signing in, open **Preferences → Model configurations**:

   - Create a configuration from a built-in template, or choose **Configure private model** and enter an OpenAI-compatible endpoint, model ID, and supported stages.
   - Enter a BYOK when the model service requires one; leave it empty for an unauthenticated private endpoint.
   - Verify the configuration and select defaults for the required stages. A service with no safe probe establishes availability on its first real invocation.

6. Start the local Celery worker from the `perfume-video` conda environment:

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

`.env.example` documents deployment-level settings. At minimum, configure the PostgreSQL URL, Redis broker URL, and the endpoint and credentials required by your S3-compatible storage integration. Model endpoints and BYOKs belong to user-owned model configurations; do not put them in `.env` or commit them to Git. The sample currently includes a RustFS endpoint as a development example; adapt it for your chosen provider.

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
