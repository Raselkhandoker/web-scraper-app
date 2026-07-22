"""YouTube SEO research tools (vidIQ-style) built on the official YouTube Data API v3.

Three features:
- keyword_research: tag suggestions + estimated competition for a search term
- channel_analysis: channel stats + recent upload performance
- video_seo_score: SEO score/breakdown for a single video
"""
import os
import re
from collections import Counter

import requests

YOUTUBE_API_BASE = 'https://www.googleapis.com/youtube/v3'


class YouTubeAPIError(Exception):
    pass


def _api_key():
    key = os.getenv('YOUTUBE_API_KEY')
    if not key:
        raise YouTubeAPIError(
            'YOUTUBE_API_KEY is not set. Get a free API key from Google Cloud Console '
            '(enable "YouTube Data API v3") and add it to your .env file.'
        )
    return key


def _get(endpoint, params):
    params = {**params, 'key': _api_key()}
    response = requests.get(f'{YOUTUBE_API_BASE}/{endpoint}', params=params, timeout=15)
    if response.status_code != 200:
        try:
            message = response.json().get('error', {}).get('message', response.text)
        except ValueError:
            message = response.text
        raise YouTubeAPIError(f'YouTube API error ({response.status_code}): {message}')
    return response.json()


def extract_video_id(value):
    """Accept a raw video ID or a youtube.com/youtu.be URL."""
    value = value.strip()
    match = re.search(r'(?:v=|youtu\.be/|shorts/)([\w-]{11})', value)
    if match:
        return match.group(1)
    if re.fullmatch(r'[\w-]{11}', value):
        return value
    raise YouTubeAPIError('Could not parse a video ID from that input.')


def extract_channel_ref(value):
    """Return a dict describing how to look up the channel: by id or by handle."""
    value = value.strip()
    match = re.search(r'youtube\.com/channel/([\w-]+)', value)
    if match:
        return {'channelId': match.group(1)}
    match = re.search(r'youtube\.com/@([\w.-]+)', value)
    if match:
        return {'forHandle': '@' + match.group(1)}
    if value.startswith('@'):
        return {'forHandle': value}
    if re.fullmatch(r'UC[\w-]{22}', value):
        return {'channelId': value}
    return {'forHandle': value if value.startswith('@') else '@' + value}


def _video_stats(video_ids):
    if not video_ids:
        return []
    data = _get('videos', {
        'part': 'snippet,statistics,contentDetails',
        'id': ','.join(video_ids),
    })
    return data.get('items', [])


def keyword_research(keyword, max_results=15):
    """Search top videos for a keyword and derive tag suggestions + a rough
    competition estimate. There is no public search-volume API, so competition
    is approximated from how many videos rank and how large their view/subscriber
    counts are - it's directionally useful, not an exact number."""
    search_data = _get('search', {
        'part': 'snippet',
        'q': keyword,
        'type': 'video',
        'maxResults': max_results,
        'order': 'relevance',
    })
    video_ids = [item['id']['videoId'] for item in search_data.get('items', [])]
    videos = _video_stats(video_ids)

    tag_counter = Counter()
    total_views = 0
    top_videos = []
    for video in videos:
        stats = video.get('statistics', {})
        snippet = video.get('snippet', {})
        views = int(stats.get('viewCount', 0))
        total_views += views
        for tag in snippet.get('tags', []):
            tag_counter[tag.lower()] += 1
        top_videos.append({
            'title': snippet.get('title'),
            'channel': snippet.get('channelTitle'),
            'video_id': video.get('id'),
            'views': views,
            'likes': int(stats.get('likeCount', 0)),
            'published_at': snippet.get('publishedAt'),
        })

    avg_views = total_views // len(videos) if videos else 0
    # Rough 0-100 competition estimate: more results + higher avg views = harder to rank.
    competition_score = min(100, int((len(videos) / max_results) * 40 + min(avg_views / 5000, 60)))

    suggested_tags = [tag for tag, _count in tag_counter.most_common(20)]

    return {
        'keyword': keyword,
        'results_analyzed': len(videos),
        'avg_views': avg_views,
        'estimated_competition': competition_score,
        'suggested_tags': suggested_tags,
        'top_videos': sorted(top_videos, key=lambda v: v['views'], reverse=True),
    }


