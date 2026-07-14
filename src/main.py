from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from src.auth.routes import router as auth_router
from src.api.products import router as products_router
from src.api.tasks import router as tasks_router
from src.ws.progress import progress_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

app = FastAPI(title="Perfume Video API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/api/v1")
app.include_router(products_router, prefix="/api/v1")
app.include_router(tasks_router, prefix="/api/v1")


@app.websocket("/ws/tasks/{task_id}")
async def ws_progress(websocket: WebSocket, task_id: str):
    await progress_manager.connect(task_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except Exception:
        progress_manager.disconnect(task_id, websocket)
