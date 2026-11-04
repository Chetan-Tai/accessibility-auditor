# backend/sam_test/python/app.py
from __future__ import annotations

import base64
import io
import json
import shutil
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps

from survey import survey_multi
from measure import scan_door_from_photos
from reasoning import reason_about_scene

app = FastAPI()

STATIC_DIR = Path(__file__).resolve().parents[3] / "frontend"


def _normalize_orientation(raw: bytes) -> bytes:
    """Phone photos often store pixels in one orientation plus an EXIF tag
    telling viewers to rotate them for display. Browsers auto-rotate for
    <img>, but PIL (and SAM) read raw pixel dimensions — without baking the
    rotation in here, bounding-box percentages get computed in one
    orientation and rendered in another, producing misaligned overlays."""
    img = Image.open(io.BytesIO(raw))
    img = ImageOps.exif_transpose(img)
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=95)
    return buf.getvalue()


def _event(obj: dict) -> bytes:
    return (json.dumps(obj) + "\n").encode("utf-8")


@app.post("/api/audit")
async def audit_endpoint(photos: list[UploadFile] = File(...)):
    tmp_dir = Path(tempfile.mkdtemp(prefix="accessibility-audit-"))
    saved_paths: list[Path] = []
    images_b64: dict[str, str] = {}

    for i, upload in enumerate(photos):
        raw = await upload.read()
        data = _normalize_orientation(raw)

        dest = tmp_dir / f"{i}.jpg"
        dest.write_bytes(data)
        saved_paths.append(dest)
        images_b64[str(dest)] = f"data:image/jpeg;base64,{base64.b64encode(data).decode('ascii')}"

    async def run_pipeline():
        try:
            yield _event({"stage": "segmenting", "status": "start"})
            survey_result = await survey_multi(saved_paths)
            yield _event({"stage": "segmenting", "status": "done"})

            door_result = None
            if survey_result.get("door", {}).get("detected"):
                yield _event({"stage": "calibrating", "status": "start"})
                door_result = await scan_door_from_photos(saved_paths)
                yield _event({"stage": "calibrating", "status": "done"})
            else:
                yield _event({"stage": "calibrating", "status": "skipped"})

            yield _event({"stage": "reasoning", "status": "start"})
            assessment = await reason_about_scene(saved_paths, survey_result, door_result)
            yield _event({"stage": "reasoning", "status": "done"})

            result = {
                "photos": [str(p) for p in saved_paths],
                "survey": survey_result,
                "door_measurement": door_result,
                "assessment": assessment.model_dump(),
            }
            yield _event({"stage": "complete", "result": result, "images": images_b64})
        except Exception as exc:
            yield _event({"stage": "error", "message": str(exc)})
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    return StreamingResponse(run_pipeline(), media_type="application/x-ndjson")


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")