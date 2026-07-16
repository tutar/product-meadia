import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from src.tools.render import render_hyperframes


@pytest.mark.asyncio
async def test_render_hyperframes_success():
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"", b""))

    with patch("asyncio.create_subprocess_shell", return_value=mock_proc) as mock_exec:
        with patch("tempfile.mkdtemp", return_value="/tmp/hyperframes/hf_test") as mock_mkdtemp:
            with patch("builtins.open", MagicMock()):
                path = await render_hyperframes("<html>test</html>")
                assert path == "/tmp/hyperframes/hf_test/output.mp4"
                mock_mkdtemp.assert_called_once_with(prefix="render_", dir="/tmp/hyperframes")
                mock_exec.assert_called_once()


@pytest.mark.asyncio
async def test_render_hyperframes_failure_raises():
    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.communicate = AsyncMock(return_value=(b"", b"Render error"))

    with patch("asyncio.create_subprocess_shell", return_value=mock_proc) as mock_exec:
        with patch("tempfile.mkdtemp", return_value="/tmp/hf_fail"):
            with patch("builtins.open", MagicMock()):
                with pytest.raises(RuntimeError, match="HyperFrames render failed"):
                    await render_hyperframes("<html>bad</html>")
