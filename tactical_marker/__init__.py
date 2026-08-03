"""tactical_marker — auto-annotate football clips with tactical markings.

Detects and tracks players, then draws ground rings under them, a spotlight that
follows the key player, and motion arrows.

    from tactical_marker import MarkerConfig, process
    process(MarkerConfig(input_path="match.mp4", output_path="marked.mp4"))
"""
from .config import MarkerConfig
from .processor import process

__all__ = ["MarkerConfig", "process"]
