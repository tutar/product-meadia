import asyncio
import datetime as _dt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from src.config import settings
from src.tasks.celery_app import celery_app
from src.models.task import VideoTask
from src.models.script import Script
from src.models.generated_image import GeneratedImage
from src.models.viral_analysis import ViralAnalysis
from src.agents.state import VideoAgentState
from src.ws.progress import progress_manager
from src.agents.checkpoint import get_checkpointer
from src.tasks.execution import ARTIFACT_STATE_KEYS, NodeExecutionError, stage_for_node

engine = create_async_engine(settings.database_url)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


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
    import datetime as _dt
    try:
        async with SessionLocal() as db:
            result = await db.execute(select(VideoTask).where(VideoTask.id == task_id))
            task = result.scalar_one()
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
                    {"sort_order": img.sort_order, "image_url": img.image_url, "status": img.status}
                    for img in db_images
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
                        await db.commit()
                    await progress_manager.send_progress(task_id, {"status": next_review})
                    return

                if node_output is None:
                    continue

                last_node = node_name

                # Persist agent outputs to DB and record progress
                await _persist_node_output(task_id, node_name, node_output)
                entry = {"step": node_name, "time": _dt.datetime.utcnow().isoformat() + "Z", "status": "ok"}
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
                progress_log.append(entry)
                async with SessionLocal() as db:
                    t = (await db.execute(
                        select(VideoTask).where(VideoTask.id == task_id).with_for_update()
                    )).scalar_one()
                    latest_log = list(t.progress_log or [])
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
            if final_video:
                t.result_video_url = final_video
            await db.commit()
        await progress_manager.send_progress(task_id, {"status": "done", "video_url": final_video})

    except Exception as e:
        failed_node = e.node_name if isinstance(e, NodeExecutionError) else last_node or "unknown"
        root_error = e.__cause__ if isinstance(e, NodeExecutionError) and e.__cause__ else e
        error_entry = {
            "step": failed_node,
            "time": _dt.datetime.utcnow().isoformat() + "Z",
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
            for img_data in output.get("generated_images", []):
                sort_order = img_data.get("sort_order", 0)
                old = existing_map.get(sort_order)
                if old:
                    old.image_url = img_data.get("image_url", old.image_url)
                    old.status = img_data.get("status", old.status)
                else:
                    db.add(GeneratedImage(
                        task_id=task_id, prompt="",
                        image_url=img_data.get("image_url", ""),
                        sort_order=sort_order,
                        status=img_data.get("status", "pending_review"),
                    ))
            await db.commit()

        elif node_name == "generate_character":
            if output.get("character_image_url"):
                gi = GeneratedImage(
                    task_id=task_id, prompt="character",
                    image_url=output["character_image_url"],
                    sort_order=0, status="pending_review",
                )
                db.add(gi)
                await db.commit()

        elif node_name == "generate_video_clips":
            # Persist video clip URLs for retry resilience
            if output.get("video_clips"):
                t = (await db.execute(select(VideoTask).where(VideoTask.id == task_id))).scalar_one()
                t.status = "video_gen"
                await db.commit()

        elif node_name == "generate_voiceover":
            if output.get("tts_audio_url"):
                t = (await db.execute(select(VideoTask).where(VideoTask.id == task_id))).scalar_one()
                t.status = "compositing"
                await db.commit()

        elif node_name in ("composite_video", "composite"):
            if output.get("final_video_path"):
                t = (await db.execute(select(VideoTask).where(VideoTask.id == task_id))).scalar_one()
                t.result_video_url = output["final_video_path"]
                t.status = "done"
                await db.commit()
