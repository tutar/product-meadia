from pathlib import Path
import os
import subprocess


def test_project_docs_declare_local_video_worker_and_beat():
    root = Path(__file__).parents[2]
    readme = (root / "README.md").read_text()

    assert (root / "start-worker.sh").is_file()
    assert (root / "start-beat.sh").is_file()
    assert "./start-worker.sh" in readme
    assert "./start-beat.sh" in readme


def test_start_script_launches_worker_after_starting_frontend(tmp_path):
    root = Path(__file__).parents[2]
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    worker_log = tmp_path / "commands.log"

    for command in ("conda", "npm"):
        executable = bin_dir / command
        executable.write_text(
            "#!/bin/sh\n"
            'printf "%s\\n" "$*" >> "$WORKER_LOG"\n'
        )
        executable.chmod(0o755)

    environment = os.environ | {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "WORKER_LOG": str(worker_log),
    }
    subprocess.run(
        ["bash", "./start.sh"],
        cwd=root,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )

    assert "celery -A src.tasks.celery_app worker" in worker_log.read_text()
