import pytest

from src.services.product_validation import AttributeValidationError, normalize_attributes


class Stub:
    def __init__(self, key, type_, required, options):
        self.key = key
        self.type = type_
        self.required = required
        self.options = options


@pytest.fixture
def definitions():
    return [
        Stub("title", "text", True, []),
        Stub("weight", "number", True, []),
        Stub("color", "single_select", True, ["red", "blue"]),
        Stub("tags", "multi_select", False, ["new", "gift"]),
        Stub("recyclable", "boolean", False, []),
    ]


def test_normalize_attributes_supports_all_types(definitions):
    assert normalize_attributes(
        definitions,
        {
            "title": "Cup",
            "weight": 2.5,
            "color": "red",
            "tags": ["gift", "gift"],
            "recyclable": True,
        },
    ) == {
        "title": "Cup",
        "weight": 2.5,
        "color": "red",
        "tags": ["gift"],
        "recyclable": True,
    }


@pytest.mark.parametrize("values,key", [
    ({"weight": 1, "color": "red"}, "title"),
    ({"title": "", "weight": 1, "color": "red"}, "title"),
    ({"title": "Cup", "weight": 1, "color": ""}, "color"),
])
def test_normalize_attributes_rejects_missing_or_empty_required_values(definitions, values, key):
    with pytest.raises(AttributeValidationError) as exc_info:
        normalize_attributes(definitions, values)
    assert key in exc_info.value.errors


def test_normalize_attributes_reports_all_unknown_keys(definitions):
    with pytest.raises(AttributeValidationError) as exc_info:
        normalize_attributes(
            definitions,
            {"title": "Cup", "weight": 1, "color": "red", "size": "L", "sku": "1"},
        )
    assert exc_info.value.errors == {"size": "Unknown attribute", "sku": "Unknown attribute"}


@pytest.mark.parametrize("values,key", [
    ({"title": 1, "weight": 1, "color": "red"}, "title"),
    ({"title": "Cup", "weight": True, "color": "red"}, "weight"),
    ({"title": "Cup", "weight": 1, "color": "green"}, "color"),
    ({"title": "Cup", "weight": 1, "color": "red", "recyclable": 1}, "recyclable"),
    ({"title": "Cup", "weight": 1, "color": "red", "tags": "gift"}, "tags"),
    ({"title": "Cup", "weight": 1, "color": "red", "tags": ["other"]}, "tags"),
])
def test_normalize_attributes_rejects_invalid_types_and_options(definitions, values, key):
    with pytest.raises(AttributeValidationError) as exc_info:
        normalize_attributes(definitions, values)
    assert key in exc_info.value.errors


def test_normalize_attributes_raises_once_with_all_errors(definitions):
    with pytest.raises(AttributeValidationError) as exc_info:
        normalize_attributes(definitions, {"title": 1, "weight": True, "unknown": "x"})
    assert set(exc_info.value.errors) == {"title", "weight", "color", "unknown"}
