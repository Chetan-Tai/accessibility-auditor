import argparse
import asyncio
import json
from pathlib import Path

from sam_api import segment_image

SURVEY_CONCEPTS = ["door", "stairs", "ramp", "floor obstruction", "handrail", "threshold"]


async def survey(image_path: Path) -> dict:
    results = await asyncio.gather(*(segment_image(image_path, c) for c in SURVEY_CONCEPTS))
    output = {}
    for concept, result in zip(SURVEY_CONCEPTS, results):
        boxes = [r for r in result.records if r.kind == "box"]
        output[concept] = {"detected": len(boxes) > 0, "count": len(boxes)}
    return output


def main():
    parser = argparse.ArgumentParser(description="Survey an image for accessibility-relevant objects.")
    parser.add_argument("image", type=Path)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(survey(args.image)), indent=2))


if __name__ == "__main__":
    main()