"""Render the demo video from demo/scenes/index.html with headless Microsoft Edge (Playwright) and ffmpeg.

    demo\\.venv\\Scripts\\python demo\\render.py --stills 5,35,55    # check single frames (demo/build/stills/)
"""
import argparse
import functools
import http.server
import sys
import threading
from contextlib import contextmanager
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stills", help="comma-separated seconds to save as single frames")
    args = parser.parse_args()
    if args.stills:
        stills([float(s) for s in args.stills.split(",")])
        return 0
    parser.error("the full render is added in Task 4; use --stills for now")
    return 2


if __name__ == "__main__":
    sys.exit(main())
