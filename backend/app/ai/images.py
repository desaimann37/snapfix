"""Image intake: validate, read EXIF GPS, fix orientation, strip EXIF, resize to 1568 px, optional face blur."""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass

from PIL import Image, ImageOps, UnidentifiedImageError

from app.config import get_settings

log = logging.getLogger(__name__)

MAX_EDGE = 1568
JPEG_QUALITY = 85
ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "GIF", "BMP", "MPO"}


class ImageRejected(ValueError):
    pass


@dataclass
class ProcessedImage:
    jpeg: bytes
    width: int
    height: int
    gps: tuple[float, float] | None
    faces_blurred: int = 0
    media_type: str = "image/jpeg"


def _dms_to_deg(dms, ref) -> float | None:
    try:
        deg = float(dms[0]) + float(dms[1]) / 60 + float(dms[2]) / 3600
    except (TypeError, ValueError, IndexError, ZeroDivisionError):
        return None
    return -deg if ref in ("S", "W", b"S", b"W") else deg


def read_gps(img: Image.Image) -> tuple[float, float] | None:
    try:
        gps = img.getexif().get_ifd(0x8825)  # GPSInfo
    except Exception:
        return None
    if not gps or 2 not in gps or 4 not in gps:
        return None
    lat = _dms_to_deg(gps.get(2), gps.get(1))
    lng = _dms_to_deg(gps.get(4), gps.get(3))
    if lat is None or lng is None or not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return None
    return round(lat, 6), round(lng, 6)


def blur_faces(img: Image.Image) -> tuple[Image.Image, int]:
    """Blur faces with an OpenCV Haar cascade (optional dependency; skipped if OpenCV isn't installed)."""
    try:
        import cv2  # type: ignore
        import numpy as np
    except ImportError:
        log.warning("BLUR_FACES=true but opencv-python-headless is not installed; skipping face blur")
        return img, 0
    arr = np.array(img)
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(40, 40))
    for (x, y, w, h) in faces:
        roi = arr[y:y + h, x:x + w]
        arr[y:y + h, x:x + w] = cv2.GaussianBlur(roi, (0, 0), sigmaX=max(w, h) / 6)
    return Image.fromarray(arr), len(faces)


def preprocess(raw: bytes) -> ProcessedImage:
    settings = get_settings()
    if len(raw) > settings.max_upload_mb * 1024 * 1024:
        raise ImageRejected(f"Image is larger than {settings.max_upload_mb} MB")
    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise ImageRejected("That file is not a supported image (use JPEG, PNG or WebP)") from exc
    if img.format not in ALLOWED_FORMATS:
        raise ImageRejected(f"Unsupported image type {img.format}")

    gps = read_gps(img)  # read before EXIF is discarded
    img = ImageOps.exif_transpose(img)  # bake in camera orientation, then drop EXIF entirely
    img = img.convert("RGB")
    img.thumbnail((MAX_EDGE, MAX_EDGE), Image.LANCZOS)
    faces = 0
    if settings.blur_faces:
        img, faces = blur_faces(img)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=True)  # no exif= -> metadata stripped
    return ProcessedImage(jpeg=buf.getvalue(), width=img.width, height=img.height, gps=gps, faces_blurred=faces)
