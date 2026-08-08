"""Automatic, conservative direction correction for scanned document pages.

The module deliberately changes a page orientation or mirrors it only when
Tesseract produces a clear OCR signal. A weak or empty OCR result never changes
the page direction, appearance, crop, or sharpness.
"""

from __future__ import annotations

import os
import re
import sys
from math import sqrt
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageOps

try:
    import pytesseract
    from pytesseract import Output
except ImportError:  # Kept optional so the regular editor remains usable.
    pytesseract = None
    Output = None


class OcrUnavailableError(RuntimeError):
    """Raised when the local Tesseract engine cannot be used."""


@dataclass
class AutoCorrectionResult:
    image: Image.Image
    actions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _application_root() -> Path:
    """Return the application bundle root for both source and PyInstaller runs."""
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))


def _find_tesseract() -> Path | None:
    candidates = [
        _application_root() / "resources" / "tesseract" / "tesseract.exe",
        Path(os.environ.get("PROGRAMFILES", r"C:\\Program Files"))
        / "Tesseract-OCR" / "tesseract.exe",
        Path(os.environ.get("LOCALAPPDATA", ""))
        / "Programs" / "Tesseract-OCR" / "tesseract.exe",
    ]

    configured = os.environ.get("TESSERACT_CMD")
    if configured:
        candidates.insert(0, Path(configured))

    for candidate in candidates:
        try:
            if candidate.is_file():
                return candidate
        except OSError:
            # A half-finished local Tesseract installation can leave an
            # inaccessible executable behind.  Ignore it and allow the visual
            # fallback to keep working.
            continue
    return None


def ensure_ocr_available() -> list[str]:
    """Configure Tesseract and return the installed OCR languages."""
    if pytesseract is None:
        raise OcrUnavailableError(
            "Thiếu thư viện pytesseract. Hãy cài lại gói yêu cầu của ứng dụng."
        )

    executable = _find_tesseract()
    if executable is None:
        raise OcrUnavailableError(
            "Không tìm thấy bộ máy OCR Tesseract. Bản build cần kèm "
            "resources/tesseract hoặc máy cần cài Tesseract-OCR."
        )

    pytesseract.pytesseract.tesseract_cmd = str(executable)
    try:
        languages = pytesseract.get_languages(config="")
    except Exception as error:
        raise OcrUnavailableError(f"Không khởi động được OCR: {error}") from error

    if not languages:
        raise OcrUnavailableError("OCR không có dữ liệu ngôn ngữ để nhận dạng.")
    return languages


def _ocr_language(languages: list[str]) -> str:
    wanted = [language for language in ("vie", "eng") if language in languages]
    return "+".join(wanted) if wanted else languages[0]


def _ocr_preview(image: Image.Image, max_side: int = 2200) -> Image.Image:
    """Keep OCR fast while leaving the full-resolution image untouched."""
    preview = image.convert("RGB")
    largest_side = max(preview.size)
    if largest_side <= max_side:
        return preview

    scale = max_side / largest_side
    return preview.resize(
        (round(preview.width * scale), round(preview.height * scale)),
        Image.Resampling.LANCZOS,
    )


def _suggested_rotation(image: Image.Image, language: str) -> int | None:
    """Ask Tesseract's dedicated orientation engine for the correction angle.

    OSD is trained separately from Vietnamese/English text recognition.  Using
    ``vie+eng`` here makes OSD fail on sparse scans such as land certificates,
    while explicitly selecting ``osd`` can still detect the 90-degree layout.
    """
    try:
        result = pytesseract.image_to_osd(
            _ocr_preview(image),
            lang="osd",
            config="--psm 0",
        )
    except Exception:
        return None

    match = re.search(r"Rotate:\s*(0|90|180|270)", result)
    return int(match.group(1)) if match else None


def _mean_confidence(image: Image.Image, language: str) -> float:
    """Return a stable OCR score for dense and sparse document scans."""
    best_score = -1.0
    preview = _ocr_preview(image)
    for psm in (6, 11):
        try:
            data = pytesseract.image_to_data(
                preview,
                lang=language,
                config=f"--psm {psm}",
                output_type=Output.DICT,
            )
        except Exception:
            continue

        scores = []
        for confidence, text in zip(data["conf"], data["text"]):
            try:
                score = float(confidence)
            except (TypeError, ValueError):
                continue
            if text.strip() and score >= 0:
                scores.append(score)

        if scores:
            # A single coincidental glyph must not determine page direction.
            coverage = min(1.0, len(scores) / 6)
            best_score = max(best_score, (sum(scores) / len(scores)) * coverage)
    return best_score


def _best_rotation_by_ocr(image: Image.Image, language: str) -> int | None:
    """Fallback for scans where Tesseract's OSD cannot find enough text.

    OCR confidence is compared in all four cardinal directions.  The original
    direction wins unless another direction is both usable and clearly better,
    which prevents a low-quality scan from being rotated at random.
    """
    scores = {}
    for angle in (0, 90, 180, 270):
        candidate = image if angle == 0 else image.rotate(-angle, expand=True)
        scores[angle] = _mean_confidence(candidate, language)

    angle, best_score = max(scores.items(), key=lambda item: item[1])
    original_score = scores[0]
    if (
        angle != 0
        and best_score >= 18
        and (original_score < 0 or best_score >= original_score + 7)
    ):
        return angle
    return None


