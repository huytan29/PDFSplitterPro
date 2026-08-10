"""OCR-based filename suggestions for Vietnamese land and identity documents."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
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
    match = re.search(r"(?<![A-Z0-9])([A-Z]{2})\s*([0-9]{4,9})(?![0-9])", compact)
    if match:
        return f"{match.group(1)} {match.group(2)}"

    no_spaces = re.sub(r"[^A-Z0-9]", "", text.upper())
    match = re.search(r"([A-Z]{2})([0-9]{4,9})", no_spaces)
    return f"{match.group(1)} {match.group(2)}" if match else None


def _publication_parts(publication_number: str) -> tuple[str, str] | None:
    match = re.fullmatch(r"([A-Z]{2})\s*([0-9]{4,9})", publication_number.upper())
    return (match.group(1), match.group(2)) if match else None


def _select_publication_number(
    candidates: list[str],
    reference_codes: list[str],
    preferred_reference: str | None = None,
) -> str | None:
    """Choose a code from OCR evidence without treating a folder name as truth."""
    parsed_candidates = [
        (candidate, parts[0], parts[1])
        for candidate in candidates
        if (parts := _publication_parts(candidate)) is not None
    ]
    if not parsed_candidates:
        return None

    counts = Counter(candidate for candidate, _, _ in parsed_candidates)

    # A source filename is only a review hint.  Accept it when OCR independently
    # sees the complete code, or when the scan visibly cuts off exactly one final
    # digit and only one reference can complete that prefix.  Never substitute a
    # merely "similar" code: real folders can contain stale or incorrect codes.
    supported_references: list[tuple[int, str]] = []
    for reference in reference_codes:
        parts = _publication_parts(reference)
        if parts is None:
            continue
        reference_letters, reference_digits = parts
        exact_votes = counts.get(f"{reference_letters} {reference_digits}", 0)
        prefix_votes = sum(
            counts[candidate]
            for candidate, letters, digits in set(parsed_candidates)
            if letters == reference_letters
            and 1 <= len(reference_digits) - len(digits) <= (
                2 if reference == preferred_reference else 1
            )
            and reference_digits.startswith(digits)
        )
        letter_confusion_votes = sum(
            counts[candidate]
            for candidate, letters, digits in set(parsed_candidates)
            if digits == reference_digits
            and _edit_distance(letters, reference_letters) == 1
        )
        if exact_votes or prefix_votes or letter_confusion_votes:
            supported_references.append(
                (
                    exact_votes + prefix_votes + letter_confusion_votes,
                    f"{reference_letters} {reference_digits}",
                )
            )
    if supported_references:
        supported_references.sort(reverse=True)
        best_score = supported_references[0][0]
        best_references = [
            reference
            for score, reference in supported_references
            if score == best_score
        ]
        if preferred_reference in best_references:
            return preferred_reference
        if len(best_references) == 1:
            return best_references[0]

    # Reconcile split evidence such as BO 832371 (complete digits) and
    # BQ 83237 (correct letters but a clipped last digit).  The combined result
    # is accepted only when one two-letter prefix has strictly stronger support.
    composite_counts: Counter[str] = Counter()
    for _, full_letters, full_digits in set(parsed_candidates):
        if len(full_digits) not in {6, 8}:
            continue
        letter_votes: Counter[str] = Counter()
        for candidate, letters, digits in set(parsed_candidates):
            if _edit_distance(letters, full_letters) > 1:
                continue
            if digits == full_digits or (
                len(full_digits) == len(digits) + 1 and full_digits.startswith(digits)
            ):
                letter_votes[letters] += counts[candidate]
        if not letter_votes:
            continue
        ranked_letters = letter_votes.most_common()
        if len(ranked_letters) == 1 or ranked_letters[0][1] > ranked_letters[1][1]:
            letters, votes = ranked_letters[0]
            composite_counts[f"{letters} {full_digits}"] += votes

    if composite_counts:
        ranked_composites = composite_counts.most_common()
        if (
            len(ranked_composites) == 1
            or ranked_composites[0][1] > ranked_composites[1][1]
        ):
            return ranked_composites[0][0]

    # Six digits are the normal publication series; some older series use
    # eight. Five, seven, or nine digits are usually a clipped/duplicated glyph,
    # so leave an ambiguous suggestion editable instead of naming it wrongly.
    plausible = Counter(
        candidate
        for candidate, _, digits in parsed_candidates
        if len(digits) in {6, 8}
    )
    if not plausible:
        return None
    ranked = plausible.most_common()
    if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
        top_votes = ranked[0][1]
        tied = [candidate for candidate, votes in ranked if votes == top_votes]
        reference_letters = {
            parts[0]
            for reference in reference_codes
            if (parts := _publication_parts(reference)) is not None
        }
        family_matches = [
            candidate
            for candidate in tied
            if _publication_parts(candidate)[0] in reference_letters
        ]
        if len(family_matches) == 1:
            return family_matches[0]
        return None
    return ranked[0][0]


def _is_gcn_cover(image: Image.Image) -> bool:
    title_crop = _prepare_color(_relative_crop(image, (0.22, 0.04, 0.98, 0.68)))
    title_text = _search_text(_ocr(title_crop, "vie", 11))
    return "GIAY CHUNG NHAN" in title_text or "QUYEN SU DUNG" in title_text


def _gcn_code_is_strong_without_title(
    publication_number: str,
    candidates: list[str],
    reference_codes: list[str],
) -> bool:
    counts = Counter(candidates)
    votes = counts.get(publication_number, 0)
    if votes >= 3:
        return True
    if publication_number not in reference_codes:
        return False

    selected_parts = _publication_parts(publication_number)
    if selected_parts is None:
        return False
    selected_letters, selected_digits = selected_parts
    supporting_votes = 0
    for candidate, candidate_votes in counts.items():
        parts = _publication_parts(candidate)
        if parts is None:
            continue
        letters, digits = parts
        same_number = digits == selected_digits and _edit_distance(
            letters,
            selected_letters,
        ) <= 1
        clipped_number = (
            letters == selected_letters
            and 1 <= len(selected_digits) - len(digits) <= 2
            and selected_digits.startswith(digits)
        )
        if same_number or clipped_number:
            supporting_votes += candidate_votes
    return supporting_votes >= 2


def _gcn_code_conflicts_with_only_reference(
    publication_number: str,
    reference_codes: list[str],
) -> bool:
    if len(reference_codes) != 1:
        return False
    publication_parts = _publication_parts(publication_number)
    reference_parts = _publication_parts(reference_codes[0])
    if publication_parts is None or reference_parts is None:
        return False
    return (
        publication_parts[0] != reference_parts[0]
        and publication_parts[1] != reference_parts[1]
    )


def _gcn_candidates_from_regions(
    image: Image.Image,
    regions: tuple[tuple[tuple[float, float, float, float], bool], ...],
) -> list[str]:
    candidates: list[str] = []
    for region, use_dark_threshold in regions:
        crop = _relative_crop(image, region).convert("RGB")
        for channel in ("R", "G", "B"):
            base = ImageOps.autocontrast(crop.getchannel(channel), cutoff=0.5)
            variants = [base]
            if use_dark_threshold:
                variants.append(base.point(lambda value: 255 if value > 100 else 0))
            for prepared in variants:
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
                candidate = _gcn_candidate(text)
                if candidate:
                    candidates.append(candidate)
    return candidates


def _detect_gcn(
    image: Image.Image,
    reference_codes: list[str] | None = None,
    preferred_reference: str | None = None,
) -> AutoNameResult | None:
    reference_codes = reference_codes or []

    primary_regions = (
        ((0.845, 0.795, 0.940, 0.850), False),
        ((0.865, 0.82, 0.970, 0.88), False),
        ((0.82, 0.80, 0.96, 0.89), False),
        # Some CamScanner pages cut the final digit against the right edge.
        ((0.86, 0.785, 0.985, 0.875), True),
    )
    candidates = _gcn_candidates_from_regions(image, primary_regions)
    publication_number = _select_publication_number(
        candidates,
        reference_codes,
        preferred_reference,
    )
    title_confirmed = _is_gcn_cover(image)

    if (
        publication_number is not None
        and not _gcn_code_conflicts_with_only_reference(
            publication_number,
            reference_codes,
        )
        and (
            title_confirmed
            or _gcn_code_is_strong_without_title(
                publication_number,
                candidates,
                reference_codes,
            )
        )
    ):
        return AutoNameResult(
            sanitize_filename(publication_number),
            "GCN",
            f"Đã nhận dạng GCN: số phát hành {publication_number}",
        )

    # A wrong orientation or a non-GCN page usually has neither a title nor a
    # serial candidate.  Stop here so the caller can try the next rotation
    # without spending many OCR passes on unrelated lower-page regions.
    if not title_confirmed and not candidates:
        return None

    fallback_regions = (
        ((0.72, 0.80, 0.91, 0.90), False),
        ((0.84, 0.72, 0.98, 0.82), False),
        ((0.68, 0.70, 0.88, 0.82), False),
        ((0.35, 0.70, 0.75, 0.96), False),
        ((0.20, 0.68, 0.98, 0.97), False),
        # Red-cover and portrait scans print the serial lower and farther left.
        ((0.62, 0.82, 0.92, 0.92), True),
        ((0.60, 0.80, 0.94, 0.94), True),
    )
    candidates.extend(_gcn_candidates_from_regions(image, fallback_regions))
    publication_number = _select_publication_number(
        candidates,
        reference_codes,
        preferred_reference,
    )

    if (
        publication_number is not None
        and not _gcn_code_conflicts_with_only_reference(
            publication_number,
            reference_codes,
        )
        and (
            title_confirmed
            or _gcn_code_is_strong_without_title(
                publication_number,
                candidates,
                reference_codes,
            )
        )
    ):
        return AutoNameResult(
            sanitize_filename(publication_number),
            "GCN",
            f"Đã nhận dạng GCN: số phát hành {publication_number}",
        )

    # Last resort for a confirmed cover whose serial is physically clipped or
    # too blurred to read: use the range-matched source hint only when OCR found
    # no candidate at all.  For a one-code source, the sole hint may also recover
    # a severely degraded serial.  Multi-code folders with conflicting OCR are
    # deliberately left for manual review instead of forcing their page order.
    source_fallback = None
    if title_confirmed and preferred_reference and not candidates:
        source_fallback = preferred_reference
    elif title_confirmed and preferred_reference:
        preferred_parts = _publication_parts(preferred_reference)
        parsed_short = [
            parts
            for candidate in candidates
            if (parts := _publication_parts(candidate)) is not None
        ]
        if (
            preferred_parts is not None
            and parsed_short
            and all(len(digits) <= 4 for _, digits in parsed_short)
            and sum(
                letters == preferred_parts[0]
                for letters, _ in parsed_short
            )
            > len(parsed_short) / 2
        ):
            source_fallback = preferred_reference
    if source_fallback is None and title_confirmed and len(reference_codes) == 1:
        source_fallback = reference_codes[0]
    if source_fallback:
        return AutoNameResult(
            sanitize_filename(source_fallback),
            "GCN",
            f"Đã nhận dạng bìa GCN và đối chiếu số phát hành {source_fallback}",
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
    preferred_reference = None
    if publication_codes and range_start:
        pair_index = max(0, (range_start - 1) // 2)
        reference_index = len(publication_codes) - 1 - pair_index
        if 0 <= reference_index < len(publication_codes):
            preferred_reference = publication_codes[reference_index]

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
            gcn = _detect_gcn(image, publication_codes, preferred_reference)
            if gcn:
                return gcn
    return None
