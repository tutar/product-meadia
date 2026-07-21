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
from src.models.creative_brief import CreativeBrief
from src.models.shot_plan import ShotPlan
from src.models.editing_blueprint import EditingBlueprint
from src.models.generated_image import GeneratedImage
from src.models.video_candidate import VideoCandidate
from src.models.review_feedback import ReviewFeedback
from src.models.user import User
from src.models.viral_analysis import ViralAnalysis
from src.agents.state import VideoAgentState
from src.ws.progress import progress_manager
from src.agents.checkpoint import get_checkpointer
from src.tasks.execution import (
    ARTIFACT_STATE_KEYS, NodeExecutionError, execution_stage, execution_timing,
    next_execution_attempt, reset_execution_reporter, review_status_for_node,
    safe_error_summary, set_execution_reporter, stage_for_node,
)
from src.tasks.generation_records import generation_substep, reset_generation_recorder, set_generation_recorder
from src.models.generation_record import GenerationRecord
from src.models.media_asset import MediaAsset
from src.models.composition_source import CompositionSourceSnapshot
from src.services.composition_sources import canonicalize_html, html_checksum

# Celery invokes each task through asyncio.run(), creating a new event loop.
# Asyncpg connections cannot move between those loops, so this worker must not
# retain pooled connections across task invocations.
engine = create_async_engine(settings.database_url, poolclass=NullPool)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class TaskCancellationRequested(RuntimeError):
    pass


