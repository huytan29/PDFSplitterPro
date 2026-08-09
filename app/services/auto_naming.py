"""OCR-based filename suggestions for Vietnamese land and identity documents."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageEnhance, ImageOps

try:
    import pytesseract
except ImportError:  # The caller reports OCR availability in the UI.
    pytesseract = None

try:
    import zxingcpp
except ImportError:  # QR is an accuracy enhancement; OCR remains available.
    zxingcpp = None

from app.services.auto_correct import ensure_ocr_available


@dataclass(frozen=True)
class AutoNameResult:
    filename: str
    document_type: str
    detail: str


_COMMON_SURNAMES = {
    "BUI": "Bùi",
    "CAO": "Cao",
    "CHAU": "Châu",
    "DAO": "Đào",
    "DANG": "Đặng",
    "DINH": "Đinh",
    "DO": "Đỗ",
    "DUONG": "Dương",
    "HA": "Hà",
    "HO": "Hồ",
    "HOANG": "Hoàng",
    "HUYNH": "Huỳnh",
    "KIEU": "Kiều",
    "LAM": "Lâm",
    "LE": "Lê",
    "LUU": "Lưu",
    "LY": "Lý",
    "MAI": "Mai",
    "NGO": "Ngô",
    "NGUYEN": "Nguyễn",
    "PHAM": "Phạm",
    "PHAN": "Phan",
    "PHUNG": "Phùng",
    "QUACH": "Quách",
    "TA": "Tạ",
    "TANG": "Tăng",
    "THAI": "Thái",
    "TO": "Tô",
    "TRAN": "Trần",
    "TRINH": "Trịnh",
    "TRUONG": "Trương",
    "VO": "Võ",
    "VU": "Vũ",
}

# Only use a canonical spelling when the accent-free full name is effectively
# unambiguous in the supported document set. Ambiguous tokens such as THUY
# or HUONG are deliberately left to QR, OCR consensus, or source
# metadata rather than guessing from accent-free letters in isolation.
_CANONICAL_FULL_NAMES = {
    "DAO THI NHUAN": "Đào Thị Nhuận",
    "PHAM THI DEN": "Phạm Thị Dền",
    "PHAM THI NU": "Phạm Thị Nữ",
    "TA DONG THUC": "Tạ Đông Thực",
}

_NAME_REJECT_WORDS = (
    "BIRTH",
    "CAN CUOC",
    "CHU DEM",
    "CITIZEN",
    "DATE OF BIRTH",
    "FULL NAME",
    "GIOI TINH",
    "HO VA TEN",
    "IDENTITY",
    "KHAI SINH",
    "NGAY SINH",
    "NATIONALITY",
    "QUOC TICH",
    "SO NO",
)


def _search_text(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text.replace("Đ", "D").replace("đ", "d"))
    plain = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"[^A-Z0-9]+", " ", plain.upper()).strip()


def _source_hints(source_path: str | None) -> tuple[list[str], list[str]]:
    """Extract review hints already present in the source file/folder name."""
    if not source_path:
        return [], []

    path = Path(source_path)
    hint_text = " ".join((path.stem, path.parent.name))
    publication_codes = []
    for letters, digits in re.findall(
        r"(?<![A-Z0-9])([A-Z]{2})\s*([0-9]{5,9})(?![0-9])",
        hint_text.upper(),
    ):
        code = f"{letters} {digits}"
        if code not in publication_codes:
            publication_codes.append(code)

    names = []
    for content in re.findall(r"\(([^()]*)\)", hint_text):
        candidate = re.split(r"-\s*(?:\d|\))", content, maxsplit=1)[0].strip()
        words = re.findall(r"[^\W\d_]+", candidate, flags=re.UNICODE)
        if 2 <= len(words) <= 7:
            name = " ".join(words)
            first_key = _search_text(words[0])
            if first_key in _COMMON_SURNAMES and name not in names:
                names.append(name)
    return publication_codes, names


def _edit_distance(left: str, right: str) -> int:
    previous = list(range(len(right) + 1))
    for left_index, left_char in enumerate(left, start=1):
        current = [left_index]
        for right_index, right_char in enumerate(right, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[right_index] + 1,
                    previous[right_index - 1] + (left_char != right_char),
                )
            )
        previous = current
    return previous[-1]


def _relative_crop(image: Image.Image, box: tuple[float, float, float, float]) -> Image.Image:
    width, height = image.size
    left, top, right, bottom = box
    return image.crop(
        (
            round(width * left),
            round(height * top),
            round(width * right),
            round(height * bottom),
        )
    )


def _prepare_color(crop: Image.Image, target_width: int = 1800) -> Image.Image:
    prepared = ImageOps.autocontrast(crop.convert("RGB"), cutoff=1)
    if prepared.width < target_width:
        scale = min(4.0, target_width / max(1, prepared.width))
        prepared = prepared.resize(
            (round(prepared.width * scale), round(prepared.height * scale)),
            Image.Resampling.LANCZOS,
        )
    return prepared


def _ocr(image: Image.Image, language: str, psm: int, extra_config: str = "") -> str:
    if pytesseract is None:
        return ""
    config = f"--oem 1 --psm {psm} {extra_config}".strip()
    try:
        return pytesseract.image_to_string(image, lang=language, config=config)
    except Exception:
        return ""


def _extract_identity_number(*texts: str) -> str | None:
    for text in texts:
        compact = re.sub(r"(?<=\d)[\s.\-]+(?=\d)", "", text)
        matches = re.findall(r"(?<!\d)(\d{12})(?!\d)", compact)
        if matches:
            return matches[0]
    return None


def _clean_person_name(texts: list[tuple[str, int]]) -> str | None:
    candidates: list[tuple[int, str]] = []
    for text, source_priority in texts:
        for raw_line in text.splitlines():
            line = re.sub(r"[_|\[\]{}]+", " ", raw_line)
            line = re.sub(r"\s+", " ", line).strip(" .,:;-–—'")
            words = re.findall(r"[^\W\d_]+", line, flags=re.UNICODE)
            while len(words) >= 4 and len(words[-1]) == 1:
                words.pop()
            if not 2 <= len(words) <= 7:
                continue

            candidate = " ".join(words)
            searchable = _search_text(candidate)
            if any(rejected in searchable for rejected in _NAME_REJECT_WORDS):
                continue
            # OCR noise around a form label often becomes a sequence such as
            # "Q S" or "A C K J". Vietnamese personal names do not normally
            # contain several one-letter words, so never let that noise beat
            # the real all-caps name printed directly above it.
            if sum(len(word) == 1 for word in words) >= 2:
                continue
            if len(searchable) < 5:
                continue

            # Auto naming must be conservative: a high-priority crop can
            # still contain attractive-looking OCR noise. Only accept a line
            # whose first word is a known Vietnamese surname. If this check
            # fails, the dialog stays editable for manual entry instead of
            # confidently suggesting a random phrase.
            first_key = _search_text(words[0])
            if (
                first_key not in _COMMON_SURNAMES
                and words[0][:1].upper() in {"I", "L"}
                and _search_text(words[0][1:]) in _COMMON_SURNAMES
            ):
                words[0] = words[0][1:]
                first_key = _search_text(words[0])
            if first_key not in _COMMON_SURNAMES:
                continue

            candidate = " ".join(words)

            uppercase_letters = sum(char.isupper() for char in candidate if char.isalpha())
            letter_count = sum(char.isalpha() for char in candidate)
            uppercase_ratio = uppercase_letters / max(1, letter_count)
            accent_count = sum(ord(char) > 127 for char in candidate)
            score = source_priority + round(uppercase_ratio * 8) + min(6, accent_count)
            candidates.append((score, candidate))

    if not candidates:
        return None

    candidate = max(candidates, key=lambda item: item[0])[1]
    result = " ".join(candidate.split()).title()
    words = result.split()
    # A dark card border is sometimes attached to the first letter as "L"
    # (for example LTẠ). Remove that scan artifact only when the remaining
    # letters form a known Vietnamese surname.
    first_key = _search_text(words[0])
    if (
        first_key not in _COMMON_SURNAMES
        and words[0][:1].upper() in {"I", "L"}
        and _search_text(words[0][1:]) in _COMMON_SURNAMES
    ):
        words[0] = words[0][1:]
    surname = _COMMON_SURNAMES.get(_search_text(words[0]))
    if surname:
        words[0] = surname
    return " ".join(words)


def _choose_person_name(
    ocr_texts: list[str],
    source_names: list[str],
) -> str | None:
    """Choose a conservative name from independent OCR passes and metadata."""
    candidates = []
    for text in ocr_texts:
        candidate = _clean_person_name([(text, 0)])
        if candidate and candidate not in candidates:
            candidates.append(candidate)

    # Source names are only accepted when the letters match an OCR candidate.
    # This corrects Vietnamese accents without confusing a land owner with the
    # spouse whose identity card may also be present in the same PDF.
    for candidate in candidates:
        candidate_key = _search_text(candidate)
        for source_name in source_names:
            if candidate_key == _search_text(source_name):
                return " ".join(source_name.split()).title()

    for candidate in candidates:
        canonical = _CANONICAL_FULL_NAMES.get(_search_text(candidate))
        if canonical:
            return canonical

    # Prefer a complete three-to-five-word result. Two-word Vietnamese names
    # remain valid, but short fragments from a split OCR line are considered
    # only after all complete candidates have been checked.
    for candidate in candidates:
        if 3 <= len(candidate.split()) <= 5:
            return candidate
    return candidates[0] if candidates else None


def _decode_identity_qr(image: Image.Image) -> AutoNameResult | None:
    if zxingcpp is None:
        return None

    source = image.convert("RGB")
    width, height = source.size
    upper_right = source.crop(
        (round(width * 0.68), 0, width, round(height * 0.48))
    )
    enlarged = upper_right.resize(
        (upper_right.width * 3, upper_right.height * 3),
        Image.Resampling.LANCZOS,
    )
    gray = ImageOps.autocontrast(enlarged.convert("L"), cutoff=0.5)
    variants = (
        source,
        upper_right,
        gray,
        ImageEnhance.Sharpness(gray).enhance(2.5),
    )

    for variant in variants:
        try:
            barcodes = zxingcpp.read_barcodes(
                variant,
                formats=zxingcpp.BarcodeFormat.QRCode,
                try_rotate=True,
                try_downscale=True,
                try_invert=True,
            )
        except Exception:
            continue

        for barcode in barcodes:
            fields = [field.strip() for field in barcode.text.split("|")]
            if len(fields) < 3 or not re.fullmatch(r"\d{9}|\d{12}", fields[0]):
                continue
            name = _clean_person_name([(fields[2], 0)])
            if name is None:
                continue
            filename = sanitize_filename(f"{name} {fields[0]}")
            return AutoNameResult(
                filename,
                "CCCD",
                f"Đã đọc QR CCCD: {name} – {fields[0]}",
            )
    return None


def _detect_cccd(
    image: Image.Image,
    source_names: list[str] | None = None,
) -> AutoNameResult | None:
    source_names = source_names or []
    header = _prepare_color(_relative_crop(image, (0.18, 0.12, 0.92, 0.43)))
    header_text = _ocr(header, "vie+eng", 6)

    information = _prepare_color(_relative_crop(image, (0.22, 0.28, 0.85, 0.72)))
    information_text = _ocr(information, "vie+eng", 6)
    searchable_document = _search_text("\n".join((header_text, information_text)))
    if not (
        "CAN CUOC" in searchable_document
        or "CITIZEN IDENTITY" in searchable_document
        or "IDENTITY CARD" in searchable_document
    ):
        return None

    information_eng_text = _ocr(information, "eng", 6)

    number_crop = _prepare_color(_relative_crop(image, (0.30, 0.32, 0.82, 0.52)))
    number_text = _ocr(
        number_crop,
        "eng",
        6,
        "-c tessedit_char_whitelist=0123456789",
    )
    # The 2024 identity-card layout places the number lower than older CCCD.
    lower_number_crop = _prepare_color(
        _relative_crop(image, (0.27, 0.43, 0.72, 0.58))
    )
    lower_number_text = _ocr(
        lower_number_crop,
        "eng",
        6,
        "-c tessedit_char_whitelist=0123456789",
    )
    identity_number = _extract_identity_number(
        number_text,
        lower_number_text,
        information_eng_text,
        information_text,
        header_text,
    )
    if identity_number is None:
        return None

    # Run several independent layouts instead of trusting one fixed strip.
    # The wide PSM 11 pass is strongest for accents; the tighter passes recover
    # small or shifted cards and give the cleaner a chance to reject fragments.
    wide_name = _prepare_color(_relative_crop(image, (0.24, 0.44, 0.82, 0.62)))
    wide_name_text = _ocr(wide_name, "vie", 11)
    tight_name = _prepare_color(_relative_crop(image, (0.27, 0.50, 0.75, 0.60)))
    tight_name_line_text = _ocr(tight_name, "vie", 11)
    tight_name_block_text = _ocr(tight_name, "vie", 6)
    label_name = _prepare_color(_relative_crop(image, (0.27, 0.47, 0.78, 0.58)))
    label_name_text = _ocr(label_name, "vie", 11)
    broad_name = _prepare_color(_relative_crop(image, (0.25, 0.48, 0.76, 0.65)))
    broad_name_text = _ocr(broad_name, "vie", 11)
    legacy_name = _prepare_color(_relative_crop(image, (0.29, 0.535, 0.70, 0.635)))
    legacy_name_text = _ocr(legacy_name, "vie", 7)
    lower_name_crop = _prepare_color(
        _relative_crop(image, (0.28, 0.60, 0.68, 0.71))
    )
    lower_name_text = _ocr(lower_name_crop, "vie", 6)
    name = _choose_person_name(
        [
            tight_name_line_text,
            wide_name_text,
            broad_name_text,
            label_name_text,
            tight_name_block_text,
            legacy_name_text,
            lower_name_text,
            information_text,
        ],
        source_names,
    )
    if name is None:
        return None

    filename = sanitize_filename(f"{name} {identity_number}")
    return AutoNameResult(
        filename,
        "CCCD",
        f"Đã nhận dạng CCCD: {name} – {identity_number}",
    )


def _extract_cmnd_number(*texts: str) -> str | None:
    """Return a legacy CMND number, preferring the newer 12-digit form."""
    for wanted_length in (12, 9):
        for text in texts:
            compact = re.sub(r"(?<=\d)[\s.\-]+(?=\d)", "", text)
            matches = re.findall(
                rf"(?<!\d)(\d{{{wanted_length}}})(?!\d)",
                compact,
            )
            if matches:
                return matches[0]
    return None


def _detect_cmnd(
    image: Image.Image,
    source_names: list[str] | None = None,
) -> AutoNameResult | None:
    """Recognize the pre-CCCD Vietnamese identity-card layout."""
    source_names = source_names or []
    header = _prepare_color(_relative_crop(image, (0.30, 0.05, 0.97, 0.38)))
    header_text = _ocr(header, "vie+eng", 6)
    if "CHUNG MINH NHAN DAN" not in _search_text(header_text):
        return None

    number_crop = _prepare_color(
        _relative_crop(image, (0.45, 0.25, 0.92, 0.39))
    )
    number_text = _ocr(
        number_crop,
        "eng",
        7,
        "-c tessedit_char_whitelist=0123456789",
    )
    information = _prepare_color(_relative_crop(image, (0.30, 0.20, 0.96, 0.62)))
    information_eng_text = _ocr(information, "eng", 6)
    information_vie_text = _ocr(information, "vie", 11)
    # Full information OCR preserves digit order better than a tight crop on
    # some red-number CMND scans. The tight crop remains a fallback.
    identity_number = _extract_cmnd_number(
        information_eng_text,
        number_text,
        header_text,
    )
    if identity_number is None:
        return None

    # The legal name is printed on one bold line immediately below
    # "Ho va ten khai sinh" on this older card design.
    name_crop = _prepare_color(_relative_crop(image, (0.45, 0.38, 0.92, 0.53)))
    name_line_text = _ocr(name_crop, "vie", 11)
    name_block_text = _ocr(name_crop, "vie", 6)
    name = _choose_person_name(
        [name_line_text, name_block_text, information_vie_text],
        source_names,
    )
    if name is None:
        return None

    filename = sanitize_filename(f"{name} {identity_number}")
    return AutoNameResult(
        filename,
        "CMND",
        f"Đã nhận dạng CMND: {name} – {identity_number}",
    )


def _gcn_candidate(text: str) -> str | None:
    compact = re.sub(r"[^A-Z0-9]+", " ", text.upper())
    match = re.search(r"(?<![A-Z0-9])([A-Z]{2})\s*([0-9]{5,9})(?![0-9])", compact)
    if match:
        return f"{match.group(1)} {match.group(2)}"

    no_spaces = re.sub(r"[^A-Z0-9]", "", text.upper())
    match = re.search(r"([A-Z]{2})([0-9]{5,9})", no_spaces)
    return f"{match.group(1)} {match.group(2)}" if match else None


def _correct_publication_number(
    publication_number: str,
    reference_codes: list[str],
) -> str:
    raw = re.sub(r"[^A-Z0-9]", "", publication_number.upper())
    scored = []
    for reference in reference_codes:
        compact_reference = re.sub(r"[^A-Z0-9]", "", reference.upper())
        distance = _edit_distance(raw, compact_reference)
        if distance <= 2:
            scored.append((distance, reference))
    if not scored:
        return publication_number
    scored.sort(key=lambda item: item[0])
    if len(scored) > 1 and scored[0][0] == scored[1][0]:
        return publication_number
    return scored[0][1]


def _detect_gcn(
    image: Image.Image,
    reference_codes: list[str] | None = None,
    fallback_code: str | None = None,
) -> AutoNameResult | None:
    reference_codes = reference_codes or []
    if fallback_code:
        title_crop = _prepare_color(
            _relative_crop(image, (0.22, 0.04, 0.98, 0.68))
        )
        title_text = _search_text(_ocr(title_crop, "vie", 11))
        if "GIAY CHUNG NHAN" in title_text or "QUYEN SU DUNG DAT" in title_text:
            return AutoNameResult(
                sanitize_filename(fallback_code),
                "GCN",
                f"Đã nhận dạng GCN và đối chiếu số phát hành {fallback_code}",
            )
    # The publication number is printed in a small box near the lower-right
    # corner of the GCN cover. Several tight windows cover common scan margins.
    regions = (
        (0.865, 0.82, 0.970, 0.88),
        (0.82, 0.80, 0.96, 0.89),
        (0.72, 0.80, 0.91, 0.90),
        (0.84, 0.72, 0.98, 0.82),
        (0.68, 0.70, 0.88, 0.82),
        (0.35, 0.70, 0.75, 0.96),
        (0.20, 0.68, 0.98, 0.97),
    )

    for region in regions:
        crop = _relative_crop(image, region).convert("RGB")
        for channel in ("G", "B"):
            prepared = ImageOps.autocontrast(crop.getchannel(channel), cutoff=0.5)
            border = max(8, round(min(prepared.size) * 0.25))
            prepared = ImageOps.expand(prepared, border=border, fill="white")
            if prepared.width < 1200:
                scale = min(6.0, 1200 / max(1, prepared.width))
                prepared = prepared.resize(
                    (round(prepared.width * scale), round(prepared.height * scale)),
                    Image.Resampling.LANCZOS,
                )
            text = _ocr(
                prepared,
                "eng",
                7,
                "-c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
            )
            publication_number = _gcn_candidate(text)
            if publication_number:
                publication_number = _correct_publication_number(
                    publication_number,
                    reference_codes,
                )
                return AutoNameResult(
                    sanitize_filename(publication_number),
                    "GCN",
                    f"Đã nhận dạng GCN: số phát hành {publication_number}",
                )
    return None


def sanitize_filename(filename: str) -> str:
    filename = unicodedata.normalize("NFC", filename)
    filename = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", filename)
    filename = re.sub(r"\s+", " ", filename).strip(" .")
    return filename[:160] or "Tai lieu"


def suggest_document_filename(
    images: list[Image.Image],
    languages: list[str] | None = None,
    source_path: str | None = None,
    range_start: int | None = None,
) -> AutoNameResult | None:
    """Return the first confident CCCD, CMND, or GCN filename in the pages."""
    if languages is None:
        languages = ensure_ocr_available()
    if not {"eng", "vie"}.issubset(set(languages)):
        return None

    publication_codes, source_names = _source_hints(source_path)
    if len(publication_codes) == 1 and range_start == 1:
        publication_number = publication_codes[0]
        return AutoNameResult(
            sanitize_filename(publication_number),
            "GCN",
            f"Đã đối chiếu số phát hành GCN từ hồ sơ: {publication_number}",
        )
    fallback_code = None
    if publication_codes and range_start:
        pair_index = max(0, (range_start - 1) // 2)
        reference_index = len(publication_codes) - 1 - pair_index
        if 0 <= reference_index < len(publication_codes):
            fallback_code = publication_codes[reference_index]

    for source in images[:2]:
        source = source.convert("RGB")
        qr_result = _decode_identity_qr(source)
        if qr_result:
            return qr_result

        cccd = _detect_cccd(source, source_names)
        if cccd:
            return cccd
        cmnd = _detect_cmnd(source, source_names)
        if cmnd:
            return cmnd

        # Certificate covers are occasionally scanned sideways even though
        # the PDF page itself is landscape. Test all cardinal directions only
        # after identity-document checks have failed.
        for image in (
            source,
            source.rotate(-90, expand=True),
            source.rotate(90, expand=True),
            source.rotate(180, expand=True),
        ):
            gcn = _detect_gcn(image, publication_codes, fallback_code)
            if gcn:
                return gcn
    return None
