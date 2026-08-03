"""
ai_backends.py
--------------
Optional AI engine that sends the whole video to a hosted model instead of
processing it locally with OpenCV.

This uses Replicate (https://replicate.com). To use it you need:

    REPLICATE_API_TOKEN   -- your API token (required)
    REPLICATE_MODEL       -- "owner/model" or "owner/model:version" of a
                             video-stylisation model (optional; a sensible
                             default is used).

The flow is:
    1. Upload the input file to Replicate's file store -> get a URL.
    2. Create a prediction with that URL as input.
    3. Poll until it finishes.
    4. Download the resulting video to ``output_path``.

Everything is done with ``requests`` (already a project dependency) so no
extra SDK is needed. If the token is missing we raise a clear error so the
caller can fall back to the local engine.
"""

from __future__ import annotations

import os
import time
import logging
from typing import Callable, Optional

import requests

logger = logging.getLogger(__name__)

ProgressCB = Optional[Callable[[int], None]]

API_BASE = "https://api.replicate.com/v1"

# A video-to-video stylisation model. Override with REPLICATE_MODEL if you
# prefer a different one. The ":version" hash may be required by Replicate
# for some models; the code resolves the latest version automatically when
# only "owner/model" is given.
DEFAULT_MODEL = "fofr/tooncrafter"


class ReplicateError(RuntimeError):
    pass


class ReplicateAnimator:
    def __init__(
        self,
        token: Optional[str] = None,
        model: Optional[str] = None,
        input_key: str = "video",
    ):
        self.token = token or os.getenv("REPLICATE_API_TOKEN")
        if not self.token:
            raise ReplicateError(
                "REPLICATE_API_TOKEN is not set. Add it to your environment "
                "to use the AI engine, or use the free local engine instead."
            )
        self.model = model or os.getenv("REPLICATE_MODEL", DEFAULT_MODEL)
        self.input_key = os.getenv("REPLICATE_INPUT_KEY", input_key)

    # -- public ------------------------------------------------------------- #

    def process(
        self,
        input_path: str,
        output_path: str,
        style: str = "cartoon",
        progress_cb: ProgressCB = None,
        poll_interval: float = 3.0,
        timeout: float = 1800.0,
    ) -> dict:
        if progress_cb:
            progress_cb(2)

        file_url = self._upload(input_path)
        if progress_cb:
            progress_cb(10)

        version = self._resolve_version()
        prediction = self._create_prediction(
            version, {self.input_key: file_url, "prompt": style}
        )

        output_url = self._await_prediction(
            prediction, progress_cb, poll_interval, timeout
        )
        self._download(output_url, output_path)
        if progress_cb:
            progress_cb(100)

        return {"engine": "ai", "model": self.model, "style": style,
                "has_audio": False}

    # -- internals ---------------------------------------------------------- #

    @property
    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}

    def _upload(self, path: str) -> str:
        with open(path, "rb") as fh:
            resp = requests.post(
                f"{API_BASE}/files",
                headers=self._headers,
                files={"content": (os.path.basename(path), fh,
                                   "application/octet-stream")},
                timeout=120,
            )
        if resp.status_code >= 300:
            raise ReplicateError(f"File upload failed: {resp.status_code} {resp.text}")
        data = resp.json()
        url = data.get("urls", {}).get("get") or data.get("url")
        if not url:
            raise ReplicateError("Upload succeeded but no file URL was returned.")
        return url

    def _resolve_version(self) -> str:
        if ":" in self.model:
            return self.model.split(":", 1)[1]
        resp = requests.get(
            f"{API_BASE}/models/{self.model}", headers=self._headers, timeout=30
        )
        if resp.status_code >= 300:
            raise ReplicateError(
                f"Could not look up model '{self.model}': "
                f"{resp.status_code} {resp.text}"
            )
        version = resp.json().get("latest_version", {}).get("id")
        if not version:
            raise ReplicateError(f"Model '{self.model}' has no available version.")
        return version

    def _create_prediction(self, version: str, model_input: dict) -> dict:
        resp = requests.post(
            f"{API_BASE}/predictions",
            headers={**self._headers, "Content-Type": "application/json"},
            json={"version": version, "input": model_input},
            timeout=60,
        )
        if resp.status_code >= 300:
            raise ReplicateError(
                f"Prediction failed to start: {resp.status_code} {resp.text}"
            )
        return resp.json()

    def _await_prediction(
        self, prediction: dict, progress_cb: ProgressCB,
        poll_interval: float, timeout: float,
    ) -> str:
        get_url = prediction.get("urls", {}).get("get")
        if not get_url:
            raise ReplicateError("Prediction response missing polling URL.")

        deadline = time.time() + timeout
        pct = 15
        while time.time() < deadline:
            resp = requests.get(get_url, headers=self._headers, timeout=30)
            data = resp.json()
            status = data.get("status")

            if status == "succeeded":
                out = data.get("output")
                url = out[-1] if isinstance(out, list) else out
                if not url:
                    raise ReplicateError("Model succeeded but returned no output.")
                return url
            if status in ("failed", "canceled"):
                raise ReplicateError(f"AI job {status}: {data.get('error')}")

            if progress_cb and pct < 90:
                pct += 2
                progress_cb(pct)
            time.sleep(poll_interval)

        raise ReplicateError("AI job timed out.")

    def _download(self, url: str, output_path: str) -> None:
        with requests.get(url, stream=True, timeout=300) as resp:
            resp.raise_for_status()
            with open(output_path, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=1 << 16):
                    fh.write(chunk)
