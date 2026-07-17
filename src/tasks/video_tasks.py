import asyncio
import datetime as _dt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import NullPool
from src.config import settings
from src.media.rustfs import create_rustfs_storage
from src.services.media_service import MediaService
from src.tasks.celery_app import celery_app
from src.models.task import VideoTask
from src.models.script import Script
from src.models.generated_image import GeneratedImage
from src.models.viral_analysis import ViralAnalysis
from src.agents.state import VideoAgentState
from src.ws.progress import progress_manager
from src.agents.checkpoint import get_checkpointer
from src.tasks.execution import (
    ARTIFACT_STATE_KEYS, NodeExecutionError, execution_stage, execution_timing,
    reset_execution_reporter, set_execution_reporter, stage_for_node,
)

# Celery invokes each task through asyncio.run(), creating a new event loop.
# Asyncpg connections cannot move between those loops, so this worker must not
# retain pooled connections across task invocations.
engine = create_async_engine(settings.database_url, poolclass=NullPool)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _fetch_provider_media(url: str) -> tuple[bytes, str]:
    from pathlib import Path
    import httpx

    if not url.startswith(("http://", "https://")):
        path = Path(url)
        return path.read_bytes(), "video/mp4"
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.content, response.headers.get("content-type", "application/octet-stream")


def _get_graph(task_type: str):
    """Get the pre-compiled graph structure (checkpointer-free, for inspection only)."""
    if task_type == "promo":
        from src.agents.promo_graph import promo_graph
        return promo_graph
    elif task_type == "viral":
        from src.agents.viral_graph import viral_graph
        return viral_graph
    elif task_type == "personify":
        from src.agents.personify_graph import personify_graph
        return personify_graph
    raise ValueError(f"Unknown task type: {task_type}")


async def _make_runnable_graph(task_type: str, skip_interrupts: set[str] | None = None):
    """Recompile the graph with MemorySaver checkpointer for actual execution."""
    from langgraph.checkpoint.memory import MemorySaver
    checkpointer = MemorySaver()
    skip = skip_interrupts or set()

    if task_type == "promo":
        from src.agents.promo_graph import build_promo_graph
        interrupts = ["wait_script_review", "wait_image_review"]
        return build_promo_graph(checkpointer=checkpointer, interrupt_before=[i for i in interrupts if i not in skip])
    elif task_type == "viral":
        from src.agents.viral_graph import build_viral_graph
        interrupts = ["wait_viral_confirm", "wait_script_review", "wait_image_review"]
        return build_viral_graph(checkpointer=checkpointer, interrupt_before=[i for i in interrupts if i not in skip])
    elif task_type == "personify":
        from src.agents.personify_graph import build_personify_graph
        interrupts = ["wait_character_review", "wait_script_review"]
        return build_personify_graph(checkpointer=checkpointer, interrupt_before=[i for i in interrupts if i not in skip])
    raise ValueError(f"Unknown task type: {task_type}")


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def run_video_task(self, task_id: str):
    return asyncio.run(_async_run(task_id, self.request.id))


