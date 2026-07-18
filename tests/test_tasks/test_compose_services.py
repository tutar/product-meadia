from pathlib import Path


def test_project_docs_declare_local_video_worker_and_beat():
    root = Path(__file__).parents[2]
    readme = (root / "README.md").read_text()

    assert (root / "start-worker.sh").is_file()
    assert (root / "start-beat.sh").is_file()
    assert "./start-worker.sh" in readme
    assert "./start-beat.sh" in readme