async def _fetch_provider_media(url: str) -> tuple[bytes, str]:
    import mimetypes
    from pathlib import Path
    import httpx

    if not url.startswith(("http://", "https://")):
        path = Path(url)
        return path.read_bytes(), mimetypes.guess_type(path.name)[0] or "application/octet-stream"
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
        interrupts = ["wait_creative_brief_review", "wait_script_review", "wait_shot_plan_review", "wait_image_review"]
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
    generation_recorder_token = None
    try:
        async with SessionLocal() as db:
            result = await db.execute(select(VideoTask).where(VideoTask.id == task_id))
            task = result.scalar_one()
            if task.status == "cancellation_requested":
                task.status = "cancelled"
                task.progress_log = list(task.progress_log or []) + [{"stage": "other", "step": "cancelled", "time": _dt.datetime.utcnow().isoformat() + "Z", "status": "ok", "summary": "Task cancelled"}]
                await db.commit()
                return
            # A failed task starts a new Execution Attempt; ordinary resumes
            # after a review stay within the existing attempt.
            attempt_number = next_execution_attempt(task.progress_log or [], is_retry=task.status == "failed")
            media = MediaService(db, create_rustfs_storage(settings))
            snapshot = task.product_snapshot
            if snapshot.get("version") != 1:
                raise ValueError("Invalid product snapshot")
            main_image_data_uri = ""
            if main_image_asset_id := snapshot.get("main_image_asset_id"):
                main_image_data_uri = await media.data_uri(main_image_asset_id, task.user_id)

            initial_state: VideoAgentState = {
                "task_id": str(task.id),
                "product_id": str(task.product_id or snapshot["id"]),
                "product_info": snapshot,
                "main_image_data_uri": main_image_data_uri,
                "task_type": task.type,
                "image_count": task.image_count,
                "creative_brief": {}, "creative_brief_approved": False,
                "shot_plan": [], "shot_plan_approved": False,
                "clip_segments": [], "editing_blueprint": [],
                "viral_url": "",
                "script_content": "", "edited_script_content": "", "image_prompts": [],
                "voiceover_text": "", "generated_images": [], "video_clips": [], "video_clips_reused": False,
                "tts_audio_url": "", "tts_duration_seconds": 0.0, "tts_generation_key": "initial", "tts_words": [], "lipsync_video_url": "",
                "character_image_url": "", "viral_analysis": {},
                "hyperframes_html": "", "final_video_path": "", "composition_source_snapshot_id": "",
                "review_approved": False, "script_approved": False,
                "images_approved": False, "character_approved": False,
                "review_feedback": [], "video_feedback_by_sort_order": {}, "messages": [],
            }

            if task.type == "viral":
                v_result = await db.execute(select(ViralAnalysis).where(ViralAnalysis.task_id == task.id))
                va = v_result.scalar_one_or_none()
                if va:
                    initial_state["viral_url"] = va.source_url

            # Restore previously-completed state on retry
            db_brief = await db.scalar(select(CreativeBrief).where(CreativeBrief.task_id == task.id))
            if db_brief:
                initial_state["creative_brief"] = db_brief.content or {}
                initial_state["creative_brief_approved"] = db_brief.status == "approved"
            db_shot_plan = await db.scalar(select(ShotPlan).where(ShotPlan.task_id == task.id))
            if db_shot_plan:
                initial_state["shot_plan"] = db_shot_plan.shots or []
                initial_state["shot_plan_approved"] = db_shot_plan.status == "approved"
            script_result = await db.execute(select(Script).where(Script.task_id == task_id))
            db_script = script_result.scalar_one_or_none()
            if db_script:
                if db_script.status != "rejected":
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
                        "id": str(img.id),
                        "prompt": img.prompt,
                        "image_url": await media.access_url(img.asset_id, task.user_id),
                        "asset_id": str(img.asset_id),
                        "status": img.status,
                        **(img.generation_context or {}),
                    }
                    for img in db_images
                    if img.asset_id
                ]

            character = next((img for img in db_images if img.prompt == "character"), None)
            if character and character.status == "approved":
                initial_state["character_approved"] = True
                if character.asset_id:
                    initial_state["character_image_url"] = await media.access_url(character.asset_id, task.user_id)

            feedback = (await db.scalars(select(ReviewFeedback).where(
                ReviewFeedback.task_id == task.id,
                ReviewFeedback.consumed.is_(False),
            ).order_by(ReviewFeedback.created_at))).all()
            initial_state["review_feedback"] = [
                {"id": str(item.id), "target_type": item.target_type,
                 "target_id": str(item.target_id) if item.target_id else None,
                 "content": item.content}
                for item in feedback
            ]
            for item in feedback:
                if item.target_type != "video_clip" or not item.target_id:
                    continue
                candidate = await db.scalar(select(VideoCandidate).where(VideoCandidate.id == item.target_id))
                if candidate:
                    initial_state["video_feedback_by_sort_order"][candidate.sort_order] = item.content

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
                elif db_shot_plan and db_shot_plan.status == "approved":
                    task.status = "imaging"
                elif db_script and db_script.status == "approved":
                    task.status = "planning"
                elif db_script:
                    task.status = "script_review"
                elif db_brief and db_brief.status == "approved":
                    task.status = "scripting"
                else:
                    task.status = "planning"
            elif task.status == "pending":
                task.status = "planning"

            task.error_message = None
            task.current_step = None
            task.celery_task_id = celery_task_id
            await db.commit()

        # Skip interrupts for steps already completed
        skip = set()
        if initial_state.get("script_approved"):
            skip.add("wait_script_review")
        if initial_state.get("creative_brief_approved"):
            skip.add("wait_creative_brief_review")
        if initial_state.get("shot_plan_approved"):
            skip.add("wait_shot_plan_review")
        if initial_state.get("images_approved"):
            skip.add("wait_image_review")
        if initial_state.get("character_approved"):
            skip.add("wait_character_review")

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
                if t.status == "cancellation_requested":
                    raise TaskCancellationRequested()
                t.progress_log = list(t.progress_log or []) + [entry]
                await db.commit()
            await progress_manager.send_progress(task_id, {"status": execution_stage(node_name)})

        async def persist_generation_record(provider, model, parameters, normalized_input, normalized_output, provider_payload):
            substep = generation_substep()
            if not substep:
                return
            async with SessionLocal() as record_db:
                task_snapshot = await record_db.scalar(select(VideoTask.product_snapshot).where(VideoTask.id == task_id))
                input_asset_ids = [asset_id for asset_id in [
                    (task_snapshot or {}).get("main_image_asset_id"),
                    *((task_snapshot or {}).get("packaging_image_asset_ids") or []),
                ] if asset_id]
                assets = (await record_db.scalars(select(MediaAsset).where(MediaAsset.id.in_(input_asset_ids)))).all() if input_asset_ids else []
                normalized_input = {
                    **normalized_input,
                    "media_assets": [{"id": str(asset.id), "checksum": asset.checksum} for asset in assets],
                }
                record_db.add(GenerationRecord(
                    task_id=task_id, stage=execution_stage(substep), substep=substep,
                    attempt=attempt_number, provider=provider, model=model, parameters=parameters,
                    normalized_input=normalized_input, normalized_output=normalized_output,
                    provider_payload=provider_payload,
                    provenance={"workflow_commit": settings.git_commit, "prompt_template_hash": parameters.get("prompt_template_hash")},
                ))
                await record_db.commit()

        generation_recorder_token = set_generation_recorder(persist_generation_record)
        reporter_token = set_execution_reporter(record_substep_start)
        node_started_at = _dt.datetime.utcnow()
        async for event in stream:
            for node_name, node_output in event.items():
                # Track last meaningful node for interrupt detection
                if node_name == "__interrupt__":
                    # Map to the correct review state based on what ran last
                    next_review = review_status_for_node(last_node)
                    async with SessionLocal() as db:
                        t = (await db.execute(select(VideoTask).where(VideoTask.id == task_id))).scalar_one()
                        user = await db.scalar(select(User).where(User.id == t.user_id))
                        auto_approve = (
                            last_node in ("generate_script", "generate_rewritten_script") and user.auto_approve_script
                        ) or (
                            last_node in ("generate_images", "generate_character") and user.auto_approve_images
                        )
                        if auto_approve:
                            if last_node in ("generate_script", "generate_rewritten_script"):
                                script = await db.scalar(select(Script).where(Script.task_id == task_id))
                                if script:
                                    script.status = "approved"
                                t.status = "planning"
                            else:
                                images = (await db.scalars(select(GeneratedImage).where(GeneratedImage.task_id == task_id))).all()
                                for image in images:
                                    image.status = "approved"
                                t.status = "video_gen"
                            t.progress_log = list(t.progress_log or []) + [{
                                "attempt": attempt_number, "stage": execution_stage(last_node),
                                "step": f"wait_{next_review}", "time": _dt.datetime.utcnow().isoformat() + "Z",
                                "status": "ok", "summary": "Automatically approved by user preference",
                            }]
                            await db.commit()
                            from src.tasks.video_tasks import run_video_task
                            run_video_task.delay(task_id)
                            reset_execution_reporter(reporter_token)
                            reporter_token = None
                            reset_generation_recorder(generation_recorder_token)
                            generation_recorder_token = None
                            return
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
                elif node_name == "render_composition":
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

                # Video and final composition are explicit review boundaries.
                # Their persisted candidates let a later resume reuse approved inputs.
                if (node_name == "generate_video_clips" and not node_output.get("video_clips_reused")) or node_name == "render_composition":
                    reset_execution_reporter(reporter_token)
                    reporter_token = None
                    return

        # Graph completed without hitting an interrupt — collect final video path
        final_video = ""
        async for event in graph.astream(None, config):
            for node_name, node_output in event.items():
                if node_output and node_output.get("final_video_path"):
                    final_video = node_output["final_video_path"]

        async with SessionLocal() as db:
            t = (await db.execute(select(VideoTask).where(VideoTask.id == task_id))).scalar_one()
            if t.status == "cancellation_requested":
                t.status = "cancelled"
                t.progress_log = list(t.progress_log or []) + [{"stage": "other", "step": "cancelled", "time": _dt.datetime.utcnow().isoformat() + "Z", "status": "ok", "summary": "Task cancelled"}]
                await db.commit()
                return
            t.status = "done"
            await db.commit()
        await progress_manager.send_progress(task_id, {"status": "done", "video_url": final_video})
        reset_execution_reporter(reporter_token)
        reporter_token = None
        reset_generation_recorder(generation_recorder_token)
        generation_recorder_token = None

    except TaskCancellationRequested:
        async with SessionLocal() as db:
            t = (await db.execute(select(VideoTask).where(VideoTask.id == task_id))).scalar_one()
            t.status = "cancelled"
            t.progress_log = list(t.progress_log or []) + [{"stage": "other", "step": "cancelled", "time": _dt.datetime.utcnow().isoformat() + "Z", "status": "ok", "summary": "Task cancelled"}]
            await db.commit()
        await progress_manager.send_progress(task_id, {"status": "cancelled"})
        return
    except Exception as e:
        if reporter_token is not None:
            reset_execution_reporter(reporter_token)
            reporter_token = None
        if generation_recorder_token is not None:
            reset_generation_recorder(generation_recorder_token)
            generation_recorder_token = None
        failed_node = e.node_name if isinstance(e, NodeExecutionError) else last_node or "unknown"
        root_error = e.__cause__ if isinstance(e, NodeExecutionError) and e.__cause__ else e
        error_entry = {
            "attempt": attempt_number,
            "stage": execution_stage(failed_node),
            "step": failed_node,
            "time": _dt.datetime.utcnow().isoformat() + "Z",
            "finished_at": _dt.datetime.utcnow().isoformat() + "Z",
            "status": "error",
            "summary": safe_error_summary(root_error)
        }
        async with SessionLocal() as db:
            t = (await db.execute(
                select(VideoTask).where(VideoTask.id == task_id).with_for_update()
            )).scalar_one()
            t.status = "failed"
            t.current_step = stage_for_node(failed_node)
            t.error_message = safe_error_summary(root_error)
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
        feedback_targets = {
            "generate_creative_brief": "creative_brief",
            "generate_script": "script",
            "generate_rewritten_script": "script",
            "generate_shot_plan": "shot_plan",
            "generate_images": "image",
            "generate_character": "character",
            "generate_video_clips": "video_clip",
            "generate_clips_and_voiceover": "video_clip",
            "composite_video": "composition",
            "composite": "composition",
        }
        feedback_target = feedback_targets.get(node_name)
        if feedback_target:
            items = (await db.scalars(select(ReviewFeedback).where(
                ReviewFeedback.task_id == task_id,
                ReviewFeedback.target_type == feedback_target,
                ReviewFeedback.consumed.is_(False),
            ))).all()
            for item in items:
                item.consumed = True
        if node_name == "generate_creative_brief":
            brief = await db.scalar(select(CreativeBrief).where(CreativeBrief.task_id == task_id))
            if not brief:
                brief = CreativeBrief(task_id=task_id, content={}, status="pending_review")
                db.add(brief)
            brief.content = output.get("creative_brief", brief.content)
            await db.commit()

        elif node_name == "generate_shot_plan":
            plan = await db.scalar(select(ShotPlan).where(ShotPlan.task_id == task_id))
            if not plan:
                plan = ShotPlan(task_id=task_id, shots=[], status="pending_review")
                db.add(plan)
            plan.shots = output.get("shot_plan", plan.shots)
            await db.commit()

        elif node_name == "generate_script" or node_name == "generate_rewritten_script":
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
                    old.prompt = img_data.get("image_prompt", old.prompt)
                    old.generation_context = {
                        key: img_data[key] for key in ("shot_index", "segment_index", "segment_count", "target_duration_seconds", "voiceover_text")
                        if key in img_data
                    }
                else:
                    db.add(GeneratedImage(
                        task_id=task_id, prompt=img_data.get("image_prompt", ""),
                        image_url=None,
                        asset_id=asset_id,
                        sort_order=sort_order,
                        status=img_data.get("status", "pending_review"),
                        generation_context={
                            key: img_data[key] for key in ("shot_index", "segment_index", "segment_count", "target_duration_seconds", "voiceover_text")
                            if key in img_data
                        },
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
            if output.get("video_clips") and not output.get("video_clips_reused"):
                t = (await db.execute(select(VideoTask).where(VideoTask.id == task_id))).scalar_one()
                media = MediaService(db, create_rustfs_storage(settings))
                asset_ids = []
                replaced_indexes = set(output.get("regenerated_clip_indexes", []))
                indexes = sorted(replaced_indexes) if replaced_indexes else range(len(output["video_clips"]))
                for index in indexes:
                    url = output["video_clips"][index]
                    previous_all = (await db.scalars(select(VideoCandidate).where(
                        VideoCandidate.task_id == task_id,
                        VideoCandidate.kind == "clip",
                        VideoCandidate.sort_order == index,
                    ))).all()
                    asset = await media.create_from_remote(
                        owner_user_id=t.user_id, category="video_clip",
                        source_url=url, filename=f"{task_id}-clip-{index}.mp4",
                        fetch=_fetch_provider_media, task_id=t.id,
                        source_provider="video-provider",
                        idempotency_key=f"task:{task_id}:video-clip:{index}:{len(previous_all) + 1}",
                    )
                    asset_ids.append(str(asset.id))
                    previous = (await db.scalars(select(VideoCandidate).where(VideoCandidate.task_id == task_id, VideoCandidate.kind == "clip", VideoCandidate.sort_order == index, VideoCandidate.is_current.is_(True)))).all()
                    for candidate in previous:
                        candidate.is_current = False
                    db.add(VideoCandidate(
                        task_id=t.id, asset_id=asset.id, kind="clip", sort_order=index, version=len(previous_all) + 1,
                        status="pending_review",
                        generation_context=(output.get("clip_segments") or [{}] * len(output["video_clips"]))[index],
                    ))
                current_candidates = (await db.scalars(select(VideoCandidate).where(
                    VideoCandidate.task_id == task_id,
                    VideoCandidate.kind == "clip",
                    VideoCandidate.is_current.is_(True),
                ).order_by(VideoCandidate.sort_order))).all()
                output["video_clip_asset_ids"] = [str(candidate.asset_id) for candidate in current_candidates]
                t.status = "video_review"
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
                    idempotency_key=f"task:{task_id}:tts-audio:{output.get('tts_generation_key', 'initial')}",
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
            blueprint = await db.scalar(select(EditingBlueprint).where(EditingBlueprint.task_id == task_id))
            if not blueprint:
                blueprint = EditingBlueprint(task_id=task_id, entries=[])
                db.add(blueprint)
            blueprint.entries = output.get("editing_blueprint", blueprint.entries)
            t = (await db.execute(select(VideoTask).where(VideoTask.id == task_id))).scalar_one()
            media = MediaService(db, create_rustfs_storage(settings))
            clips = (await db.scalars(select(VideoCandidate).where(
                VideoCandidate.task_id == task_id,
                VideoCandidate.kind == "clip",
                VideoCandidate.is_current.is_(True),
                VideoCandidate.asset_id.is_not(None),
            ).order_by(VideoCandidate.sort_order))).all()
            audio = await db.scalar(select(MediaAsset).where(
                MediaAsset.task_id == task_id,
                MediaAsset.category == "tts_audio",
                MediaAsset.status == "available",
            ).order_by(MediaAsset.created_at.desc()))
            source = canonicalize_html(
                output["hyperframes_html"], [str(clip.asset_id) for clip in clips], str(audio.id) if audio else None
            )
            source_asset = await media.create_asset(
                owner_user_id=t.user_id,
                category="composition_source",
                data=source.canonical_html.encode("utf-8"),
                content_type="text/html; charset=utf-8",
                filename=f"{task_id}-composition-source.html",
                task_id=t.id,
                source_provider="hyperframes",
                idempotency_key=f"task:{task_id}:composition-source:{len(t.progress_log or []) + 1}",
            )
            snapshot = CompositionSourceSnapshot(
                task_id=t.id,
                asset_id=source_asset.id,
                source_kind="captured",
                canonical_html_checksum=html_checksum(source.canonical_html),
                input_asset_ids=source.input_asset_ids,
                render_spec={"hyperframes_version": "0.7.59", "fps": 30},
                provenance={"template_hash": html_checksum(source.canonical_html)},
            )
            db.add(snapshot)
            await db.flush()
            output["composition_source_snapshot_id"] = str(snapshot.id)
            await db.commit()

        elif node_name == "render_composition":
            if output.get("final_video_path"):
                t = (await db.execute(select(VideoTask).where(VideoTask.id == task_id))).scalar_one()
                media = MediaService(db, create_rustfs_storage(settings))
                candidates = (await db.scalars(select(VideoCandidate).where(
                    VideoCandidate.task_id == task_id,
                    VideoCandidate.kind == "composition",
                ))).all()
                next_version = max((candidate.version for candidate in candidates), default=0) + 1
                asset = await media.create_from_remote(
                    owner_user_id=t.user_id, category="final_video",
                    source_url=output["final_video_path"], filename=f"{task_id}-final.mp4",
                    fetch=_fetch_provider_media, task_id=t.id,
                    source_provider="renderer",
                    idempotency_key=f"task:{task_id}:final-video:{next_version}",
                )
                output["final_video_asset_id"] = str(asset.id)
                previous = [candidate for candidate in candidates if candidate.is_current]
                for candidate in previous:
                    candidate.is_current = False
                candidate = VideoCandidate(task_id=t.id, asset_id=asset.id, kind="composition", sort_order=0, version=next_version, status="pending_review")
                db.add(candidate)
                await db.flush()
                snapshot = await db.scalar(select(CompositionSourceSnapshot).where(
                    CompositionSourceSnapshot.id == output["composition_source_snapshot_id"],
                    CompositionSourceSnapshot.task_id == task_id,
                ))
                if not snapshot:
                    raise RuntimeError("composition source snapshot was not captured before render")
                snapshot.candidate_id = candidate.id
                snapshot.generation_record_id = await db.scalar(select(GenerationRecord.id).where(
                    GenerationRecord.task_id == task_id,
                    GenerationRecord.substep == "render_composition",
                ).order_by(GenerationRecord.created_at.desc()).limit(1))
                t.result_video_asset_id = asset.id
                t.result_video_url = None
                t.status = "composition_review"
                await db.commit()

        # Persistent Media is linked by durable asset identity only.  The
        # corresponding provider or access URLs never enter a Generation Record.
        media_asset_ids = []
        if node_name == "generate_images":
            media_asset_ids = [str(asset_id) for asset_id in await db.scalars(
                select(GeneratedImage.asset_id).where(
                    GeneratedImage.task_id == task_id,
                    GeneratedImage.asset_id.is_not(None),
                )
            )]
        elif node_name == "generate_video_clips":
            media_asset_ids = [str(asset_id) for asset_id in await db.scalars(
                select(VideoCandidate.asset_id).where(
                    VideoCandidate.task_id == task_id,
                    VideoCandidate.kind == "clip",
                    VideoCandidate.asset_id.is_not(None),
                )
            )]
        elif output.get("tts_audio_asset_id"):
            media_asset_ids = [str(output["tts_audio_asset_id"])]
        elif output.get("final_video_asset_id"):
            media_asset_ids = [str(output["final_video_asset_id"])]
        if media_asset_ids:
            records = (await db.scalars(select(GenerationRecord).where(
                GenerationRecord.task_id == task_id,
                GenerationRecord.substep == node_name,
            ).order_by(GenerationRecord.created_at.desc()))).all()
            for record in records:
                record.media_asset_ids = media_asset_ids
            await db.commit()
