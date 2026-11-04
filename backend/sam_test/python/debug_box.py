# backend/sam_test/python/debug_box.py
import asyncio
import sys
from pathlib import Path

from PIL import Image, ImageDraw
from sam_api import segment_image


async def main():
    path = Path(sys.argv[1])
    concept = sys.argv[2] if len(sys.argv) > 2 else "paper"

    img = Image.open(path).convert("RGB")
    print(f"Image size (PIL, width x height): {img.size}")

    result = await segment_image(path, concept)
    boxes = [r for r in result.records if r.kind == "box"]
    if not boxes:
        print(f"No '{concept}' boxes detected.")
        return

    draw = ImageDraw.Draw(img)
    for b in boxes:
        print(f"raw box -> left={b.left}, top={b.top}, right={b.right}, bottom={b.bottom}")
        draw.rectangle([b.left, b.top, b.right, b.bottom], outline="red", width=6)

    out_path = path.with_name(f"{path.stem}_{concept}_boxed.jpg")
    img.save(out_path)
    print(f"Saved annotated image to: {out_path}")


if __name__ == "__main__":
    asyncio.run(main())