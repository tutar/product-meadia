import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.tools.image_gen import generate_image


def _make_coro(return_value):
    """Create an awaitable that returns the given value."""
    async def _coro(*args, **kwargs):
        return return_value
    return _coro


@pytest.mark.asyncio
async def test_generate_image_returns_url():
    mock_response = MagicMock()
    mock_response.data = [MagicMock(url="https://rustfs:8001/images/test.png")]

    with patch("src.tools.image_gen.client.images.generate", side_effect=_make_coro(mock_response)) as mock_gen:
        url = await generate_image("A perfume bottle on a marble table")
        assert url == "https://rustfs:8001/images/test.png"
        mock_gen.assert_called_once()
        call_kwargs = mock_gen.call_args.kwargs
        assert call_kwargs["model"] == "agnes-image-2.1-flash"
        assert call_kwargs["prompt"] == "A perfume bottle on a marble table"
        assert call_kwargs["size"] == "1024x1024"


@pytest.mark.asyncio
async def test_generate_image_with_ref_image():
    mock_response = MagicMock()
    mock_response.data = [MagicMock(url="https://rustfs:8001/images/test2.png")]

    with patch("src.tools.image_gen.client.images.generate", side_effect=_make_coro(mock_response)) as mock_gen:
        url = await generate_image("Variant of the scene", ref_image_url="https://example.com/ref.png")
        assert url == "https://rustfs:8001/images/test2.png"
        assert mock_gen.call_args.kwargs["extra_body"] == {"image": ["https://example.com/ref.png"]}


@pytest.mark.asyncio
async def test_generate_image_retries_then_raises():
    async def _failing(*args, **kwargs):
        raise Exception("API down")

    with patch("src.tools.image_gen.client.images.generate", side_effect=_failing) as mock_gen:
        with pytest.raises(Exception):
            await generate_image("test")
        assert mock_gen.call_count == 3
