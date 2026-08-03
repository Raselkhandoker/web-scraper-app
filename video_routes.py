"""
video_routes.py
---------------
API endpoints for the video-to-animation feature. Registered as its own
blueprint so the existing scraper routes stay untouched.

Endpoints (all under /api/video):
    GET    /styles                 -> available styles, engines, audio modes
    POST   /jobs                   -> upload a video (+ optional audio) + options
    GET    /jobs                   -> list jobs
    GET    /jobs/<id>              -> one job (poll this for progress/status)
    GET    /jobs/<id>/source       -> the original uploaded video (for preview)
    GET    /jobs/<id>/download     -> the produced animation
    DELETE /jobs/<id>              -> delete job + files
"""

from __future__ import annotations

import os
import json
import uuid
import logging
import threading
from datetime import datetime

import cv2
from flask import Blueprint, request, jsonify, send_file, current_app

from models import db, VideoJob
from video_animator import (
    VideoAnimator, STYLES, REMOVE_METHODS, parse_cut_segments,
)


def _parse_regions(raw):
    """Parse the remove_regions JSON into a list of (x,y,w,h) fraction tuples."""
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return []
    regions = []
    for item in data if isinstance(data, list) else []:
        try:
            x, y, w, h = (float(item[0]), float(item[1]),
                          float(item[2]), float(item[3]))
        except (TypeError, ValueError, IndexError, KeyError):
            continue
        # clamp to 0..1 and drop empty boxes
        x, y = max(0.0, min(1.0, x)), max(0.0, min(1.0, y))
        w, h = max(0.0, min(1.0, w)), max(0.0, min(1.0, h))
        if w > 0.001 and h > 0.001:
            regions.append((x, y, w, h))
    return regions

logger = logging.getLogger(__name__)
video_bp = Blueprint('video', __name__, url_prefix='/api/video')

ALLOWED_VIDEO_EXT = {'.mp4', '.mov', '.avi', '.mkv', '.webm', '.m4v', '.mpg', '.mpeg'}
ALLOWED_AUDIO_EXT = {'.mp3', '.wav', '.m4a', '.aac', '.ogg', '.flac'}
AUDIO_MODES = {'keep', 'mute', 'replace', 'ai_music'}


# --------------------------------------------------------------------------- #
#  Storage helpers
# --------------------------------------------------------------------------- #

def _media_root() -> str:
    root = current_app.config.get('MEDIA_ROOT') or os.path.join(os.getcwd(), 'media')
    os.makedirs(os.path.join(root, 'uploads'), exist_ok=True)
    os.makedirs(os.path.join(root, 'outputs'), exist_ok=True)
    return root


def _uploads_dir() -> str:
    return os.path.join(_media_root(), 'uploads')


def _outputs_dir() -> str:
    return os.path.join(_media_root(), 'outputs')


def _video_duration(path: str) -> float:
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    cap.release()
    return frames / fps if fps else 0.0


def _apply_audio_track(video_path: str, audio_path: str) -> None:
    """Replace the audio of video_path with audio_path (in place)."""
    tmp = video_path + '.mux.mp4'
    VideoAnimator()._mux_replacement_audio(video_path, audio_path, tmp)
    os.replace(tmp, video_path)


# --------------------------------------------------------------------------- #
#  Background worker
# --------------------------------------------------------------------------- #

def run_video_job(app, job_id: int):
    """Process one video job inside its own app context / thread."""
    with app.app_context():
        job = VideoJob.query.get(job_id)
        if not job:
            return

        def set_progress(pct: int):
            j = VideoJob.query.get(job_id)
            if j:
                j.progress = int(pct)
                db.session.commit()

        try:
            job.status = 'running'
            job.started_at = datetime.utcnow()
            db.session.commit()

            input_path = os.path.join(_uploads_dir(), job.source_filename)
            audio_upload = (os.path.join(_uploads_dir(), job.audio_filename)
                            if job.audio_filename else None)
            out_name = f"anim_{job.id}_{uuid.uuid4().hex[:8]}.mp4"
            output_path = os.path.join(_outputs_dir(), out_name)
            audio_mode = job.audio_mode or 'keep'
            cuts = parse_cut_segments(job.cut_segments)
            regions = _parse_regions(job.remove_regions)

            if job.engine == 'ai':
                stats = _run_ai_engine(job, input_path, output_path,
                                       audio_mode, audio_upload, cuts,
                                       set_progress)
            else:
                stats = _run_local_engine(job, input_path, output_path,
                                          audio_mode, audio_upload, cuts,
                                          regions, set_progress)

            job = VideoJob.query.get(job_id)
            job.output_filename = out_name
            job.stats = json.dumps(stats)
            job.progress = 100
            job.status = 'completed'
            job.completed_at = datetime.utcnow()
            db.session.commit()
            logger.info("Video job %s completed (%s / %s / audio=%s)",
                        job_id, job.engine, job.style, audio_mode)

        except Exception as e:  # noqa: BLE001
            logger.exception("Video job %s failed", job_id)
            job = VideoJob.query.get(job_id)
            if job:
                job.status = 'failed'
                job.error_message = str(e)
                job.completed_at = datetime.utcnow()
                db.session.commit()