def channel_analysis(channel_ref, recent_video_count=10):
    """Resolve a channel (by ID, @handle, or URL) and summarize its stats plus
    recent-upload performance."""
    lookup = extract_channel_ref(channel_ref)
    channel_data = _get('channels', {'part': 'snippet,statistics', **lookup})
    items = channel_data.get('items', [])
    if not items:
        raise YouTubeAPIError(f'No channel found for "{channel_ref}".')

    channel = items[0]
    stats = channel.get('statistics', {})
    channel_id = channel['id']
    subscriber_count = int(stats.get('subscriberCount', 0))

    search_data = _get('search', {
        'part': 'snippet',
        'channelId': channel_id,
        'type': 'video',
        'order': 'date',
        'maxResults': recent_video_count,
    })
    video_ids = [item['id']['videoId'] for item in search_data.get('items', [])
                 if item['id'].get('videoId')]
    recent_videos = _video_stats(video_ids)

    views = [int(v.get('statistics', {}).get('viewCount', 0)) for v in recent_videos]
    likes = [int(v.get('statistics', {}).get('likeCount', 0)) for v in recent_videos]
    comments = [int(v.get('statistics', {}).get('commentCount', 0)) for v in recent_videos]

    avg_views = sum(views) // len(views) if views else 0
    avg_engagement = (
        (sum(likes) + sum(comments)) / sum(views) * 100 if sum(views) else 0
    )

    return {
        'channel_id': channel_id,
        'title': channel['snippet']['title'],
        'subscriber_count': subscriber_count,
        'total_view_count': int(stats.get('viewCount', 0)),
        'video_count': int(stats.get('videoCount', 0)),
        'recent_videos_analyzed': len(recent_videos),
        'avg_recent_views': avg_views,
        'avg_engagement_rate_pct': round(avg_engagement, 2),
        'views_per_subscriber_pct': (
            round(avg_views / subscriber_count * 100, 2) if subscriber_count else None
        ),
        'recent_videos': [
            {
                'title': v['snippet']['title'],
                'video_id': v['id'],
                'views': int(v.get('statistics', {}).get('viewCount', 0)),
                'likes': int(v.get('statistics', {}).get('likeCount', 0)),
                'published_at': v['snippet']['publishedAt'],
            }
            for v in recent_videos
        ],
    }


def video_seo_score(video_ref):
    """Score a single video's on-page SEO signals (title/description/tags length,
    engagement rate) out of 100, with suggestions for what's weak."""
    video_id = extract_video_id(video_ref)
    videos = _video_stats([video_id])
    if not videos:
        raise YouTubeAPIError(f'No video found for "{video_ref}".')

    video = videos[0]
    snippet = video['snippet']
    stats = video.get('statistics', {})

    title = snippet.get('title', '')
    description = snippet.get('description', '')
    tags = snippet.get('tags', [])
    views = int(stats.get('viewCount', 0))
    likes = int(stats.get('likeCount', 0))
    comments = int(stats.get('commentCount', 0))
    engagement_rate = (likes + comments) / views * 100 if views else 0

    score = 0
    suggestions = []

    if 40 <= len(title) <= 70:
        score += 25
    else:
        suggestions.append('Title should be 40-70 characters for best search display.')

    if len(description) >= 250:
        score += 25
    else:
        suggestions.append('Description is short - aim for 250+ characters with keywords in the first two lines.')

    if len(tags) >= 8:
        score += 25
    else:
        suggestions.append(f'Only {len(tags)} tags set - add more relevant tags (aim for 10-15).')

    if engagement_rate >= 2:
        score += 25
    elif engagement_rate >= 0.5:
        score += 15
    else:
        suggestions.append('Engagement rate (likes+comments / views) is low - a stronger call to action may help.')

    return {
        'video_id': video_id,
        'title': title,
        'channel': snippet.get('channelTitle'),
        'views': views,
        'likes': likes,
        'comments': comments,
        'engagement_rate_pct': round(engagement_rate, 2),
        'tag_count': len(tags),
        'description_length': len(description),
        'seo_score': score,
        'suggestions': suggestions,
    }
