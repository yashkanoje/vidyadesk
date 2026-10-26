"""Synthesise the demo video's narration (the approved storyboard's voice lines) and record each line's length.

    demo\\.venv\\Scripts\\python demo\\narration.py
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
AUDIO = HERE / "build" / "audio"
VOICE = "en-IN-PrabhatNeural"
GAP = 0.6  # seconds of silence after each line
# Extra seconds a scene stays on screen after its line, so the viewer can read the chats and the dashboard.
HOLD = {"hook": 1.0, "problem": 0.5, "meet": 1.5, "answer": 10.0, "lead": 3.0, "handoff": 3.0,
        "dashboard": 7.0, "followup": 2.0, "hood": 5.0, "close": 3.0}

# The voice lines from docs/specs/2026-10-26-demo-video-design.md, word for word.
SCENES = [
    {"id": "hook", "title": "Hook", "line": "It's 10:42 at night. A parent asks about JEE fees, and the institute is closed."},
    {"id": "problem", "title": "The problem", "line": "Most enquiries arrive in the evening or during class. When nobody replies, the student asks the next institute."},
    {"id": "meet", "title": "Meet VidyaDesk", "line": "Meet VidyaDesk, an AI assistant for coaching institutes."},
    {"id": "answer", "title": "Instant answer, any language", "line": "It answers fees, batches and timings from the institute's own facts, with exact numbers, in English, Hindi, Hinglish or Odia."},
    {"id": "lead", "title": "Lead captured, owner alerted", "line": "While it chats, it saves the student's name, class and course, rates their interest, and alerts the owner the moment a lead is hot."},
    {"id": "handoff", "title": "Hands off to a person", "line": "When a parent wants a person, it hands the chat to the owner, and passes on any new messages."},
    {"id": "dashboard", "title": "The dashboard", "line": "Every enquiry lands in the VidyaDesk dashboard: who needs a call, every conversation, and a CSV for Excel."},
    {"id": "followup", "title": "Never forgets to follow up", "line": "If a student goes quiet, it follows up once, politely. Every morning at eight, the owner gets a summary."},
    {"id": "hood", "title": "Under the hood", "line": "Under the hood: a LangGraph agent, document search with pgvector, and measured results: twenty-six of twenty-six behaviour checks, and more than three hundred automated tests."},
    {"id": "close", "title": "Close", "line": "VidyaDesk. Every enquiry answered. Every lead captured."},
]


def duration(path: Path) -> float:
    out = subprocess.run(
        [shutil.which("ffprobe") or "ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout
    return round(float(out.strip()), 3)


def main() -> int:
    AUDIO.mkdir(parents=True, exist_ok=True)
    edge_tts = Path(sys.executable).with_name("edge-tts.exe")
    scenes = []
    for number, scene in enumerate(SCENES, 1):
        audio = AUDIO / f"scene-{number:02d}.mp3"
        subprocess.run([str(edge_tts), "--voice", VOICE, "--text", scene["line"], "--write-media", str(audio)],
                       check=True, capture_output=True)
        scenes.append({**scene, "audio": f"build/audio/{audio.name}", "duration": duration(audio), "hold": HOLD[scene["id"]]})
        print(f"{number:2d} {scene['id']:<10} {scenes[-1]['duration']:6.2f} s + hold {HOLD[scene['id']]}")
    total = sum(s["duration"] + GAP + s["hold"] for s in scenes)
    (HERE / "narration.json").write_text(
        json.dumps({"voice": VOICE, "gap": GAP, "scenes": scenes}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"total {total:.1f} s; written to demo/narration.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
