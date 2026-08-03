"""Pitch detection helpers.

Used to keep only players who are actually on the (green) pitch, so spectators,
staff and dugout people don't get marked, and to optionally colour rings by team
from jersey colour.
"""
from __future__ import annotations

import cv2
import numpy as np


def pitch_mask(frame):
    """Boolean mask of the green playing surface."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    # broad green range (covers bright and shadowed grass)
    lo = np.array([30, 40, 40])
    hi = np.array([90, 255, 255])
    mask = cv2.inRange(hsv, lo, hi)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE,
                            np.ones((25, 25), np.uint8))
    return mask > 0


def on_pitch(mask, x1, y1, x2, y2, min_ratio=0.03):
    """True if a box's feet sit on green grass (filters crowd/dugout)."""
    feet_y = int(y2)
    cx = int((x1 + x2) / 2)
    h, w = mask.shape
    # sample a small band just under the player's feet
    y0 = max(0, feet_y - 6)
    y1s = min(h, feet_y + 10)
    x0 = max(0, cx - 12)
    x1s = min(w, cx + 12)
    if y1s <= y0 or x1s <= x0:
        return False
    band = mask[y0:y1s, x0:x1s]
    return band.mean() > min_ratio


def jersey_color(frame, x1, y1, x2, y2):
    """Mean BGR of a player's torso region (for team clustering)."""
    h = y2 - y1
    ty0 = int(y1 + h * 0.20)
    ty1 = int(y1 + h * 0.55)
    tx0, tx1 = int(x1), int(x2)
    patch = frame[max(0, ty0):max(1, ty1), max(0, tx0):max(1, tx1)]
    if patch.size == 0:
        return np.array([128, 128, 128], np.float32)
    return patch.reshape(-1, 3).mean(axis=0)


def classify_teams(colors):
    """K-means (k=2) over jersey colours -> per-player team label 0/1.

    Returns a list of labels aligned with ``colors`` (empty -> []).
    """
    if len(colors) < 2:
        return [0] * len(colors)
    data = np.float32(np.stack(colors))
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
    _, labels, _ = cv2.kmeans(data, 2, None, crit, 3,
                              cv2.KMEANS_PP_CENTERS)
    return labels.flatten().tolist()