def _run_local_engine(job, input_path, output_path, audio_mode, audio_upload,
                      cuts, regions, set_progress):
    animator = VideoAnimator()
    # For AI music we render silent first, then generate + mux music.
    eff_mode = 'mute' if audio_mode == 'ai_music' else audio_mode
    stats = animator.process(
        input_path, output_path, style=job.style, cut_segments=cuts,
        audio_mode=eff_mode, replacement_audio=audio_upload,
        remove_regions=regions, remove_method=(job.remove_method or 'blur'),
        progress_cb=set_progress,
    )
    if audio_mode == 'ai_music':
        _add_ai_music(job, output_path)
        stats['has_audio'] = True
        stats['audio_mode'] = 'ai_music'
    return stats


def _run_ai_engine(job, input_path, output_path, audio_mode, audio_upload,
                   cuts, set_progress):
    from ai_backends import ReplicateAnimator
    animator = ReplicateAnimator()
    stats = animator.process(input_path, output_path, style=job.style,
                             progress_cb=set_progress)
    # The AI video comes back silent; apply the requested audio afterwards.
    if audio_mode == 'ai_music':
        _add_ai_music(job, output_path)
        stats['has_audio'] = True
    elif audio_mode == 'replace' and audio_upload:
        _apply_audio_track(output_path, audio_upload)
        stats['has_audio'] = True
    elif audio_mode == 'keep':
        _apply_audio_track(output_path, input_path)  # original's audio stream
        stats['has_audio'] = True
    stats['audio_mode'] = audio_mode
    return stats


def _add_ai_music(job, output_path):
    """Generate style-matched music and mux it onto output_path."""
    from ai_backends import ReplicateMusicGenerator, music_prompt_for
    duration = int(_video_duration(output_path)) or 8
    prompt = music_prompt_for(job.style, job.music_prompt or '')
    music_path = output_path + '.music.wav'
    ReplicateMusicGenerator().generate(prompt, duration, music_path)
    try:
        _apply_audio_track(output_path, music_path)
    finally:
        if os.path.exists(music_path):
            os.remove(music_path)


# --------------------------------------------------------------------------- #
#  Routes
# --------------------------------------------------------------------------- #

@video_bp.route('/styles', methods=['GET'])
def get_styles():
    return jsonify({
        'styles': [{'id': k, 'description': v} for k, v in STYLES.items()],
        'engines': [
            {'id': 'local', 'name': 'Local filter (free, offline)'},
            {'id': 'ai', 'name': 'AI service (Replicate - needs API token)'},
        ],
        'audio_modes': [
            {'id': 'keep', 'name': 'Keep original audio'},
            {'id': 'mute', 'name': 'No audio'},
            {'id': 'replace', 'name': 'Replace with my audio file'},
            {'id': 'ai_music', 'name': 'AI music matching the style (needs token)'},
        ],
    }), 200


