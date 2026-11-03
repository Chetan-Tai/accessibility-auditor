# backend/sam_test/python/measure.py
from __future__ import annotations

import asyncio
import math
from pathlib import Path
from typing import Any

from sam_api import segment_image
from meta_sam_parser import decode_mask_to_raster

# Standard US Letter paper, in inches (used as the calibration reference)
PAPER_WIDTH_IN = 8.5
PAPER_HEIGHT_IN = 11.0
PAPER_AREA_IN2 = PAPER_WIDTH_IN * PAPER_HEIGHT_IN

ADA_MIN_CLEAR_WIDTH_IN = 32.0

EXPECTED_RATIO = PAPER_WIDTH_IN / PAPER_HEIGHT_IN  # 0.773
RATIO_TOLERANCE = 0.20  # allow 20% deviation before flagging a bad angle

# Fixed uncertainty margin, in inches — based on real validation against
# 2 test doors (measured errors of 0.2in and 1.1in). A flat inch margin,
# not a percentage, since segmentation noise is roughly constant in
# pixels/inches regardless of the door's actual size.
UNCERTAINTY_INCHES = 2.0


def box_dims(record) -> tuple[float, float]:
    return (record.right - record.left), (record.bottom - record.top)


def angle_is_acceptable(box) -> bool:
    w, h = box_dims(box)
    if w == 0 or h == 0:
        return False
    observed = w / h
    portrait_dev = abs(observed - EXPECTED_RATIO) / EXPECTED_RATIO
    landscape_dev = abs(observed - (1 / EXPECTED_RATIO)) / (1 / EXPECTED_RATIO)
    return min(portrait_dev, landscape_dev) <= RATIO_TOLERANCE


async def scan_door(image_path: Path) -> dict[str, Any]:
    door_result, paper_result = await asyncio.gather(
        segment_image(image_path, "door"),
        segment_image(image_path, "paper"),
    )

    door_boxes = [r for r in door_result.records if r.kind == "box"]
    paper_boxes = [r for r in paper_result.records if r.kind == "box"]
    paper_masks = [r for r in paper_result.records if r.kind == "mask"]

    if not door_boxes:
        return {"feature": "door", "status": "NOT_DETECTED"}

    if not paper_boxes or not paper_masks:
        return {
            "feature": "door",
            "status": "NO_CALIBRATION",
            "reason": "No reference paper detected",
        }

    if not angle_is_acceptable(paper_boxes[0]):
        return {
            "feature": "door",
            "status": "ANGLE_TOO_SKEWED",
            "reason": "Reference paper appears distorted — retake photo facing the door more directly",
        }

    paper_px_area = sum(decode_mask_to_raster(paper_masks[0].mask))
    if paper_px_area <= 0:
        return {
            "feature": "door",
            "status": "NO_CALIBRATION",
            "reason": "Reference paper mask had zero area",
        }

    scale_in_per_px = math.sqrt(PAPER_AREA_IN2 / paper_px_area)

    width_px, _ = box_dims(door_boxes[0])
    width_in = width_px * scale_in_per_px
    width_low = width_in - UNCERTAINTY_INCHES
    width_high = width_in + UNCERTAINTY_INCHES

    if width_low >= ADA_MIN_CLEAR_WIDTH_IN:
        verdict = "PASS"
    elif width_high < ADA_MIN_CLEAR_WIDTH_IN:
        verdict = "BLOCKING"
    else:
        verdict = "BORDERLINE"

    return {
        "feature": "door",
        "status": "MEASURED",
        "estimated_width_in": round(width_in, 1),
        "estimated_width_range_in": [round(width_low, 1), round(width_high, 1)],
        "ada_minimum_in": ADA_MIN_CLEAR_WIDTH_IN,
        "verdict": verdict,
    }