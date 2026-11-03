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


SYSTEM_PROMPT = """You are an accessibility auditor assistant. You are given a photo \
of a building entrance along with structured detection data about what objects were \
found in the scene. Reason about wheelchair/mobility accessibility using the full \
photo and the structured data together.

Do not invent precise measurements for anything other than the door width figure \
given to you, if present. For steps, thresholds, and ramp edges, describe their \
apparent scale only in relative, qualitative terms (e.g., "appears to have a \
noticeable raised lip", "step looks roughly ankle height") — never invented inches."""


async def reason_about_scene(
    image_path: Path, survey_result: dict, door_result: dict | None = None
) -> AccessibilityAssessment:
    data_url = image_data_url(image_path)

    user_text = (
        "Detected objects in this scene (presence/absence):\n"
        f"{json.dumps(survey_result, indent=2)}\n\n"
    )
    if door_result:
        user_text += (
            "Door measurement data (already computed — do not re-estimate):\n"
            f"{json.dumps(door_result, indent=2)}\n\n"
        )
    user_text += "Based on the photo and this data, produce the accessibility assessment."

    async with client() as api:
        completion = await api.beta.chat.completions.parse(
            model=SPARK_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_text},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
            response_format=AccessibilityAssessment,
        )

    return completion.choices[0].message.parsed