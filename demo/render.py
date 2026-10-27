"""Render the demo video from demo/scenes/index.html with headless Microsoft Edge (Playwright) and ffmpeg.

    demo\\.venv\\Scripts\\python demo\\render.py                     # docs/demo/vidyadesk-demo.mp4 + poster.png
    demo\\.venv\\Scripts\\python demo\\render.py --stills 5,35,55    # check single frames (demo/build/stills/)
"""
import argparse
import functools
import http.server
import json
import shutil
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
BUILD = HERE / "build"
WIDTH, HEIGHT, FPS = 1920, 1080, 30


@contextmanager
def serve_demo_folder():
    """Serve demo/ on a free localhost port, so the page can fetch its JSON and images."""
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    handler = functools.partial(Quiet, directory=str(HERE))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/scenes/index.html"
    finally:
        server.shutdown()


@contextmanager
def scenes_page():
    with serve_demo_folder() as url, sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge")
        page = browser.new_page(viewport={"width": WIDTH, "height": HEIGHT})
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(url)
        page.evaluate("window.ready")
        if errors:
            raise RuntimeError("the scenes page failed: " + "; ".join(errors))
        try:
            yield page
        finally:
            browser.close()


def stills(seconds) -> None:
    out = BUILD / "stills"
    out.mkdir(parents=True, exist_ok=True)
    with scenes_page() as page:
        total = page.evaluate("window.totalDuration")
        for t in seconds:
            page.evaluate(f"window.seek({t})")
            path = out / f"t{t:06.2f}.png"
            page.screenshot(path=str(path))
            print(f"{path.name}  (of {total:.1f} s)")


def render() -> Path:
    """Every frame through ffmpeg, then the narration (each line padded to its scene's length) muxed in."""
    narration = json.loads((HERE / "narration.json").read_text(encoding="utf-8"))
    out = ROOT / "docs" / "demo"
    out.mkdir(parents=True, exist_ok=True)
    silent = BUILD / "video-silent.mp4"
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    with scenes_page() as page:
        total = page.evaluate("window.totalDuration")
        frames = round(total * FPS)
        encoder = subprocess.Popen(
            [ffmpeg, "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(FPS), "-c:v", "png", "-i", "-",
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20", "-preset", "medium", str(silent)],
            stdin=subprocess.PIPE,
        )
        started = time.time()
        for n in range(frames):
            page.evaluate(f"window.seek({n / FPS})")
            encoder.stdin.write(page.screenshot(type="png"))
            if n % (FPS * 10) == 0:
                print(f"frame {n}/{frames} ({time.time() - started:.0f} s)", flush=True)
        encoder.stdin.close()
        if encoder.wait() != 0:
            raise RuntimeError("ffmpeg failed while encoding the frames")
        page.evaluate("window.seek(20)")
        page.screenshot(path=str(out / "poster.png"))
    inputs, pads = [], []
    for i, scene in enumerate(narration["scenes"], 1):
        inputs += ["-i", str(HERE / scene["audio"])]
        length = scene["duration"] + narration["gap"] + scene["hold"]
        pads.append(f"[{i}:a]apad=whole_dur={length:.3f}[a{i}]")
    joined = "".join(f"[a{i}]" for i in range(1, len(narration["scenes"]) + 1))
    final = out / "vidyadesk-demo.mp4"
    subprocess.run(
        [ffmpeg, "-y", "-loglevel", "error", "-i", str(silent), *inputs, "-filter_complex",
         ";".join(pads) + f";{joined}concat=n={len(narration['scenes'])}:v=0:a=1[a]",
         "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(final)],
        check=True,
    )
    print(f"{final} ({final.stat().st_size / 1e6:.1f} MB, {total:.1f} s)")
    return final


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stills", help="comma-separated seconds to save as single frames")
    args = parser.parse_args()
    if args.stills:
        stills([float(s) for s in args.stills.split(",")])
    else:
        render()
    return 0


if __name__ == "__main__":
    sys.exit(main())
