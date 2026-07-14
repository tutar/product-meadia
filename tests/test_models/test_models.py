import pytest
from src.models.user import User
from src.models.product import Product
from src.models.task import VideoTask
from src.models.script import Script
from src.models.generated_image import GeneratedImage
from src.models.viral_analysis import ViralAnalysis


def test_user_model_fields():
    assert hasattr(User, "email")
    assert hasattr(User, "hashed_password")
    assert hasattr(User, "google_id")
    assert hasattr(User, "role")
    assert hasattr(User, "is_active")
    assert User.__tablename__ == "users"


def test_product_model_fields():
    assert hasattr(Product, "name")
    assert hasattr(Product, "top_note")
    assert hasattr(Product, "middle_note")
    assert hasattr(Product, "base_note")
    assert hasattr(Product, "scenarios")
    assert hasattr(Product, "main_image_url")
    assert hasattr(Product, "created_at")
    assert hasattr(Product, "updated_at")


def test_video_task_model_fields():
    assert hasattr(VideoTask, "product_id")
    assert hasattr(VideoTask, "type")
    assert hasattr(VideoTask, "status")
    assert hasattr(VideoTask, "image_count")
    assert hasattr(VideoTask, "celery_task_id")
    assert VideoTask.__tablename__ == "video_tasks"


def test_video_task_relationships():
    assert hasattr(VideoTask, "product")
    assert hasattr(VideoTask, "script")
    assert hasattr(VideoTask, "images")
    assert hasattr(VideoTask, "viral_analysis")


def test_script_model_fields():
    assert hasattr(Script, "task_id")
    assert hasattr(Script, "content")
    assert hasattr(Script, "edited_content")
    assert hasattr(Script, "image_prompts")
    assert hasattr(Script, "voiceover_text")
    assert hasattr(Script, "status")


def test_generated_image_model_fields():
    assert hasattr(GeneratedImage, "task_id")
    assert hasattr(GeneratedImage, "prompt")
    assert hasattr(GeneratedImage, "image_url")
    assert hasattr(GeneratedImage, "sort_order")
    assert hasattr(GeneratedImage, "status")


def test_viral_analysis_model_fields():
    assert hasattr(ViralAnalysis, "task_id")
    assert hasattr(ViralAnalysis, "source_url")
    assert hasattr(ViralAnalysis, "original_script")
    assert hasattr(ViralAnalysis, "script_structure")
    assert hasattr(ViralAnalysis, "shot_list")
    assert hasattr(ViralAnalysis, "style_params")


