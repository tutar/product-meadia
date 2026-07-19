import asyncio
import tempfile
import os
from langfuse import observe
from src.tasks.generation_records import record_generation


@observe(name="render_hyperframes")
async def render_hyperframes(html_content: str) -> str:
    output_root = os.environ.get("VIDEO_OUTPUT_DIR")
    if output_root:
        os.makedirs(output_root, exist_ok=True)
        workdir = tempfile.mkdtemp(prefix="render_", dir=output_root)
    else:
        workdir = tempfile.mkdtemp(prefix="render_")
    html_path = os.path.join(workdir, "index.html")
    output_path = os.path.join(workdir, "output.mp4")

    with open(html_path, "w") as f:
        f.write(html_content)

    cmd = f"export NVM_DIR=\"$HOME/.nvm\"; [ -s \"$NVM_DIR/nvm.sh\" ] && . \"$NVM_DIR/nvm.sh\"; hyperframes render {workdir} --output {output_path}"
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=workdir,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)

    if proc.returncode != 0:
        raise RuntimeError(f"HyperFrames render failed: {stderr.decode()}")
    await record_generation(
        "hyperframes", "hyperframes-renderer", {},
        {"composition": "promo-video", "html_length": len(html_content)},
        {"result": "final composition rendered"},
        {"composition": "promo-video", "html_length": len(html_content)},
    )
    return output_path