async def _async_run(task_id: str, celery_task_id: str):
    graph = None
    progress_log: list = []
    last_node = None
    attempt_number = 1
    node_started_at = _dt.datetime.utcnow()
    reporter_token = None
    import datetime as _dt
    try:
        async with SessionLocal() as db:
            result = await db.execute(select(VideoTask).where(VideoTask.id == task_id))
            task = result.scalar_one()
            # A failed task starts a new Execution Attempt; ordinary resumes
            # after a review stay within the existing attempt.
            previous_attempts = [entry.get("attempt", 1) for entry in task.progress_log or []]
            attempt_number = max(previous_attempts, default=0) + (1 if task.status == "failed" else 0)
            attempt_number = max(attempt_number, 1)
            media = MediaService(db, create_rustfs_storage(settings))
            snapshot = task.product_snapshot
            if snapshot.get("version") != 1:
                raise ValueError("Invalid product snapshot")

            initial_state: VideoAgentState = {
                "task_id": str(task.id),
                "product_id": str(task.product_id or snapshot["id"]),
                "product_info": snapshot,
                "task_type": task.type,
                "image_count": task.image_count,
                "viral_url": "",
                "script_content": "", "edited_script_content": "", "image_prompts": [],
                "voiceover_text": "", "generated_images": [], "video_clips": [],
                "tts_audio_url": "", "tts_words": [], "lipsync_video_url": "",
                "character_image_url": "", "viral_analysis": {},
                "hyperframes_html": "", "final_video_path": "",
                "review_approved": False, "script_approved": False,
                "images_approved": False, "messages": [],
            }

            if task.type == "viral":
                v_result = await db.execute(select(ViralAnalysis).where(ViralAnalysis.task_id == task.id))
                va = v_result.scalar_one_or_none()
                if va:
                    initial_state["viral_url"] = va.source_url

            # Restore previously-completed state on retry
            script_result = await db.execute(select(Script).where(Script.task_id == task_id))
            db_script = script_result.scalar_one_or_none()
            if db_script:
                initial_state["script_content"] = db_script.content or ""
                initial_state["edited_script_content"] = db_script.edited_content or ""
                initial_state["image_prompts"] = db_script.image_prompts or []
                initial_state["voiceover_text"] = db_script.voiceover_text or ""

            img_result = await db.execute(
                select(GeneratedImage).where(GeneratedImage.task_id == task_id).order_by(GeneratedImage.sort_order)
            )
            db_images = img_result.scalars().all()
            if db_images:
                initial_state["generated_images"] = [
                    {
                        "sort_order": img.sort_order,
                        "image_url": await media.access_url(img.asset_id, task.user_id),
                        "asset_id": str(img.asset_id),
                        "status": img.status,
                    }
                    for img in db_images
                    if img.asset_id
                ]

            # Restore outputs of completed expensive nodes. These snapshots
            # make retries resume at the failed small step instead of
            # regenerating already-successful video/audio assets.
            for entry in task.progress_log or []:
                if entry.get("status") != "ok":
                    continue
                saved_state = entry.get("state") or {}
                for key in ARTIFACT_STATE_KEYS:
                    if key in saved_state:
                        initial_state[key] = saved_state[key]
                if saved_state.get("video_clip_asset_ids"):
                    initial_state["video_clips"] = [
                        await media.access_url(asset_id, task.user_id)
                        for asset_id in saved_state["video_clip_asset_ids"]
                    ]
                if saved_state.get("tts_audio_asset_id"):
                    initial_state["tts_audio_url"] = await media.access_url(
                        saved_state["tts_audio_asset_id"], task.user_id
                    )
                if saved_state.get("lipsync_video_asset_id"):
                    initial_state["lipsync_video_url"] = await media.access_url(
                        saved_state["lipsync_video_asset_id"], task.user_id
                    )
                if saved_state.get("character_image_asset_id"):
                    initial_state["character_image_url"] = await media.access_url(
                        saved_state["character_image_asset_id"], task.user_id
                    )

            # Set approval flags to skip completed wait nodes on retry
            if db_script and db_script.status == "approved":
                initial_state["script_approved"] = True
            if db_images and all(img.status == "approved" for img in db_images):
                initial_state["images_approved"] = True

            # Determine starting step
            if task.status == "failed":
                if db_images and any(img.status == "approved" for img in db_images):
                    task.status = "image_review"  # Re-review or generate remaining
                elif db_script and db_script.status == "approved":
                    task.status = "imaging"
                elif db_script:
                    task.status = "script_review"
                else:
                    task.status = "scripting"
            elif task.status == "pending":
                task.status = "scripting"

            task.error_message = None
            task.current_step = None
            task.celery_task_id = celery_task_id
            await db.commit()

        # Skip interrupts for steps already completed
        skip = set()
        if initial_state.get("script_approved"):
            skip.add("wait_script_review")
        if initial_state.get("images_approved"):
            skip.add("wait_image_review")

        graph = await _make_runnable_graph(task.type, skip)
        config = {"configurable": {"thread_id": task_id}}

        # Try resume from checkpoint first; fall back to fresh start
        try:
            stream = graph.astream(None, config)
            await stream.__anext__()  # will raise if no checkpoint
            stream = graph.astream(None, config)  # restart the stream properly
        except Exception:
            stream = graph.astream(initial_state, config)

        async with SessionLocal() as db:
            t = (await db.execute(select(VideoTask).where(VideoTask.id == task_id))).scalar_one()
            # Keep the execution history across retries/resumes and append new
            # entries as the graph advances. The UI polls this field while the
            # task is running, so clearing it here made the log disappear.
            progress_log = list(t.progress_log or [])

        async def record_substep_start(node_name: str) -> None:
            started_at = _dt.datetime.utcnow().isoformat() + "Z"
            entry = {
                "attempt": attempt_number,
                "stage": execution_stage(node_name),
                "step": node_name,
                "time": started_at,
                "started_at": started_at,
                "status": "running",
            }
            async with SessionLocal() as db:
                t = (await db.execute(
                    select(VideoTask).where(VideoTask.id == task_id).with_for_update()
                )).scalar_one()
                t.progress_log = list(t.progress_log or []) + [entry]
                await db.commit()
            await progress_manager.send_progress(task_id, {"status": execution_stage(node_name)})

        reporter_token = set_execution_reporter(record_substep_start)
        node_started_at = _dt.datetime.utcnow()
        async for event in stream:
            for node_name, node_output in event.items():
                # Track last meaningful node for interrupt detection
                if node_name == "__interrupt__":
                    # Map to the correct review state based on what ran last
                    review_map = {
                        "generate_script": "script_review",
                        "generate_rewritten_script": "script_review",
                        "generate_images": "image_review",
                        "generate_character": "character_review",
                    }
                    next_review = review_map.get(last_node, "script_review")
                    async with SessionLocal() as db:
                        t = (await db.execute(select(VideoTask).where(VideoTask.id == task_id))).scalar_one()
                        t.status = next_review
                        wait_entry = {
                            "attempt": attempt_number,
                            "stage": execution_stage(last_node),
                            "step": f"wait_{next_review}",
                            "time": _dt.datetime.utcnow().isoformat() + "Z",
                            "started_at": _dt.datetime.utcnow().isoformat() + "Z",
                            "status": "waiting",
                            "summary": "Waiting for user review",
                        }
                        t.progress_log = list(t.progress_log or []) + [wait_entry]
                        await db.commit()
                    await progress_manager.send_progress(task_id, {"status": next_review})
                    reset_execution_reporter(reporter_token)
                    reporter_token = None
                    return

                if node_output is None:
                    continue

                last_node = node_name

                # Persist agent outputs to DB and record progress
                await _persist_node_output(task_id, node_name, node_output)
                finished_at = _dt.datetime.utcnow()
                started_at = node_started_at
                entry = {
                    "attempt": attempt_number,
                    "stage": execution_stage(node_name),
                    "step": node_name,
                    "time": finished_at.isoformat() + "Z",
                    "started_at": started_at.isoformat() + "Z",
                    "finished_at": finished_at.isoformat() + "Z",
                    "duration_ms": execution_timing(started_at.isoformat() + "Z", finished_at.isoformat() + "Z"),
                    "status": "ok",
                }
                # Summarize output for display
                if node_name in ("generate_script", "generate_rewritten_script"):
                    entry["summary"] = f"Script generated ({len(node_output.get('script_content',''))} chars)"
                elif node_name == "generate_images":
                    imgs = node_output.get("generated_images", [])
                    entry["summary"] = f"Images: {len(imgs)} generated/reused"
                elif node_name == "generate_video_clips":
                    clips = node_output.get("video_clips", [])
                    entry["summary"] = f"Video clips: {len(clips)} generated"
                elif node_name == "generate_voiceover":
                    entry["summary"] = "TTS audio generated"
                elif node_name in ("composite_video", "composite"):
                    entry["summary"] = f"Final video: {node_output.get('final_video_path', 'N/A')[:60]}"
                saved_state = {key: node_output[key] for key in ARTIFACT_STATE_KEYS if key in node_output}
                if saved_state:
                    entry["state"] = saved_state
                node_started_at = finished_at
                async with SessionLocal() as db:
                    t = (await db.execute(
                        select(VideoTask).where(VideoTask.id == task_id).with_for_update()
                    )).scalar_one()
                    latest_log = list(t.progress_log or [])
                    for index in range(len(latest_log) - 1, -1, -1):
                        candidate = latest_log[index]
                        if candidate.get("attempt") == attempt_number and candidate.get("step") == node_name and candidate.get("status") == "running":
                            entry["started_at"] = candidate["started_at"]
                            entry["duration_ms"] = execution_timing(entry["started_at"], entry["finished_at"])
                            latest_log[index] = entry
                            break
                    else:
                        latest_log.append(entry)
                    t.progress_log = latest_log
                    progress_log = latest_log
                    await db.commit()

        # Graph completed without hitting an interrupt — collect final video path
        final_video = ""
        async for event in graph.astream(None, config):
            for node_name, node_output in event.items():
                if node_output and node_output.get("final_video_path"):
                    final_video = node_output["final_video_path"]

        async with SessionLocal() as db:
            t = (await db.execute(select(VideoTask).where(VideoTask.id == task_id))).scalar_one()
            t.status = "done"
            await db.commit()
        await progress_manager.send_progress(task_id, {"status": "done", "video_url": final_video})
        reset_execution_reporter(reporter_token)
        reporter_token = None

    except Exception as e:
        if reporter_token is not None:
            reset_execution_reporter(reporter_token)
            reporter_token = None
        failed_node = e.node_name if isinstance(e, NodeExecutionError) else last_node or "unknown"
        root_error = e.__cause__ if isinstance(e, NodeExecutionError) and e.__cause__ else e
        error_entry = {
            "attempt": attempt_number,
            "stage": execution_stage(failed_node),
            "step": failed_node,
            "time": _dt.datetime.utcnow().isoformat() + "Z",
            "finished_at": _dt.datetime.utcnow().isoformat() + "Z",
            "status": "error",
            "summary": f"{type(root_error).__name__}: {str(root_error)[:300]}"
        }
        async with SessionLocal() as db:
            t = (await db.execute(
                select(VideoTask).where(VideoTask.id == task_id).with_for_update()
            )).scalar_one()
            t.status = "failed"
            t.current_step = stage_for_node(failed_node)
            t.error_message = f"{type(root_error).__name__}: {root_error}"
            latest_log = list(t.progress_log or [])
            for index in range(len(latest_log) - 1, -1, -1):
                candidate = latest_log[index]
                if candidate.get("attempt") == attempt_number and candidate.get("step") == failed_node and candidate.get("status") == "running":
                    error_entry["started_at"] = candidate["started_at"]
                    error_entry["duration_ms"] = execution_timing(error_entry["started_at"], error_entry["finished_at"])
                    latest_log[index] = error_entry
                    break
            else:
                latest_log.append(error_entry)
            t.progress_log = latest_log
            await db.commit()
        await progress_manager.send_progress(task_id, {"status": "failed", "error": str(root_error)})
        raise


