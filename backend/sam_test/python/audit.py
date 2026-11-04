# backend/sam_test/python/audit.py
import argparse
import asyncio
import json
from pathlib import Path

from survey import survey_multi
from measure import scan_door_from_photos
from reasoning import reason_about_scene


async def run_audit(image_paths: list[Path]) -> dict:
    survey_result = await survey_multi(image_paths)

    door_result = None
    if survey_result.get("door", {}).get("detected"):
        door_result = await scan_door_from_photos(image_paths)

    assessment = await reason_about_scene(image_paths, survey_result, door_result)

    return {
        "photos": [str(p) for p in image_paths],
        "survey": survey_result,
        "door_measurement": door_result,
        "assessment": assessment.model_dump(),
    }


def main():
    parser = argparse.ArgumentParser(description="Full accessibility audit across one or more photos of the same space.")
    parser.add_argument("images", type=Path, nargs="+")
    args = parser.parse_args()
    result = asyncio.run(run_audit(args.images))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()