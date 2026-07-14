import asyncio
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from src.config import settings
from src.tasks.celery_app import celery_app
from src.models.product import Product
from src.models.task import VideoTask
from src.models.script import Script
from src.models.generated_image import GeneratedImage
from src.models.viral_analysis import ViralAnalysis
from src.agents.state import VideoAgentState
from src.ws.progress import progress_manager

engine = create_async_engine(settings.database_url)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

GRAPHS = {}


def _get_graph(task_type: str):
    if task_type not in GRAPHS:
        if task_type == "promo":
            from src.agents.promo_graph import promo_graph
            GRAPHS["promo"] = promo_graph
        elif task_type == "viral":
            from src.agents.viral_graph import viral_graph
            GRAPHS["viral"] = viral_graph
        elif task_type == "personify":
            from src.agents.personify_graph import personify_graph
            GRAPHS["personify"] = personify_graph
    return GRAPHS[task_type]


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def run_video_task(self, task_id: str):
    return asyncio.get_event_loop().run_until_complete(
        _async_run(task_id, self.request.id)
    )


async def _async_run(task_id: str, celery_task_id: str):
    async with SessionLocal() as db:
        result = await db.execute(select(VideoTask).where(VideoTask.id == task_id))
        task = result.scalar_one()
        product_result = await db.execute(
            select(Product).where(Product.id == task.product_id)
        )
        product = product_result.scalar_one()

        initial_state: VideoAgentState = {
            "task_id": str(task.id),
            "product_id": str(product.id),
            "product_info": {
                "name": product.name,
                "top_note": product.top_note,
                "middle_note": product.middle_note,
                "base_note": product.base_note,
                "scenarios": product.scenarios,
                "main_image_url": product.main_image_url,
            },
            "task_type": task.type,
            "image_count": task.image_count,
            "viral_url": "",
            "script_content": "",
            "edited_script_content": "",
            "image_prompts": [],
            "voiceover_text": "",
            "generated_images": [],
            "video_clips": [],
            "tts_audio_url": "",
            "tts_words": [],
            "lipsync_video_url": "",
            "character_image_url": "",
            "viral_analysis": {},
            "hyperframes_html": "",
            "final_video_path": "",
            "review_approved": False,
            "messages": [],
        }

        if task.type == "viral":
            v_result = await db.execute(
                select(ViralAnalysis).where(ViralAnalysis.task_id == task.id)
            )
            va = v_result.scalar_one_or_none()
            if va:
                initial_state["viral_url"] = va.source_url

        task.status = "scripting"
        task.celery_task_id = celery_task_id
        await db.commit()

    graph = _get_graph(task.type)
    config = {"configurable": {"thread_id": task_id}}

    async for event in graph.astream(initial_state, config):
        await progress_manager.send_progress(task_id, {"event": str(event)})
        for node_name, node_output in event.items():
            if node_name.startswith("wait_"):
                async with SessionLocal() as db:
                    t = (
                        await db.execute(
                            select(VideoTask).where(VideoTask.id == task_id)
                        )
                    ).scalar_one()
                    t.status = node_name
                    await db.commit()

    async with SessionLocal() as db:
        t = (
            await db.execute(select(VideoTask).where(VideoTask.id == task_id))
        ).scalar_one()
        t.status = "done"
        await db.commit()
