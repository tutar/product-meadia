import pytest
from unittest.mock import patch, MagicMock
from src.tools.render import render_hyperframes


@pytest.mark.asyncio
async def test_render_hyperframes_success():
    mock_run = MagicMock()
    mock_run.return_value.returncode = 0
    mock_run.return_value.stderr = ""

    with patch("subprocess.run", mock_run):
        with patch("tempfile.mkdtemp", return_value="/tmp/hf_test"):
            with patch("builtins.open", MagicMock()):
                path = await render_hyperframes("<html>test</html>", "/tmp")
                assert path == "/tmp/hf_test/output.mp4"
                mock_run.assert_called_once()


@pytest.mark.asyncio
async def test_render_hyperframes_failure_raises():
    mock_run = MagicMock()
    mock_run.return_value.returncode = 1
    mock_run.return_value.stderr = "Render error"

    with patch("subprocess.run", mock_run):
        with patch("tempfile.mkdtemp", return_value="/tmp/hf_fail"):
            with patch("builtins.open", MagicMock()):
                with pytest.raises(RuntimeError, match="HyperFrames render failed"):
                    await render_hyperframes("<html>bad</html>", "/tmp")
