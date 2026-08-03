"""Minimal web UI for the tactical marker.

    pip install flask ultralytics
    python -m tactical_marker.webapp      # http://localhost:5002

Upload a football clip, choose which markings to draw, and the annotated video
is produced for download. Detection runs on CPU, so processing takes a while
(~a few seconds per second of footage) — meant for local single-user use.
"""
from __future__ import annotations

import os
import tempfile
import uuid

from flask import (Flask, request, send_file, render_template_string, abort)

from .config import MarkerConfig
from .processor import process

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024

OUT_DIR = os.path.join(tempfile.gettempdir(), "tactical_marker_out")
os.makedirs(OUT_DIR, exist_ok=True)
ALLOWED = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}

PAGE = """
<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tactical Marker</title>
<style>
 *{box-sizing:border-box} body{margin:0;font-family:system-ui,Segoe UI,Roboto,sans-serif;
   background:#0d1f14;color:#eaf2ec;min-height:100vh;display:flex;justify-content:center}
 .card{background:#13291b;margin:36px 16px;padding:26px;border-radius:16px;width:100%;
   max-width:560px;box-shadow:0 12px 40px rgba(0,0,0,.4)}
 h1{margin:0 0 4px;font-size:24px} p.sub{margin:0 0 20px;color:#9db3a4;font-size:14px}
 label{display:block;font-weight:600;margin:14px 0 6px;font-size:14px}
 input[type=file]{width:100%;padding:10px;border:1px solid #2c4a36;border-radius:10px;
   background:#0d1f14;color:#eaf2ec}
 .opt{display:flex;align-items:center;gap:10px;margin:8px 0;font-size:15px}
 .opt input{width:18px;height:18px}
 .hint{color:#7f9587;font-size:12px;margin-top:4px}
 button{margin-top:22px;width:100%;padding:14px;border:0;border-radius:12px;
   background:#8bc73f;color:#0d1f14;font-weight:800;font-size:16px;cursor:pointer}
 button:hover{background:#7ab234}
 .err{background:#3a1414;color:#ffb4a8;padding:12px;border-radius:10px;margin-bottom:14px}
 .ok{text-align:center} video{width:100%;border-radius:12px;margin:16px 0;background:#000}
 a.dl{display:inline-block;background:#8bc73f;color:#0d1f14;font-weight:800;padding:12px 22px;
   border-radius:12px;text-decoration:none} a{color:#8bc73f}
 .note{background:#0d1f14;border:1px solid #2c4a36;padding:10px 12px;border-radius:10px;
   font-size:13px;color:#9db3a4;margin-top:14px}
</style></head><body><div class="card">
{% if built %}
 <div class="ok"><h1>✅ Marked video ready</h1>
 <video src="{{ url_for('download',name=name) }}" controls playsinline></video>
 <a class="dl" href="{{ url_for('download',name=name) }}" download>⬇ Download MP4</a>
 <p style="margin-top:18px"><a href="{{ url_for('index') }}">← Mark another</a></p></div>
{% else %}
 <h1>⚽ Tactical Marker</h1>
 <p class="sub">Upload a football clip — players are auto-detected and marked with rings, a spotlight, and motion arrows.</p>
 {% if error %}<div class="err">{{ error }}</div>{% endif %}
 <form method="post" action="{{ url_for('do_build') }}" enctype="multipart/form-data">
   <label>Your football video *</label>
   <input type="file" name="video" accept="video/*" required>
   <label>Mode</label>
   <div class="opt"><input type="radio" name="mode" value="ball-follow" checked><span><b>Follow the ball</b> — mark only the carrier + passes</span></div>
   <div class="opt"><input type="radio" name="mode" value="all-players"><span>Ring every player</span></div>
   <label>Markings</label>
   <div class="opt"><input type="checkbox" name="rings" checked><span>Rings under player(s)</span></div>
   <div class="opt"><input type="checkbox" name="spotlight" checked><span>Spotlight</span></div>
   <div class="opt"><input type="checkbox" name="arrows" checked><span>Pass / motion arrows</span></div>
   <div class="opt"><input type="checkbox" name="team"><span>Colour rings by team (all-players mode)</span></div>
   <label>Only process first N seconds (optional)</label>
   <input type="text" name="max_seconds" placeholder="e.g. 15 — leave blank for whole clip"
      style="width:100%;padding:10px;border:1px solid #2c4a36;border-radius:10px;background:#0d1f14;color:#eaf2ec">
   <div class="hint">Detection runs on CPU — expect a few seconds of processing per second of video.</div>
   <button type="submit">Mark my video</button>
 </form>
 <div class="note">First run downloads a ~6&nbsp;MB detection model automatically.</div>
{% endif %}
</div></body></html>
"""


@app.get("/")
def index():
    return render_template_string(PAGE, built=False, error=None)


@app.post("/build")
def do_build():
    f = request.files.get("video")
    if not f or not f.filename:
        return render_template_string(PAGE, built=False, error="Please choose a video.")
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in ALLOWED:
        return render_template_string(PAGE, built=False,
                                      error=f"Unsupported type '{ext}'.")
    job = uuid.uuid4().hex[:12]
    src = os.path.join(OUT_DIR, f"src_{job}{ext}")
    out = os.path.join(OUT_DIR, f"marked_{job}.mp4")
    f.save(src)

    max_s = request.form.get("max_seconds", "").strip()
    try:
        max_seconds = float(max_s) if max_s else None
    except ValueError:
        max_seconds = None

    mode = request.form.get("mode", "ball-follow")
    if mode not in ("ball-follow", "all-players"):
        mode = "ball-follow"
    cfg = MarkerConfig(
        input_path=src, output_path=out, mode=mode,
        rings="rings" in request.form,
        spotlight="spotlight" in request.form,
        arrows="arrows" in request.form,
        color_by_team="team" in request.form,
        max_seconds=max_seconds,
    )
    try:
        process(cfg)
    except Exception as exc:
        return render_template_string(PAGE, built=False, error=f"Failed: {exc}")
    finally:
        try:
            os.remove(src)
        except OSError:
            pass
    return render_template_string(PAGE, built=True, name=os.path.basename(out))


@app.get("/download/<name>")
def download(name):
    if "/" in name or "\\" in name or not name.endswith(".mp4"):
        abort(404)
    path = os.path.join(OUT_DIR, name)
    if not os.path.exists(path):
        abort(404)
    return send_file(path, mimetype="video/mp4", as_attachment=False,
                     download_name="marked.mp4")


def main():
    port = int(os.environ.get("PORT", "5002"))
    app.run(host="0.0.0.0", port=port, debug=False)


if __name__ == "__main__":
    main()
