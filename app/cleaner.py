"""CSV data-cleaning engine.

Pure pandas: no Flask and no database, so it can be unit-tested on its own.
Everything is processed as *strings* so values like ZIP codes with leading
zeros are never silently turned into numbers. Each cleaning step is
independently switchable and reports how many cells (or rows) it touched.

Entry point: clean_csv(text, options) -> JSON-serializable dict.
"""
from __future__ import annotations

import csv
import io
import json
import re
import warnings

import pandas as pd

MAX_ROWS = 5000
MAX_COLUMNS = 50
PREVIEW_ROWS = 12
MAX_PREVIEW_CELL_CHARS = 200

DEFAULT_OPTIONS = {
    "normalize_headers": True,
    "trim_whitespace": True,
    "standardize_nulls": True,
    "standardize_text": True,
    "normalize_phones": True,
    "normalize_dates": True,
    "parse_numbers": True,
    "remove_duplicates": True,
    # Opt-in: it invents data, so it is never on unless asked for.
    "fill_numeric_median": False,
}

# Cell values (compared case-insensitively) that mean "no value".
NULL_TOKENS = {"", "n/a", "#n/a", "na", "nan", "null", "none", "nil", "-", "--", "?"}

# Header words that mean a column is an identifier, not a quantity.
ID_LIKE_WORDS = {"id", "zip", "zipcode", "postal", "phone", "ssn", "code", "sku"}

_WHITESPACE_RE = re.compile(r"\s+")
_PLAIN_NUMBER_RE = re.compile(r"-?\d+(\.\d+)?")
_MONEY_RE = re.compile(
    r"(?P<neg1>-)?\s*(?P<cur>[$€£])?\s*(?P<neg2>-)?"
    r"(?P<num>\d{1,3}(?:,\d{3})+|\d+)(?P<frac>\.\d+)?"
)
_NOT_A_NAME = ("username", "filename", "hostname", "screenname", "nickname")
_NOT_A_DATE = ("candidate", "mandate", "update", "validate")


class CleanerError(ValueError):
    """Input the cleaner cannot or will not process (bad CSV, too large, ...)."""


# --------------------------------------------------------------------------
# Options and input handling
# --------------------------------------------------------------------------

def parse_options(raw: str | None) -> dict:
    """Merge a JSON options string over the defaults, rejecting anything unexpected."""
    options = dict(DEFAULT_OPTIONS)
    if not raw:
        return options
    try:
        supplied = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CleanerError("options must be valid JSON") from exc
    if not isinstance(supplied, dict):
        raise CleanerError("options must be a JSON object")
    for key, value in supplied.items():
        if key not in DEFAULT_OPTIONS:
            raise CleanerError(f"unknown option: {key}")
        if not isinstance(value, bool):
            raise CleanerError(f"option {key} must be true or false")
        options[key] = value
    return options


def decode_bytes(raw: bytes) -> str:
    """UTF-8 (with or without BOM); fall back to Windows-1252, which is what Excel writes."""
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def _detect_delimiter(text: str) -> str:
    header = text.lstrip("\r\n").split("\n", 1)[0]
    counts = {d: header.count(d) for d in (",", ";", "\t", "|")}
    best = max(counts, key=lambda d: counts[d])
    return best if counts[best] > 0 else ","


