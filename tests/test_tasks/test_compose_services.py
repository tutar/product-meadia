from pathlib import Path

import yaml


def test_project_compose_declares_video_worker_and_beat():
    compose = yaml.safe_load(
        (Path(__file__).parents[2] / "docker-compose.yml").read_text()
    )
    assert "worker" in compose["services"]
    assert "beat" in compose["services"]