async def _persist_node_output(task_id: str, node_name: str, output: dict):
    """Persist agent node outputs to their corresponding DB tables."""
    async with SessionLocal() as db:
        if node_name == "generate_script" or node_name == "generate_rewritten_script":
            stmt = select(Script).where(Script.task_id == task_id)
            result = await db.execute(stmt)
            script = result.scalar_one_or_none()
            if not script:
                script = Script(task_id=task_id, content="", status="pending_review")
                db.add(script)
            script.content = output.get("script_content", script.content)
            script.voiceover_text = output.get("voiceover_text", script.voiceover_text)
            if output.get("image_prompts"):
                script.image_prompts = output["image_prompts"]
            await db.commit()

        elif node_name == "generate_images":
            # Upsert images — preserve approved status on retry
            existing = (await db.execute(select(GeneratedImage).where(GeneratedImage.task_id == task_id))).scalars().all()
            existing_map = {img.sort_order: img for img in existing}
            task = (await db.execute(select(VideoTask).where(VideoTask.id == task_id))).scalar_one()
            media = MediaService(db, create_rustfs_storage(settings))
            for img_data in output.get("generated_images", []):
                sort_order = img_data.get("sort_order", 0)
                old = existing_map.get(sort_order)
                asset_id = img_data.get("asset_id")
                if not asset_id and img_data.get("image_url"):
                    asset = await media.create_from_remote(
                        owner_user_id=task.user_id,
                        category="generated_image",
                        source_url=img_data["image_url"],
                        filename=f"{task_id}-{sort_order}.bin",
                        fetch=_fetch_provider_media,
                        task_id=task.id,
                        source_provider="image-provider",
                        idempotency_key=f"task:{task_id}:generated-image:{sort_order}",
                    )
                    asset_id = asset.id
                if old:
                    old.asset_id = asset_id or old.asset_id
                    old.status = img_data.get("status", old.status)
                else:
                    db.add(GeneratedImage(
                        task_id=task_id, prompt="",
                        image_url=None,
                        asset_id=asset_id,
                        sort_order=sort_order,
                        status=img_data.get("status", "pending_review"),
                    ))
            await db.commit()

        elif node_name == "generate_character":
            if output.get("character_image_url"):
                task = (await db.execute(select(VideoTask).where(VideoTask.id == task_id))).scalar_one()
                media = MediaService(db, create_rustfs_storage(settings))
                asset = await media.create_from_remote(
                    owner_user_id=task.user_id,
                    category="character_image",
                    source_url=output["character_image_url"],
                    filename=f"{task_id}-character.bin",
                    fetch=_fetch_provider_media,
                    task_id=task.id,
                    source_provider="image-provider",
                    idempotency_key=f"task:{task_id}:character-image",
                )
                gi = GeneratedImage(
                    task_id=task_id, prompt="character",
                    image_url=None,
                    asset_id=asset.id,
                    sort_order=0, status="pending_review",
                )
                db.add(gi)
                await db.commit()

        elif node_name == "generate_video_clips":
            if output.get("video_clips"):
                t = (await db.execute(select(VideoTask).where(VideoTask.id == task_id))).scalar_one()
                media = MediaService(db, create_rustfs_storage(settings))
                asset_ids = []
                for index, url in enumerate(output["video_clips"]):
                    asset = await media.create_from_remote(
                        owner_user_id=t.user_id, category="video_clip",
                        source_url=url, filename=f"{task_id}-clip-{index}.mp4",
                        fetch=_fetch_provider_media, task_id=t.id,
                        source_provider="video-provider",
                        idempotency_key=f"task:{task_id}:video-clip:{index}",
                    )
                    asset_ids.append(str(asset.id))
                output["video_clip_asset_ids"] = asset_ids
                t.status = "video_gen"
                await db.commit()

        elif node_name in ("generate_voiceover", "generate_clips_and_voiceover", "generate_tts_and_lipsync"):
            if output.get("tts_audio_url"):
                t = (await db.execute(select(VideoTask).where(VideoTask.id == task_id))).scalar_one()
                media = MediaService(db, create_rustfs_storage(settings))
                asset = await media.create_from_remote(
                    owner_user_id=t.user_id, category="tts_audio",
                    source_url=output["tts_audio_url"], filename=f"{task_id}-voice.wav",
                    fetch=_fetch_provider_media, task_id=t.id,
                    source_provider="tts-provider",
                    idempotency_key=f"task:{task_id}:tts-audio",
                )
                output["tts_audio_asset_id"] = str(asset.id)
                if output.get("lipsync_video_url"):
                    lipsync = await media.create_from_remote(
                        owner_user_id=t.user_id, category="lipsync_video",
                        source_url=output["lipsync_video_url"],
                        filename=f"{task_id}-lipsync.mp4",
                        fetch=_fetch_provider_media, task_id=t.id,
                        source_provider="lipsync-provider",
                        idempotency_key=f"task:{task_id}:lipsync-video",
                    )
                    output["lipsync_video_asset_id"] = str(lipsync.id)
                t.status = "compositing"
                await db.commit()

        elif node_name in ("composite_video", "composite"):
            if output.get("final_video_path"):
                t = (await db.execute(select(VideoTask).where(VideoTask.id == task_id))).scalar_one()
                media = MediaService(db, create_rustfs_storage(settings))
                asset = await media.create_from_remote(
                    owner_user_id=t.user_id, category="final_video",
                    source_url=output["final_video_path"], filename=f"{task_id}-final.mp4",
                    fetch=_fetch_provider_media, task_id=t.id,
                    source_provider="renderer",
                    idempotency_key=f"task:{task_id}:final-video",
                )
                output["final_video_asset_id"] = str(asset.id)
                t.result_video_asset_id = asset.id
                t.result_video_url = None
                t.status = "done"
                await db.commit()