def _read_table(text: str) -> tuple[list[str], pd.DataFrame]:
    """Parse into (headers, frame). The frame has integer column labels 0..n-1 so
    duplicate or blank headers can never collide, and index = data-row number
    (line number in the file is index + 2)."""
    if not text.strip():
        raise CleanerError("the file is empty")
    try:
        raw = pd.read_csv(
            io.StringIO(text),
            sep=_detect_delimiter(text),
            header=None,
            dtype=str,
            keep_default_na=False,
            skip_blank_lines=False,
        )
    except (pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        ragged = re.search(r"Expected (\d+) fields in line (\d+), saw (\d+)", str(exc))
        if ragged:
            expected, line, saw = ragged.groups()
            raise CleanerError(
                f"could not parse the file as CSV: line {line} has {saw} columns but the header (line 1) has {expected}"
            ) from exc
        raise CleanerError("could not parse the file as CSV") from exc

    raw = raw.fillna("").astype(object)
    headers = [str(h) for h in raw.iloc[0].tolist()]
    frame = raw.iloc[1:].reset_index(drop=True)
    frame.columns = range(frame.shape[1])

    if frame.shape[1] > MAX_COLUMNS:
        raise CleanerError(f"too many columns ({frame.shape[1]}; the limit is {MAX_COLUMNS})")
    if len(frame) == 0:
        raise CleanerError("the file has a header row but no data rows")
    if len(frame) > MAX_ROWS:
        raise CleanerError(f"too many rows ({len(frame):,}; the limit is {MAX_ROWS:,})")
    return headers, frame


# --------------------------------------------------------------------------
# Column-type heuristics (based on header text)
# --------------------------------------------------------------------------

def _squash(header: str) -> str:
    return re.sub(r"[^0-9a-z]", "", header.lower())


def _words(header: str) -> set[str]:
    """Split a header into lowercase words, breaking camelCase too (signupDate -> signup, date)."""
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", header)
    return set(re.sub(r"[^0-9a-zA-Z]+", " ", spaced).lower().split())


def _is_email(header: str) -> bool:
    return "email" in _squash(header)


def _is_name(header: str) -> bool:
    s = _squash(header)
    return s.endswith("name") and not s.endswith(_NOT_A_NAME)


def _is_city(header: str) -> bool:
    s = _squash(header)
    return s.endswith("city") or s == "town"


def _is_state(header: str) -> bool:
    s = _squash(header)
    return s in ("province", "stateprovince") or s.endswith("state")


def _is_phone(header: str) -> bool:
    s = _squash(header)
    return "phone" in s or s.startswith(("mobile", "cell", "tel", "fax")) or s.endswith(("mobile", "cell"))


def _is_date(header: str) -> bool:
    if "date" in _words(header):  # signup_date, "Signup Date", signupDate
        return True
    s = _squash(header)
    if s.endswith(_NOT_A_DATE):  # candidate, update, ... are not dates
        return False
    return s.endswith(("date", "timestamp", "datetime")) or s in ("dob", "birthday")


def _is_id_like(header: str) -> bool:
    return bool(_words(header) & ID_LIKE_WORDS) or _squash(header) in ID_LIKE_WORDS


# --------------------------------------------------------------------------
# Cell-level helpers (each takes and returns a str)
# --------------------------------------------------------------------------

def _trim(value: str) -> str:
    return _WHITESPACE_RE.sub(" ", value).strip()


def _null_to_blank(value: str) -> str:
    return "" if value.strip().lower() in NULL_TOKENS else value


def _cap_word(word: str) -> str:
    """Capitalize one space-free word: hyphen parts and apostrophe parts get capitals
    (O'Neil, Mary-Jane) but a trailing possessive stays lowercase (John's)."""
    hyphen_parts = []
    for part in word.split("-"):
        pieces = part.split("'")
        capped = [pieces[0][:1].upper() + pieces[0][1:].lower()]
        for piece in pieces[1:]:
            capped.append(piece.lower() if piece.lower() == "s" else piece[:1].upper() + piece[1:].lower())
        hyphen_parts.append("'".join(capped))
    return "-".join(hyphen_parts)


def _fix_case_if_shouting_or_whispering(value: str) -> str:
    """Title-case a value only if it is ALL CAPS or all lowercase, so deliberate
    mixed case like McDonald or DeShawn is left alone."""
    if value.isupper() or value.islower():
        return " ".join(_cap_word(w) for w in value.split(" "))
    return value


def _upper_if_two_letters(value: str) -> str:
    return value.upper() if len(value) == 2 and value.isalpha() else value


def _format_phone(value: str) -> str:
    """US numbers -> 555-123-4567. Anything that isn't clearly a 10-digit number
    (extensions, international) is left exactly as it was."""
    if re.search(r"[A-Za-z]", value):
        return value
    digits = re.sub(r"\D", "", value)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10:
        return value
    return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"


def _parse_money(value: str) -> tuple[str, bool] | None:
    """'$1,250.50' -> ('1250.50', True). A plain number returns (value, False).
    Returns None if the cell isn't a number. Comma grouping must be well-formed
    (1,250 yes; 1,5 no), so European decimals aren't misread."""
    text = value.strip()
    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative, text = True, text[1:-1].strip()
    match = _MONEY_RE.fullmatch(text)
    if not match:
        return None
    negative = negative or bool(match.group("neg1") or match.group("neg2"))
    num = match.group("num")
    decorated = bool(match.group("cur")) or "," in num or text != value or value.startswith("(")
    canonical = ("-" if negative else "") + num.replace(",", "") + (match.group("frac") or "")
    return canonical, decorated


# --------------------------------------------------------------------------
# Column-level steps. Each returns the number of cells changed.
# --------------------------------------------------------------------------

def _apply(frame: pd.DataFrame, cols, func) -> int:
    changed = 0
    for j in cols:
        old = frame[j]
        new = old.map(func)
        changed += int((new != old).sum())
        frame[j] = new
    return changed


def _normalize_headers(headers: list[str]) -> list[str]:
    used: set[str] = set()
    out = []
    for i, header in enumerate(headers):
        base = re.sub(r"[^0-9a-z]+", "_", header.strip().lower()).strip("_") or f"column_{i + 1}"
        name, n = base, 1
        while name in used:
            n += 1
            name = f"{base}_{n}"
        used.add(name)
        out.append(name)
    return out


def _normalize_date_column(series: pd.Series) -> pd.Series:
    """Parse a mixed-format date column to ISO (YYYY-MM-DD, plus time if any cell
    has one). Ambiguous slashes are read month-first (US). Cells that don't parse
    are left alone, and a column where most cells don't parse is skipped entirely."""
    candidates = series[series.str.len() >= 6]
    if candidates.empty:
        return series
    nonblank = int((series != "").sum())
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            parsed = pd.to_datetime(candidates, errors="coerce", format="mixed")
        except (ValueError, TypeError, OverflowError):
            return series
    if not pd.api.types.is_datetime64_any_dtype(parsed):
        return series
    valid = parsed.dropna()
    if nonblank == 0 or len(valid) / nonblank < 0.6:
        return series
    has_time = bool((valid != valid.dt.normalize()).any())
    formatted = valid.dt.strftime("%Y-%m-%d %H:%M:%S" if has_time else "%Y-%m-%d")
    result = series.copy()
    result.loc[formatted.index] = formatted
    return result


def _parse_numbers_column(series: pd.Series) -> pd.Series:
    """Strip currency symbols and thousands separators from a numeric-looking column.
    Plain numbers (and anything that isn't numeric) are never touched."""
    nonblank = series[series != ""]
    if nonblank.empty:
        return series
    parsed = nonblank.map(_parse_money)
    numeric = parsed.notna()
    decorated = parsed[numeric].map(lambda p: p[1])
    if numeric.sum() / len(nonblank) < 0.8 or not decorated.any():
        return series
    rewrite = decorated[decorated].index
    result = series.copy()
    result.loc[rewrite] = parsed.loc[rewrite].map(lambda p: p[0])
    return result


def _fill_numeric_median(series: pd.Series) -> tuple[pd.Series, int]:
    nonblank = series[series != ""]
    blanks = series == ""
    if nonblank.empty or not blanks.any():
        return series, 0
    is_number = nonblank.map(lambda v: bool(_PLAIN_NUMBER_RE.fullmatch(v)))
    if is_number.sum() / len(nonblank) < 0.8:
        return series, 0
    median = float(pd.to_numeric(nonblank[is_number]).median())
    fill = str(int(median)) if median.is_integer() else f"{median:.2f}"
    result = series.copy()
    result[blanks] = fill
    return result, int(blanks.sum())


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------

def clean_csv(text: str, options: dict | None = None) -> dict:
    opts = dict(DEFAULT_OPTIONS)
    opts.update(options or {})

    original_headers, frame = _read_table(text)
    original = frame.copy()
    rows_in = len(frame)
    headers = list(original_headers)
    all_cols = list(frame.columns)
    steps: list[dict] = []

    def record(step_id: str, label: str, count: int) -> None:
        steps.append({"id": step_id, "label": label, "count": int(count)})

    if opts["normalize_headers"]:
        headers = _normalize_headers(headers)
        record("normalize_headers", "Column names standardized", sum(a != b for a, b in zip(original_headers, headers)))

    if opts["trim_whitespace"]:
        record("trim_whitespace", "Extra whitespace trimmed", _apply(frame, all_cols, _trim))

    if opts["standardize_nulls"]:
        record("standardize_nulls", "Placeholders (N/A, none, -) turned into blanks", _apply(frame, all_cols, _null_to_blank))

    # Always on: a row with nothing in it carries no information.
    blank_rows = (frame == "").all(axis=1)
    blank_removed = int(blank_rows.sum())
    frame = frame[~blank_rows].copy()
    record("remove_blank_rows", "Blank rows removed", blank_removed)

    if opts["standardize_text"]:
        count = _apply(frame, [j for j, h in enumerate(original_headers) if _is_email(h)], str.lower)
        count += _apply(frame, [j for j, h in enumerate(original_headers) if _is_name(h) or _is_city(h)], _fix_case_if_shouting_or_whispering)
        count += _apply(frame, [j for j, h in enumerate(original_headers) if _is_state(h)], _upper_if_two_letters)
        record("standardize_text", "Emails lowercased, names/cities/states capitalized", count)

    if opts["normalize_phones"]:
        record("normalize_phones", "Phone numbers formatted as 555-123-4567", _apply(frame, [j for j, h in enumerate(original_headers) if _is_phone(h)], _format_phone))

    if opts["normalize_dates"]:
        count = 0
        for j in (j for j, h in enumerate(original_headers) if _is_date(h)):
            new = _normalize_date_column(frame[j])
            count += int((new != frame[j]).sum())
            frame[j] = new
        record("normalize_dates", "Dates converted to YYYY-MM-DD", count)

    if opts["parse_numbers"]:
        count = 0
        for j in all_cols:
            if _is_id_like(original_headers[j]):
                continue
            new = _parse_numbers_column(frame[j])
            count += int((new != frame[j]).sum())
            frame[j] = new
        record("parse_numbers", "Currency and thousands separators stripped from numbers", count)

    duplicates_removed = 0
    if opts["remove_duplicates"]:
        duplicate_rows = frame.duplicated(keep="first")
        duplicates_removed = int(duplicate_rows.sum())
        record("remove_duplicates", "Duplicate rows removed", duplicates_removed)
        frame = frame[~duplicate_rows].copy()

    # After de-duplication, so a repeated row can't pull the median toward itself.
    if opts["fill_numeric_median"]:
        count = 0
        for j in all_cols:
            if _is_id_like(original_headers[j]):
                continue
            new, filled = _fill_numeric_median(frame[j])
            count += filled
            frame[j] = new
        record("fill_numeric_median", "Missing numbers filled with the column median", count)

    # What actually changed, cell by cell, for the survivors (index is preserved).
    before = original.loc[frame.index].to_numpy()
    after = frame.to_numpy()
    changed = before != after
    row_changed = changed.any(axis=1)

    shown = [i for i in range(len(frame)) if row_changed[i]][:PREVIEW_ROWS]
    if not shown:
        shown = list(range(min(5, len(frame))))
    preview = []
    for i in shown:
        cells = []
        for j in range(after.shape[1]):
            cell = {"v": after[i][j][:MAX_PREVIEW_CELL_CHARS]}
            if changed[i][j]:
                cell["was"] = before[i][j][:MAX_PREVIEW_CELL_CHARS]
            cells.append(cell)
        preview.append({"source_line": int(frame.index[i]) + 2, "cells": cells})

    out = frame.copy()
    out.columns = headers
    return {
        "summary": {
            "rows_in": rows_in,
            "rows_out": len(frame),
            "cells_changed": int(changed.sum()),
            "duplicates_removed": duplicates_removed,
            "blank_rows_removed": blank_removed,
        },
        "steps": steps,
        "original_columns": original_headers,
        "columns": headers,
        "preview": {"rows": preview, "rows_changed": int(row_changed.sum())},
        "cleaned_csv": out.to_csv(index=False, lineterminator="\n"),
    }


# --------------------------------------------------------------------------
# Sample data: deliberately messy so every step has something to fix.
# --------------------------------------------------------------------------

SAMPLE_FILENAME = "messy_customers_sample.csv"
SAMPLE_CSV = "\n".join(
    [
        ' Customer Name ,E-mail,Phone Number,Signup Date,City,State,Lifetime Value',
        ' john smith ,John.Smith@Example.com,(617) 555-0142,03/04/2025,boston,ma,"$1,250.00"',
        'JANE DOE,jane.doe@example.com,617.555.0199,2025-03-11,Cambridge,MA,$980',
        'Carlos  Rivera,CARLOS.RIVERA@EXAMPLE.COM,+1 617-555-0177,Mar 5 2025,SOMERVILLE,Ma,"$2,310.50"',
        "Priya Patel,priya.patel@example.com,N/A,2025/03/06,Brookline,MA,N/A",
        'john smith,john.smith@example.com,617-555-0142,2025-03-04,Boston,MA,"$1,250.00"',
        "",
        ",,,,,,",
        'Aisha Khan,aisha.khan@example.com ,(857) 555-0123,"March 7, 2025",Medford,MA,$845.00',
        "Marcus O'Neil,marcus.oneil@example.com,857.555.0188,2025-03-08,Newton,ma,$0",
        'Elena Garcia,elena.garcia@example.com,617 555 0166,03/09/2025,Quincy,MA,"$1,780.25"',
        'DAVID LEE,david.lee@example.com,none,2025-03-10,Waltham,MA,"$3,005"',
        "sofia  martins ,Sofia.Martins@Example.com,(781) 555-0111,Mar 12 2025,Lowell,MA,N/A",
        "Tom Becker,tom.becker@example.com,617-555-0150,2025-03-13,Salem,MA,$412.75",
    ]
) + "\n"
