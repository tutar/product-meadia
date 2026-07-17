from pathlib import Path


def test_worker_image_installs_hyperframes_cli_globally():
    dockerfile = Path("Dockerfile").read_text()

    assert "npm install -g hyperframes" in dockerfile
    assert "npx hyperframes --version ||" not in dockerfile
