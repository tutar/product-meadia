import pytest
from src.models.user import User
from src.models.product import Product
from src.models.task import VideoTask
from src.models.script import Script
from src.models.generated_image import GeneratedImage
from src.models.viral_analysis import ViralAnalysis
from src.models.category import Category, CategoryAttribute
from src.models.main_image_candidate import MainImageCandidate
from src.models.catalog_initialization import CatalogInitialization


def test_user_model_fields():
    assert hasattr(User, "email")
    assert hasattr(User, "hashed_password")
    assert hasattr(User, "google_id")
    assert hasattr(User, "role")
    assert hasattr(User, "is_active")
    assert User.__tablename__ == "users"


def test_product_is_generic_and_tenant_owned():
    assert hasattr(Product, "user_id")
    assert hasattr(Product, "category_id")
    assert hasattr(Product, "name")
    assert hasattr(Product, "description")
    assert hasattr(Product, "selling_points")
    assert hasattr(Product, "scenarios")
    assert hasattr(Product, "main_image_url")
    assert hasattr(Product, "main_image_source")
    assert hasattr(Product, "attributes")
    assert hasattr(Product, "category_template_version")
    assert not hasattr(Product, "top_note")
    assert hasattr(Product, "created_at")
    assert hasattr(Product, "updated_at")


def test_catalog_model_fields_match_schema():
    assert Category.__tablename__ == "categories"
    for field in ("user_id", "name", "description", "template_version", "attributes", "products"):
        assert hasattr(Category, field)

    assert CategoryAttribute.__tablename__ == "category_attributes"
    for field in ("category_id", "key", "label", "type", "required", "options", "sort_order"):
        assert hasattr(CategoryAttribute, field)

    assert MainImageCandidate.__tablename__ == "main_image_candidates"
    for field in ("user_id", "image_url", "expires_at", "used_at", "created_at"):
        assert hasattr(MainImageCandidate, field)

    assert CatalogInitialization.__tablename__ == "catalog_initializations"
    for field in (
        "user_id", "sample_version", "status", "attempts", "error_message",
        "next_attempt_at", "completed_at", "created_at", "updated_at",
    ):
        assert hasattr(CatalogInitialization, field)


def test_catalog_models_preserve_ddl_constraints():
    assert {column.name for constraint in Category.__table__.constraints
            if constraint.__class__.__name__ == "UniqueConstraint"
            for column in constraint.columns} >= {"user_id", "name"}
    assert {column.name for constraint in CategoryAttribute.__table__.constraints
            if constraint.__class__.__name__ == "UniqueConstraint"
            for column in constraint.columns} >= {"category_id", "key"}
    assert {column.name for constraint in CatalogInitialization.__table__.constraints
            if constraint.__class__.__name__ == "UniqueConstraint"
            for column in constraint.columns} >= {"user_id", "sample_version"}

    product_fk = next(iter(VideoTask.__table__.c.product_id.foreign_keys))
    assert VideoTask.__table__.c.product_id.nullable is True
    assert product_fk.ondelete == "SET NULL"
    assert VideoTask.__table__.c.product_snapshot.nullable is False
    assert VideoTask.__table__.c.product_snapshot.default is None


def test_video_task_model_fields():
    assert hasattr(VideoTask, "user_id")
    assert hasattr(VideoTask, "product_id")
    assert hasattr(VideoTask, "product_snapshot")
    assert hasattr(VideoTask, "progress_log")
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
