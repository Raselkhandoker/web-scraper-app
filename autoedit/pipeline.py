"""End-to-end pipeline: upload a video in, get an edited video (+ clips) out."""
from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import dataclass, field
from typing import List, Optional

from . import captions as captions_mod
from . import ffmpeg_utils, highlights as highlights_mod, render, silence
from .timeline import TimelineMap
from .transcribe import Transcript, Word, transcribe

log = logging.getLogger("autoedit.pipeline")


@dataclass
class Config:
    remove_silence: bool = True
    captions: bool = True
    highlights: bool = True
    highlight_count: int = 3
    max_gap: float = 0.4          # cut silences longer than this (seconds)
    model_size: str = "base"      # whisper model
    anthropic_model: str = highlights_mod.DEFAULT_MODEL
    language: Optional[str] = None


@dataclass
class Result:
    main_output: Optional[str] = None
    clips: List[str] = field(default_factory=list)
    original_duration: float = 0.0
    edited_duration: float = 0.0
    transcript_available: bool = False
    notes: List[str] = field(default_factory=list)

    @property
    def seconds_removed(self) -> float:
        return max(0.0, self.original_duration - self.edited_duration)


def process(
    input_path: str,
    output_dir: str,
    config: Config | None = None,
    workdir: Optional[str] = None,
) -> Result:
    config = config or Config()
    if not os.path.isfile(input_path):
        raise FileNotFoundError(input_path)
    os.makedirs(output_dir, exist_ok=True)

    info = ffmpeg_utils.probe(input_path)
    result = Result(original_duration=info.duration, edited_duration=info.duration)
    log.info(
        "Input: %dx%d, %.1fs, %.2ffps, audio=%s",
        info.width, info.height, info.duration, info.fps, info.has_audio,
    )

    tmp_ctx = tempfile.TemporaryDirectory(prefix="autoedit-")
    work = workdir or tmp_ctx.name
    os.makedirs(work, exist_ok=True)

    try:
        transcript = _maybe_transcribe(input_path, work, info, config, result)
        words = transcript.words if transcript else []

        keep = _compute_keep_segments(input_path, info, words, config, result)
        tmap = TimelineMap(keep)
        result.edited_duration = tmap.output_duration

        ass_path = _build_main_captions(words, tmap, info, work, config, result)

        base = os.path.splitext(os.path.basename(input_path))[0]
        main_out = os.path.join(output_dir, f"{base}_edited.mp4")
        render.render_cut(input_path, keep, main_out, info, ass_path=ass_path)
        result.main_output = main_out

        if config.highlights:
            result.clips = _render_highlights(
                input_path, transcript, info, output_dir, work, base, config, result
            )
    finally:
        tmp_ctx.cleanup()

    return result


def _maybe_transcribe(input_path, work, info, config, result) -> Optional[Transcript]:
    need = config.captions or config.highlights
    if not need or not info.has_audio:
        if need and not info.has_audio:
            result.notes.append("Input has no audio; captions/highlights limited.")
        return None
    try:
        wav = ffmpeg_utils.extract_audio(input_path, os.path.join(work, "audio.wav"))
        transcript = transcribe(wav, model_size=config.model_size, language=config.language)
        result.transcript_available = True
        return transcript
    except Exception as exc:  # noqa: BLE001
        log.warning("Transcription unavailable (%s).", exc)
        result.notes.append(
            f"Transcription failed ({exc}). Falling back to audio-based silence "
            "detection; captions skipped."
        )
        return None


def _compute_keep_segments(input_path, info, words, config, result):
    if not config.remove_silence:
        return [(0.0, info.duration)]
    if words:
        keep = silence.keep_segments_from_words(words, info.duration, max_gap=config.max_gap)
    else:
        keep = silence.keep_segments_from_audio(input_path, info.duration, min_silence=config.max_gap)
    log.info("Keeping %d segments (%.1fs of %.1fs).",
             len(keep), silence.total_kept(keep), info.duration)
    return keep


def _build_main_captions(words, tmap, info, work, config, result) -> Optional[str]:
    if not (config.captions and words):
        return None
    edited_words: List[Word] = []
    for w in words:
        ns = tmap.map(w.start)
        if ns is None:
            continue
        ne = tmap.map_clamped(w.end)
        if ne <= ns:
            ne = ns + 0.2
        edited_words.append(Word(start=ns, end=ne, text=w.text))
    if not edited_words:
        return None
    ass = captions_mod.build_ass(edited_words, info.width, info.height)
    path = os.path.join(work, "captions_main.ass")
    with open(path, "w", encoding="utf-8") as f:
        f.write(ass)
    return path


def _render_highlights(input_path, transcript, info, output_dir, work, base, config, result):
    duration = info.duration
    hl = highlights_mod.select_highlights(
        transcript or Transcript(segments=[]),
        duration,
        count=config.highlight_count,
        model=config.anthropic_model,
    )
    clips: List[str] = []
    for i, h in enumerate(hl, 1):
        ass_path = None
        if config.captions and transcript:
            ass_path = _build_clip_captions(transcript.words, h.start, h.end, work, i)
        out = os.path.join(output_dir, f"{base}_highlight_{i}.mp4")
        render.render_clip(input_path, h.start, h.end, out, info, ass_path=ass_path, vertical=True)
        clips.append(out)
    log.info("Rendered %d highlight clip(s).", len(clips))
    return clips


def _build_clip_captions(words, start, end, work, index) -> Optional[str]:
    clip_words = [
        Word(start=w.start - start, end=w.end - start, text=w.text)
        for w in words
        if w.end > start and w.start < end
    ]
    if not clip_words:
        return None
    ass = captions_mod.build_ass(clip_words, 1080, 1920)
    path = os.path.join(work, f"captions_clip_{index}.ass")
    with open(path, "w", encoding="utf-8") as f:
        f.write(ass)
    return path
