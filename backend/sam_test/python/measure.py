# backend/sam_test/python/measure.py
from __future__ import annotations

import asyncio
import math
from pathlib import Path
from typing import Any

from PIL import Image

from sam_api import segment_image
from meta_sam_parser import decode_mask_to_raster

PAPER_WIDTH_IN = 8.5
PAPER_HEIGHT_IN = 11.0
PAPER_AREA_IN2 = PAPER_WIDTH_IN * PAPER_HEIGHT_IN

ADA_MIN_CLEAR_WIDTH_IN = 32.0

EXPECTED_RATIO = PAPER_WIDTH_IN / PAPER_HEIGHT_IN
RATIO_TOLERANCE = 0.20

UNCERTAINTY_INCHES = 2.0


def box_dims(record) -> tuple[float, float]:
    return (record.right - record.left), (record.bottom - record.top)


def box_to_relative(record, img_w: int, img_h: int) -> dict:
    """Same percentage convention as survey.py's boxes, so the frontend can
    overlay door/paper boxes using one consistent format."""
    return {
        "left_pct": round(100 * record.left / img_w, 1),
        "top_pct": round(100 * record.top / img_h, 1),
        "right_pct": round(100 * record.right / img_w, 1),
        "bottom_pct": round(100 * record.bottom / img_h, 1),
    }


def paper_ratio_deviation(box) -> float | None:
    """How far this paper's observed box ratio deviates from the true
    8.5:11 ratio. Lower = more face-on, more trustworthy calibration."""
    w, h = box_dims(box)
    if w == 0 or h == 0:
        return None
    observed = w / h
    portrait_dev = abs(observed - EXPECTED_RATIO) / EXPECTED_RATIO
    landscape_dev = abs(observed - (1 / EXPECTED_RATIO)) / (1 / EXPECTED_RATIO)
    return min(portrait_dev, landscape_dev)


def angle_is_acceptable(box) -> bool:
    dev = paper_ratio_deviation(box)
    return dev is not None and dev <= RATIO_TOLERANCE


def _verdict_for(width_low: float, width_high: float) -> str:
    if width_low >= ADA_MIN_CLEAR_WIDTH_IN:
        return "PASS"
    if width_high < ADA_MIN_CLEAR_WIDTH_IN:
        return "BLOCKING"
    return "BORDERLINE"


async def scan_door(image_path: Path) -> dict[str, Any]:
    """Single-photo door measurement (kept for simple/manual use)."""
    return await scan_door_from_photos([image_path])


async def scan_door_from_photos(image_paths: list[Path]) -> dict[str, Any]:
    """Measure door width across one or more photos of the same door.
    Uses whichever photo has the most face-on (least distorted) reference
    paper for the actual calibration, rather than averaging indiscriminately."""
    candidates = []
    per_photo_deviation: list[dict[str, Any]] = []

    for path in image_paths:
        door_result, paper_result = await asyncio.gather(
            segment_image(path, "door"),
            segment_image(path, "paper"),
        )
        door_boxes = [r for r in door_result.records if r.kind == "box"]
        paper_boxes = [r for r in paper_result.records if r.kind == "box"]
        paper_masks = [r for r in paper_result.records if r.kind == "mask"]

        if not door_boxes or not paper_boxes or not paper_masks:
            per_photo_deviation.append({"path": str(path), "deviation": None, "valid": False})
            continue

        deviation = paper_ratio_deviation(paper_boxes[0])
        if deviation is None:
            per_photo_deviation.append({"path": str(path), "deviation": None, "valid": False})
            continue

        is_acceptable = deviation <= RATIO_TOLERANCE
        per_photo_deviation.append({"path": str(path), "deviation": round(deviation, 4), "valid": is_acceptable})

        if not is_acceptable:
            continue

        paper_px_area = sum(decode_mask_to_raster(paper_masks[0].mask))
        if paper_px_area <= 0:
            continue

        with Image.open(path) as img:
            img_w, img_h = img.size

        candidates.append(
            {
                "path": str(path),
                "deviation": deviation,
                "door_box": door_boxes[0],
                "paper_box": paper_boxes[0],
                "paper_px_area": paper_px_area,
                "img_w": img_w,
                "img_h": img_h,
            }
        )

    if not candidates:
        return {
            "feature": "door",
            "status": "NO_VALID_PHOTO",
            "reason": "No photo had both a detected door and a usable, face-on calibration reference",
            "photos_considered": len(image_paths),
            "photo_angle_deviations": per_photo_deviation,
            "ratio_tolerance": RATIO_TOLERANCE,
        }

    candidates.sort(key=lambda c: c["deviation"])
    best = candidates[0]

    scale_in_per_px = math.sqrt(PAPER_AREA_IN2 / best["paper_px_area"])
    width_px, _ = box_dims(best["door_box"])
    width_in = width_px * scale_in_per_px
    width_low = width_in - UNCERTAINTY_INCHES
    width_high = width_in + UNCERTAINTY_INCHES

    return {
        "feature": "door",
        "status": "MEASURED",
        "estimated_width_in": round(width_in, 1),
        "estimated_width_range_in": [round(width_low, 1), round(width_high, 1)],
        "ada_minimum_in": ADA_MIN_CLEAR_WIDTH_IN,
        "verdict": _verdict_for(width_low, width_high),
        "photos_considered": len(image_paths),
        "valid_candidates": len(candidates),
        "best_photo": best["path"],
        "best_photo_angle_deviation": round(best["deviation"], 4),
        "best_photo_door_box": box_to_relative(best["door_box"], best["img_w"], best["img_h"]),
        "best_photo_paper_box": box_to_relative(best["paper_box"], best["img_w"], best["img_h"]),
        "photo_angle_deviations": per_photo_deviation,
        "ratio_tolerance": RATIO_TOLERANCE,
    }