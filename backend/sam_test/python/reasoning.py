# backend/sam_test/python/reasoning.py
from __future__ import annotations

import json
from enum import Enum
from pathlib import Path

from pydantic import BaseModel
from sam_api import client, image_data_url

SPARK_MODEL = "muse-spark-1.3"


class ConcernLevel(str, Enum):
    NONE = "NONE"
    LOW = "LOW"
    HIGH = "HIGH"


class OverallVerdict(str, Enum):
    ACCESSIBLE = "ACCESSIBLE"
    NOT_ACCESSIBLE = "NOT_ACCESSIBLE"
    NEEDS_VERIFICATION = "NEEDS_VERIFICATION"


class Flag(BaseModel):
    feature: str
    observation: str
    concern_level: ConcernLevel


class AccessibilityAssessment(BaseModel):
    overall_verdict: OverallVerdict
    summary: str
    flags: list[Flag]
    remediation: str


SYSTEM_PROMPT = """You are an accessibility auditor assistant. You are given one or \
more photos of the same building entrance, taken from different viewpoints, along \
with structured detection data about what objects were found across those photos. \
Synthesize ONE coherent assessment using all photos together — if something is \
visible in one photo but occluded in another, treat it as present.

Each detected object includes a bounding box as a percentage of ITS OWN photo's \
frame (left_pct/top_pct/right_pct/bottom_pct). Boxes from different photos are not \
directly comparable to each other, since camera angle and distance differ between \
photos — but boxes within the SAME photo are directly comparable. Use same-photo \
box positions to reason about real spatial relationships (e.g. whether a ramp's box \
is directly adjacent to or overlapping a door's box, suggesting a usable approach, \
versus a stairs box sitting across the same approach, suggesting it is blocked) \
rather than estimating spatial layout purely by looking at the image.

Do not invent precise measurements for anything other than the door width figure \
given to you, if present. For steps, thresholds, and ramp edges, describe their \
apparent scale only in relative, qualitative terms — never invented inches.

When flagging maneuvering clearance concerns near a door, specify whether the \
concern applies to the entering direction (push side) or exiting direction (pull \
side), since ADA clearance requirements differ significantly between them."""


def _normalize_survey_for_prompt(survey_result: dict, photo_labels: dict[str, str]) -> dict:
    """Relabel photo paths as 'Photo N' and present boxes per concept per photo,
    whether survey_result came from survey() (single photo, flat 'boxes') or
    survey_multi() (multiple photos, boxes grouped under 'by_photo')."""
    normalized = {}
    for concept, info in survey_result.items():
        entry = {"detected": info["detected"], "count": info["count"]}
        if "by_photo" in info:
            entry["by_photo"] = [
                {"photo": photo_labels.get(pb["photo"], pb["photo"]), "boxes": pb["boxes"]}
                for pb in info["by_photo"]
            ]
        elif "boxes" in info and info["boxes"]:
            only_label = next(iter(photo_labels.values()), "Photo 1")
            entry["by_photo"] = [{"photo": only_label, "boxes": info["boxes"]}]
        else:
            entry["by_photo"] = []
        normalized[concept] = entry
    return normalized


async def reason_about_scene(
    image_paths: list[Path], survey_result: dict, door_result: dict | None = None
) -> AccessibilityAssessment:
    photo_labels = {str(p): f"Photo {i + 1}" for i, p in enumerate(image_paths)}
    detections_for_prompt = _normalize_survey_for_prompt(survey_result, photo_labels)

    user_text = (
        f"You are looking at {len(image_paths)} photo(s) of the same entrance/space, "
        f"labeled Photo 1 through Photo {len(image_paths)} in the order the images "
        "appear below.\n\n"
        "Detected objects, with boxes grouped by which photo they came from "
        "(see system prompt for how to use box positions):\n"
        f"{json.dumps(detections_for_prompt, indent=2)}\n\n"
    )
    if door_result:
        user_text += (
            "Door measurement data (already computed from the most reliable photo "
            "— do not re-estimate):\n"
            f"{json.dumps(door_result, indent=2)}\n\n"
        )
    user_text += "Based on all the photos and this data, produce the accessibility assessment."

    content = [{"type": "text", "text": user_text}]
    for path in image_paths:
        content.append({"type": "image_url", "image_url": {"url": image_data_url(path)}})

    async with client() as api:
        completion = await api.beta.chat.completions.parse(
            model=SPARK_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
            response_format=AccessibilityAssessment,
        )

    return completion.choices[0].message.parsed