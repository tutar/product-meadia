import pytest
from fastapi import HTTPException

from src.api.tasks import validated_feedback


def test_feedback_is_trimmed_and_requires_meaningful_content():
    assert validated_feedback("  Make the product more prominent  ") == "Make the product more prominent"


@pytest.mark.parametrize("feedback", [None, "", " four", "x" * 1001])
def test_feedback_length_is_enforced_on_the_server(feedback):
    with pytest.raises(HTTPException) as error:
        validated_feedback(feedback)
    assert error.value.status_code == 422
