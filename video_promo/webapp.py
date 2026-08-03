"""Minimal web UI for the promo builder.

Run it::

    pip install flask
    python -m video_promo.webapp
    # open http://localhost:5001

Upload a clip, optionally fill in captions / branding, and the styled promo is
built and offered for download. Builds run synchronously (a clip takes ~20-40s),
so this is meant for local / single-user use — not a public multi-user server.
"""
from __future__ import annotations

import os
import tempfile
import uuid

from flask import (Flask, request, send_file, render_template_string,
                   redirect, url_for, abort)

from .config import BuildConfig, BrandConfig
from .builder import build

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500 MB uploads

# Where finished videos are kept for download.
OUT_DIR = os.path.join(tempfile.gettempdir(), "video_promo_out")
os.makedirs(OUT_DIR, exist_ok=True)

ALLOWED = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".avi"}


PAGE = """
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Promo Video Builder</title>
<style>
  :root { --lime:#8bc73f; --lime-d:#7ab234; --blue:#2878c8; --ink:#12161c; }
  * { box-sizing: border-box; }
  body { margin:0; font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
         background:linear-gradient(160deg,var(--blue),var(--lime)); color:#12161c;
         min-height:100vh; display:flex; align-items:flex-start; justify-content:center; }
  .card { background:#fff; margin:40px 16px; padding:28px 26px; border-radius:18px;
          box-shadow:0 12px 40px rgba(0,0,0,.25); width:100%; max-width:560px; }
  h1 { margin:0 0 4px; font-size:26px; }
  p.sub { margin:0 0 22px; color:#5b6672; font-size:14px; }
  label { display:block; font-weight:600; margin:16px 0 6px; font-size:14px; }
  input[type=text], textarea, input[type=file] {
     width:100%; padding:11px 12px; border:1px solid #d7dce2; border-radius:10px;
     font-size:14px; font-family:inherit; }
  textarea { min-height:96px; resize:vertical; }
  .row { display:flex; gap:12px; } .row > div { flex:1; }
  .hint { color:#8a94a0; font-size:12px; margin-top:4px; }
  button { margin-top:24px; width:100%; padding:14px; border:0; border-radius:12px;
           background:var(--lime); color:#12240c; font-weight:800; font-size:16px;
           cursor:pointer; letter-spacing:.5px; }
  button:hover { background:var(--lime-d); }
  .err { background:#fdecec; color:#b3261e; padding:12px 14px; border-radius:10px;
         margin-bottom:16px; font-size:14px; }
  details { margin-top:8px; } summary { cursor:pointer; font-weight:600; font-size:14px; }
  .ok { text-align:center; }
  video { width:100%; border-radius:14px; margin:18px 0; background:#000; }
  a.dl { display:inline-block; background:var(--lime); color:#12240c; font-weight:800;
         padding:13px 22px; border-radius:12px; text-decoration:none; }
</style>
</head>
<body>
  <div class="card">
  {% if built %}
    <div class="ok">
      <h1>✅ Your promo is ready</h1>
      <p class="sub">Preview below, then download.</p>
      <video src="{{ url_for('download', name=name) }}" controls playsinline></video>
      <a class="dl" href="{{ url_for('download', name=name) }}" download>⬇ Download MP4</a>
      <p style="margin-top:20px"><a href="{{ url_for('index') }}">← Build another</a></p>
    </div>
  {% else %}
    <h1>🎬 Promo Video Builder</h1>
    <p class="sub">Upload a clip — it's rebuilt in the branded vertical style automatically.</p>
    {% if error %}<div class="err">{{ error }}</div>{% endif %}
    <form method="post" action="{{ url_for('do_build') }}" enctype="multipart/form-data">
      <label>Your video *</label>
      <input type="file" name="video" accept="video/*" required>
      <div class="hint">mp4 / mov / webm — any aspect ratio.</div>

      <label>Captions (one line each, shown in order)</label>
      <textarea name="captions" placeholder="TURN YOUR CLIP&#10;INTO A POLISHED PROMO&#10;IN ONE STEP"></textarea>

      <details>
        <summary>Branding &amp; call-to-action (optional)</summary>
        <div class="row">
          <div><label>Brand name (bottom band)</label>
            <input type="text" name="brand" placeholder="YOUR BRAND"></div>
          <div><label>Outro title</label>
            <input type="text" name="outro_title" placeholder="YOURAPP"></div>
        </div>
        <label>Outro subtitle</label>
        <input type="text" name="outro_subtitle" placeholder="By Your Company">
        <div class="row">
          <div><label>CTA button</label>
            <input type="text" name="cta" placeholder="START FREE"></div>
          <div><label>CTA subtext</label>
            <input type="text" name="cta_subtext" placeholder="For iOS and Android"></div>
        </div>
      </details>

      <button type="submit">Build my promo</button>
    </form>
  {% endif %}
  </div>
</body>
</html>
"""


@app.get("/")
def index():
    return render_template_string(PAGE, built=False, error=None)


@app.post("/build")
def do_build():
    f = request.files.get("video")
    if not f or not f.filename:
        return render_template_string(PAGE, built=False,
                                      error="Please choose a video file.")
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in ALLOWED:
        return render_template_string(
            PAGE, built=False,
            error=f"Unsupported file type '{ext}'. Use mp4, mov, webm…")

    job = uuid.uuid4().hex[:12]
    src = os.path.join(OUT_DIR, f"src_{job}{ext}")
    out = os.path.join(OUT_DIR, f"promo_{job}.mp4")
    f.save(src)

    captions = [ln.strip() for ln in
                request.form.get("captions", "").splitlines() if ln.strip()]

    brand = BrandConfig()
    for field, key in [("brand", "brand_name"), ("outro_title", "outro_title"),
                       ("outro_subtitle", "outro_subtitle"), ("cta", "cta_text"),
                       ("cta_subtext", "cta_subtext")]:
        val = request.form.get(field, "").strip()
        if val:
            setattr(brand, key, val)

    cfg = BuildConfig(input_path=src, output_path=out,
                      captions=captions, brand=brand)
    try:
        build(cfg)
    except Exception as exc:
        return render_template_string(PAGE, built=False,
                                      error=f"Build failed: {exc}")
    finally:
        try:
            os.remove(src)
        except OSError:
            pass

    return render_template_string(PAGE, built=True, name=os.path.basename(out))


@app.get("/download/<name>")
def download(name):
    # basic path-traversal guard
    if "/" in name or "\\" in name or not name.endswith(".mp4"):
        abort(404)
    path = os.path.join(OUT_DIR, name)
    if not os.path.exists(path):
        abort(404)
    return send_file(path, mimetype="video/mp4",
                     as_attachment=False, download_name="promo.mp4")


def main():
    port = int(os.environ.get("PORT", "5001"))
    app.run(host="0.0.0.0", port=port, debug=False)


if __name__ == "__main__":
    main()