@video_bp.route('/jobs', methods=['POST'])
def create_video_job():
    """Accept a multipart upload + options and start processing."""
    if 'video' not in request.files:
        return jsonify({'error': 'No video file uploaded (field name: video)'}), 400

    f = request.files['video']
    if not f or not f.filename:
        return jsonify({'error': 'Empty filename'}), 400

    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in ALLOWED_VIDEO_EXT:
        return jsonify({'error': f'Unsupported video type "{ext}". '
                        f'Allowed: {", ".join(sorted(ALLOWED_VIDEO_EXT))}'}), 400

    style = request.form.get('style', 'cartoon')
    if style not in STYLES:
        return jsonify({'error': f'Unknown style "{style}"'}), 400
    engine = request.form.get('engine', 'local')
    if engine not in ('local', 'ai'):
        return jsonify({'error': f'Unknown engine "{engine}"'}), 400

    audio_mode = request.form.get('audio_mode', 'keep')
    if audio_mode not in AUDIO_MODES:
        return jsonify({'error': f'Unknown audio mode "{audio_mode}"'}), 400

    remove_method = request.form.get('remove_method', 'blur')
    if remove_method not in REMOVE_METHODS:
        return jsonify({'error': f'Unknown remove method "{remove_method}"'}), 400
    remove_regions_raw = request.form.get('remove_regions', '').strip()

    # Save the video upload.
    stored_name = f"{uuid.uuid4().hex}{ext}"
    f.save(os.path.join(_uploads_dir(), stored_name))

    # Optional replacement-audio upload (for audio_mode = replace).
    audio_stored = None
    if audio_mode == 'replace':
        af = request.files.get('audio')
        if not af or not af.filename:
            return jsonify({'error': 'audio_mode "replace" needs an audio file '
                            '(field name: audio)'}), 400
        aext = os.path.splitext(af.filename)[1].lower()
        if aext not in ALLOWED_AUDIO_EXT:
            return jsonify({'error': f'Unsupported audio type "{aext}". '
                            f'Allowed: {", ".join(sorted(ALLOWED_AUDIO_EXT))}'}), 400
        audio_stored = f"{uuid.uuid4().hex}{aext}"
        af.save(os.path.join(_uploads_dir(), audio_stored))

    job = VideoJob(
        job_name=request.form.get('job_name') or f.filename,
        source_filename=stored_name,
        original_name=f.filename,
        engine=engine,
        style=style,
        cut_segments=request.form.get('cut_segments', '').strip(),
        keep_audio=(audio_mode == 'keep'),
        audio_mode=audio_mode,
        audio_filename=audio_stored,
        music_prompt=request.form.get('music_prompt', '').strip(),
        remove_regions=remove_regions_raw,
        remove_method=remove_method,
        status='pending',
        progress=0,
    )
    db.session.add(job)
    db.session.commit()

    app = current_app._get_current_object()
    threading.Thread(target=run_video_job, args=(app, job.id), daemon=True).start()

    return jsonify(job.to_dict()), 201


@video_bp.route('/jobs', methods=['GET'])
def list_video_jobs():
    jobs = VideoJob.query.order_by(VideoJob.created_at.desc()).all()
    return jsonify([j.to_dict() for j in jobs]), 200


@video_bp.route('/jobs/<int:job_id>', methods=['GET'])
def get_video_job(job_id):
    job = VideoJob.query.get(job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    return jsonify(job.to_dict()), 200


@video_bp.route('/jobs/<int:job_id>/source', methods=['GET'])
def get_source(job_id):
    job = VideoJob.query.get(job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    path = os.path.join(_uploads_dir(), job.source_filename)
    if not os.path.exists(path):
        return jsonify({'error': 'Source file missing'}), 404
    return send_file(path, mimetype='video/mp4')


@video_bp.route('/jobs/<int:job_id>/download', methods=['GET'])
def download_output(job_id):
    job = VideoJob.query.get(job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    if not job.output_filename:
        return jsonify({'error': 'Animation not ready yet'}), 409
    path = os.path.join(_outputs_dir(), job.output_filename)
    if not os.path.exists(path):
        return jsonify({'error': 'Output file missing'}), 404
    base = os.path.splitext(job.original_name or 'video')[0]
    return send_file(path, mimetype='video/mp4', as_attachment=True,
                     download_name=f'{base}_animated.mp4')


@video_bp.route('/jobs/<int:job_id>', methods=['DELETE'])
def delete_video_job(job_id):
    job = VideoJob.query.get(job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404

    for folder, name in ((_uploads_dir(), job.source_filename),
                         (_uploads_dir(), job.audio_filename),
                         (_outputs_dir(), job.output_filename)):
        if name:
            p = os.path.join(folder, name)
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    logger.warning("Could not delete file %s", p)

    db.session.delete(job)
    db.session.commit()
    return jsonify({'message': 'Job deleted'}), 200
