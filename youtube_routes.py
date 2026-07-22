from flask import Blueprint, request, jsonify
import logging

from youtube_tool import (
    YouTubeAPIError,
    keyword_research,
    channel_analysis,
    video_seo_score,
)

logger = logging.getLogger(__name__)
youtube_bp = Blueprint('youtube', __name__, url_prefix='/api/youtube')


@youtube_bp.route('/keyword-research', methods=['POST'])
def api_keyword_research():
    data = request.get_json() or {}
    keyword = (data.get('keyword') or '').strip()
    if not keyword:
        return jsonify({'error': 'keyword is required'}), 400

    try:
        result = keyword_research(keyword)
        return jsonify(result), 200
    except YouTubeAPIError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f'Error in keyword research: {str(e)}')
        return jsonify({'error': str(e)}), 500


@youtube_bp.route('/channel-analysis', methods=['POST'])
def api_channel_analysis():
    data = request.get_json() or {}
    channel = (data.get('channel') or '').strip()
    if not channel:
        return jsonify({'error': 'channel is required'}), 400

    try:
        result = channel_analysis(channel)
        return jsonify(result), 200
    except YouTubeAPIError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f'Error in channel analysis: {str(e)}')
        return jsonify({'error': str(e)}), 500


@youtube_bp.route('/video-score', methods=['POST'])
def api_video_score():
    data = request.get_json() or {}
    video = (data.get('video') or '').strip()
    if not video:
        return jsonify({'error': 'video is required'}), 400

    try:
        result = video_seo_score(video)
        return jsonify(result), 200
    except YouTubeAPIError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error(f'Error in video SEO score: {str(e)}')
        return jsonify({'error': str(e)}), 500
