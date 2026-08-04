"""Speech-to-text using faster-whisper, producing word-level timestamps.

The model is downloaded from HuggingFace on first use and cached locally, so the
first run needs network access. Everything downstream (silence cutting, caption
timing, highlight selection) is driven by the :class:`Word` list this returns.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional

log = logging.getLogger("autoedit.transcribe")


@dataclass
class Word:
    start: float
    end: float
    text: str

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass
class Segment:
    start: float
    end: float
    text: str
    words: List[Word] = field(default_factory=list)


@dataclass
class Transcript:
    segments: List[Segment]
    language: str = "en"

    @property
    def words(self) -> List[Word]:
        out: List[Word] = []
        for seg in self.segments:
            out.extend(seg.words)
        return out

    @property
    def text(self) -> str:
        return " ".join(s.text.strip() for s in self.segments).strip()


def transcribe(
    audio_path: str,
    model_size: str = "base",
    language: Optional[str] = None,
    device: str = "auto",
    compute_type: str = "int8",
) -> Transcript:
    """Transcribe ``audio_path`` and return a :class:`Transcript` with word times."""
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "faster-whisper is required for transcription. "
            "Install it with `pip install faster-whisper`."
        ) from exc

    if device == "auto":
        device = _pick_device()

    log.info("Loading Whisper model '%s' on %s ...", model_size, device)
    model = WhisperModel(model_size, device=device, compute_type=compute_type)

    log.info("Transcribing ...")
    seg_iter, info = model.transcribe(
        audio_path,
        language=language,
        word_timestamps=True,
        vad_filter=True,
    )

    segments: List[Segment] = []
    for s in seg_iter:
        words = [
            Word(start=w.start, end=w.end, text=w.word.strip())
            for w in (s.words or [])
            if w.word and w.word.strip()
        ]
        segments.append(Segment(start=s.start, end=s.end, text=s.text.strip(), words=words))

    log.info("Transcribed %d segments (%s).", len(segments), info.language)
    return Transcript(segments=segments, language=info.language)


def _pick_device() -> str:
    try:
        import torch  # type: ignore

        if torch.cuda.is_available():
            return "cuda"
    except Exception:
        pass
    return "cpu"
