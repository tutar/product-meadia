import pytest

from src.agents.personify_graph import CHARACTER_PROMPT, SCRIPT_PROMPT
from src.agents.promo_graph import SCRIPT_SYSTEM
from src.agents.viral_graph import PROMPT
from src.services.product_context import format_product_context


def snapshot(category, name, label, value):
    return {"version": 1, "name": name, "category": {"name": category}, "attributes": [
        {"key": label.lower(), "label": label, "type": "text", "value": value}
    ], "selling_points": ["Reliable"], "scenarios": ["Everyday"], "main_image_url": "x"}


@pytest.mark.parametrize("context", [
    snapshot("Perfume", "Floral Mist", "Scent", "Rose"),
    snapshot("Electronics", "Headphones", "Color", "Black"),
    snapshot("Food", "Cookies", "Flavor", "Chocolate"),
])
def test_product_context_contains_actual_category_name_and_attributes(context):
    prompt = format_product_context(context)
    assert context["category"]["name"] in prompt
    assert context["name"] in prompt
    assert context["attributes"][0]["value"] in prompt


def test_agent_prompt_templates_are_category_neutral():
    combined = "\n".join((SCRIPT_SYSTEM, PROMPT, CHARACTER_PROMPT, SCRIPT_PROMPT)).lower()
    for forbidden in ("top notes", "middle notes", "base notes", "perfume bottle", "perfume product"):
        assert forbidden not in combined
