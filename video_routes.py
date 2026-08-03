"""
video_routes.py
---------------
API endpoints for the video-to-animation feature. Registered as its own
blueprint so the existing scraper routes stay untouched.

Endpoints (all under /api/video):
    GET    /styles                 -> available styles + engines
    POST   /jobs                   -> upload a video + options, start a job
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

from flask import Blueprint, request, jsonify, send_file, current_app

from models import db, VideoJob
from video_animator import VideoAnimator, STYLES, parse_cut_segments

logger = logging.getLogger(__name__)
video_bp = Blueprint('video', __name__, url_prefix='/api/video')

ALLOWED_EXT = {'.mp4', '.mov', '.avi', '.mkv', '.webm', '.m4v', '.mpg', '.mpeg'}


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


# --------------------------------------------------------------------------- #
#  Background worker
# --------------------------------------------------------------------------- #

def run_video_job(app, job_id: int):
    """Process one video job. Runs inside its own app context / thread."""
    with app.app_context():
        job = VideoJob.query.get(job_id)
        if not job:
            return

        def set_progress(pct: int):
            # Fresh session write so the polling endpoint sees updates.
            j = VideoJob.query.get(job_id)
            if j:
                j.progress = int(pct)
                db.session.commit()

        try:
            job.status = 'running'
            job.started_at = datetime.utcnow()
            db.session.commit()

            input_path = os.path.join(_uploads_dir(), job.source_filename)
            out_name = f"anim_{job.id}_{uuid.uuid4().hex[:8]}.mp4"
            output_path = os.path.join(_outputs_dir(), out_name)

            if job.engine == 'ai':
                # Imported lazily so a missing token never breaks local mode.
                from ai_backends import ReplicateAnimator
                animator = ReplicateAnimator()
                stats = animator.process(
                    input_path, output_path,
                    style=job.style, progress_cb=set_progress,
                )
            else:
                animator = VideoAnimator()
                stats = animator.process(
                    input_path, output_path,
                    style=job.style,
                    cut_segments=parse_cut_segments(job.cut_segments),
                    keep_audio=job.keep_audio,
                    progress_cb=set_progress,
                )

            job = VideoJob.query.get(job_id)
            job.output_filename = out_name
            job.stats = json.dumps(stats)
            job.progress = 100
            job.status = 'completed'
            job.completed_at = datetime.utcnow()
            db.session.commit()
            logger.info("Video job %s completed (%s / %s)",
                        job_id, job.engine, job.style)

        except Exception as e:  # noqa: BLE001
            logger.exception("Video job %s failed", job_id)
            job = VideoJob.query.get(job_id)
            if job:
                job.status = 'failed'
                job.error_message = str(e)
                job.completed_at = datetime.utcnow()
                db.session.commit()


# --------------------------------------------------------------------------- #
#  Routes
# --------------------------------------------------------------------------- #

@video_bp.route('/styles', methods=['GET'])
def get_styles():
    return jsonify({
        'styles': [{'id': k, 'description': v} for k, v in STYLES.items()],
        'engines': [
            {'id': 'local', 'name': 'Local cartoon filter (free, offline)'},
            {'id': 'ai', 'name': 'AI service (Replicate - needs API token)'},
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
    if ext not in ALLOWED_EXT:
        return jsonify({
            'error': f'Unsupported file type "{ext}". '
                     f'Allowed: {", ".join(sorted(ALLOWED_EXT))}'
        }), 400

    style = request.form.get('style', 'cartoon')
    if style not in STYLES:
        return jsonify({'error': f'Unknown style "{style}"'}), 400
    engine = request.form.get('engine', 'local')
    if engine not in ('local', 'ai'):
        return jsonify({'error': f'Unknown engine "{engine}"'}), 400

    # Save the upload with a unique name.
    stored_name = f"{uuid.uuid4().hex}{ext}"
    f.save(os.path.join(_uploads_dir(), stored_name))

    keep_audio = request.form.get('keep_audio', 'true').lower() != 'false'

    job = VideoJob(
        job_name=request.form.get('job_name') or f.filename,
        source_filename=stored_name,
        original_name=f.filename,
        engine=engine,
        style=style,
        cut_segments=request.form.get('cut_segments', '').strip(),
        keep_audio=keep_audio,
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
