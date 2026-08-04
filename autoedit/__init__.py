"""autoedit - upload a video, get an auto-edited MP4 back.

Removes dead air, burns in word-by-word captions, and cuts short highlight
clips. Uses ffmpeg for editing, faster-whisper for transcription, and Claude
(optional) for picking highlight moments.
"""
from .pipeline import Config, Result, process

__all__ = ["Config", "Result", "process"]
__version__ = "0.1.0"
