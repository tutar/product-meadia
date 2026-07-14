import subprocess
import tempfile
import os
from langfuse.decorators import observe


@observe(name="render_hyperframes")
async def render_hyperframes(html_content: str, asset_dir: str) -> str:
    workdir = tempfile.mkdtemp(prefix="hyperframes_")
    html_path = os.path.join(workdir, "index.html")
    output_path = os.path.join(workdir, "output.mp4")

    with open(html_path, "w") as f:
        f.write(html_content)

    result = subprocess.run(
        ["npx", "hyperframes", "render", html_path, "--output", output_path],
        capture_output=True, text=True, timeout=300, cwd=workdir,
    )
    if result.returncode != 0:
        raise RuntimeError(f"HyperFrames render failed: {result.stderr}")
    return output_path