def _scan_layout_rotation(image: Image.Image) -> int | None:
    """Detect a sideways Vietnamese certificate when OCR has no result.

    A number of land-certificate scans contain very little OCR-friendly text,
    but their text strokes still form a clear vertical pattern when sideways.
    For this narrow case we use the red/yellow national emblem as a second,
    conservative signal: the upright candidate should place it in the upper
    half of the document.  Plain black-and-white documents are left untouched.
    """
    preview = image.convert("RGB")
    # Direction recognition needs document structure, not full scan detail.
    # Keeping this small makes selected-page correction feel immediate while
    # the final rotated page remains at its original resolution.
    preview.thumbnail((450, 450))
    width, height = preview.size
    if width < 160 or height < 160:
        return None

    left, top = round(width * 0.04), round(height * 0.04)
    right, bottom = round(width * 0.96), round(height * 0.96)
    gray = preview.convert("L")
    pixels = gray.load()
    row_ink = []
    column_ink = [0] * (right - left)

    for y in range(top, bottom):
        ink = 0
        for index, x in enumerate(range(left, right)):
            dark = 1 if pixels[x, y] < 60 else 0
            ink += dark
            column_ink[index] += dark
        row_ink.append(ink)

    def deviation(values: list[int]) -> float:
        average = sum(values) / len(values)
        return sqrt(sum((value - average) ** 2 for value in values) / len(values))

    # Sideways text creates stronger variation between columns than rows.
    row_deviation = deviation(row_ink) / max(1, right - left)
    column_deviation = deviation(column_ink) / max(1, bottom - top)
    if column_deviation < row_deviation * 1.25:
        return None

    def emblem_top_score(candidate: Image.Image) -> tuple[float, int]:
        candidate = candidate.convert("RGB")
        candidate.thumbnail((450, 450))
        candidate_width, candidate_height = candidate.size
        candidate_pixels = candidate.load()
        upper = lower = 0
        for y in range(round(candidate_height * 0.04), round(candidate_height * 0.96)):
            for x in range(round(candidate_width * 0.04), round(candidate_width * 0.96)):
                red, green, blue = candidate_pixels[x, y]
                is_emblem_color = (
                    (red > 130 and red > green * 1.22 and red > blue * 1.35)
                    or (red > 150 and green > 90 and blue < 100)
                )
                if not is_emblem_color:
                    continue
                if y < candidate_height / 2:
                    upper += 1
                else:
                    lower += 1
        total = upper + lower
        return ((upper - lower) / max(1, total), total)

    candidates = {
        90: image.rotate(-90, expand=True),
        270: image.rotate(-270, expand=True),
    }
    scores = {angle: emblem_top_score(candidate) for angle, candidate in candidates.items()}
    angle, (top_score, color_count) = max(scores.items(), key=lambda item: item[1][0])
    minimum_color_pixels = max(80, round(width * height * 0.002))
    if color_count < minimum_color_pixels or top_score < 0.25:
        return None
    return angle


def auto_correct_document(
    image: Image.Image,
    languages: list[str] | None = None,
) -> AutoCorrectionResult:
    """Correct rotation or mirrored text without changing visual scan quality."""
    if languages is None:
        languages = ensure_ocr_available()
    language = _ocr_language(languages) if languages else None
    result = AutoCorrectionResult(image=image.convert("RGBA"))

    # This inexpensive visual signal handles common sideways certificates
    # immediately.  It avoids several slow OCR passes for a clearly rotated
    # document, and also protects against an OCR engine incorrectly returning
    # ``Rotate: 0`` on a sparse scan.
    rotation = _scan_layout_rotation(result.image)
    if rotation is None and language:
        rotation = _suggested_rotation(result.image, language)
    if rotation is None and language:
        rotation = _best_rotation_by_ocr(result.image, language)
    if rotation:
        # Tesseract's OSD "Rotate" is the clockwise correction angle; PIL is CCW.
        result.image = result.image.rotate(-rotation, expand=True)
        result.actions.append(f"xoay {rotation}°")
    else:
        result.warnings.append("không đủ chữ để xác định chiều xoay")

    if language:
        normal_score = _mean_confidence(result.image, language)
        mirrored = ImageOps.mirror(result.image)
        mirrored_score = _mean_confidence(mirrored, language)
        if mirrored_score >= 42 and mirrored_score >= normal_score + 15:
            result.image = mirrored
            result.actions.append("lật gương")
        elif normal_score < 0 and mirrored_score < 0:
            result.warnings.append("không đủ chữ để kiểm tra lật gương")
    else:
        result.warnings.append("OCR chưa sẵn sàng để kiểm tra lật gương")

    return result
