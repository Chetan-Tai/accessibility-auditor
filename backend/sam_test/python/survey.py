# backend/sam_test/python/survey.py
import argparse
import asyncio
import json
from pathlib import Path

from PIL import Image

from sam_api import segment_image

SURVEY_CONCEPTS = ["door", "stairs", "ramp", "floor obstruction", "handrail", "threshold"]


def _box_to_relative(box, img_w: int, img_h: int) -> dict:
    """Express a box's position/extent as % of the image frame, so Spark
    gets real spatial layout without implying false pixel-level precision."""
    return {
        "left_pct": round(100 * box.left / img_w, 1),
        "top_pct": round(100 * box.top / img_h, 1),
        "right_pct": round(100 * box.right / img_w, 1),
        "bottom_pct": round(100 * box.bottom / img_h, 1),
    }


async def survey(image_path: Path) -> dict:
    with Image.open(image_path) as img:
        img_w, img_h = img.size

    results = await asyncio.gather(*(segment_image(image_path, c) for c in SURVEY_CONCEPTS))
    output = {}
    for concept, result in zip(SURVEY_CONCEPTS, results):
        boxes = [r for r in result.records if r.kind == "box"]
        output[concept] = {
            "detected": len(boxes) > 0,
            "count": len(boxes),
            "boxes": [_box_to_relative(b, img_w, img_h) for b in boxes],
        }
    return output


async def survey_multi(image_paths: list[Path]) -> dict:
    """Union detection across multiple photos. Boxes are kept PER PHOTO
    (not merged/averaged) since the same object has different coordinates
    in each photo — merging them would be meaningless."""
    per_photo = await asyncio.gather(*(survey(p) for p in image_paths))
    merged = {c: {"detected": False, "count": 0, "by_photo": []} for c in SURVEY_CONCEPTS}
    for path, result in zip(image_paths, per_photo):
        for concept, info in result.items():
            if info["detected"]:
                merged[concept]["detected"] = True
                merged[concept]["count"] = max(merged[concept]["count"], info["count"])
                merged[concept]["by_photo"].append({
                    "photo": str(path),
                    "boxes": info["boxes"],
                })
    return merged


def main():
    parser = argparse.ArgumentParser(description="Survey one or more photos for accessibility-relevant objects.")
    parser.add_argument("images", type=Path, nargs="+")
    args = parser.parse_args()
    if len(args.images) == 1:
        result = asyncio.run(survey(args.images[0]))
    else:
        result = asyncio.run(survey_multi(args.images))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()