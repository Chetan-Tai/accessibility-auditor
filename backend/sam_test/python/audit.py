# backend/sam_test/python/audit.py
import argparse
import asyncio
import json
from pathlib import Path

from survey import survey
from measure import scan_door
from reasoning import reason_about_scene


async def run_audit(image_path: Path) -> dict:
    survey_result = await survey(image_path)

    door_result = None
    if survey_result.get("door", {}).get("detected"):
        door_result = await scan_door(image_path)

    assessment = await reason_about_scene(image_path, survey_result, door_result)

    return {
        "survey": survey_result,
        "door_measurement": door_result,
        "assessment": assessment.model_dump(),
    }


def main():
    parser = argparse.ArgumentParser(description="Full accessibility audit of one photo.")
    parser.add_argument("image", type=Path)
    args = parser.parse_args()
    result = asyncio.run(run_audit(args.image))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()