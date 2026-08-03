"""Telestration drawing primitives (OpenCV).

Every function draws directly onto a BGR frame (numpy array). Coordinates are in
pixels. These match the look of pro tactical-analysis overlays: a perspective
ground ellipse under a player's feet, a vertical spotlight beam, and thick
movement arrows.
"""
from __future__ import annotations

import cv2
import numpy as np


def ground_ellipse(img, cx, cy, width, color=(60, 60, 220), alpha=0.55,
                   outline=(255, 255, 255)):
    """A flattened ellipse on the ground under a player (cy = feet position)."""
    width = max(30, int(width))
    height = int(width * 0.42)
    ax, ay = width // 2, height // 2
    overlay = img.copy()
    cv2.ellipse(overlay, (int(cx), int(cy)), (ax, ay), 0, 0, 360, color, -1)
    cv2.addWeighted(overlay, alpha, img, 1 - alpha, 0, img)
    if outline:
        cv2.ellipse(img, (int(cx), int(cy)), (ax, ay), 0, 0, 360, outline, 2,
                    lineType=cv2.LINE_AA)


def player_ring(img, cx, cy, width, color=(255, 255, 255), thickness=4):
    """An open ring outline around a player (bigger, upright ellipse)."""
    w = max(40, int(width))
    cv2.ellipse(img, (int(cx), int(cy)), (int(w * 0.6), int(w * 0.75)),
                0, 0, 360, color, thickness, lineType=cv2.LINE_AA)


def spotlight(img, cx, cy_feet, bottom_w, color=(0, 180, 255), alpha=0.28):
    """Vertical light beam from the top of the frame down to the player."""
    top_w = int(bottom_w * 0.65)
    bot_w = int(bottom_w)
    overlay = img.copy()
    pts = np.array([[cx - top_w // 2, 0], [cx + top_w // 2, 0],
                    [cx + bot_w // 2, int(cy_feet)],
                    [cx - bot_w // 2, int(cy_feet)]], np.int32)
    cv2.fillPoly(overlay, [pts], color)
    cv2.addWeighted(overlay, alpha, img, 1 - alpha, 0, img)


def arrow(img, p1, p2, color=(60, 230, 90), thickness=14, tip=0.22):
    """Thick movement/pass arrow with a white outline for contrast."""
    p1 = (int(p1[0]), int(p1[1]))
    p2 = (int(p2[0]), int(p2[1]))
    cv2.arrowedLine(img, p1, p2, (255, 255, 255), thickness + 6,
                    tipLength=tip, line_type=cv2.LINE_AA)
    cv2.arrowedLine(img, p1, p2, color, thickness, tipLength=tip,
                    line_type=cv2.LINE_AA)
