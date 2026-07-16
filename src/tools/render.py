import asyncio
import tempfile
import os
from langfuse import observe


@observe(name="render_hyperframes")
async def render_hyperframes(html_content: str, asset_dir: str = "/tmp") -> str:
    workdir = tempfile.mkdtemp(prefix="hyperframes_")
    html_path = os.path.join(workdir, "index.html")
    output_path = os.path.join(workdir, "output.mp4")

    with open(html_path, "w") as f:
        f.write(html_content)

    proc = await asyncio.create_subprocess_exec(
        "hyperframes", "render", workdir, "--output", output_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=workdir,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)

    if proc.returncode != 0:
        raise RuntimeError(f"HyperFrames render failed: {stderr.decode()}")
    return output_path
