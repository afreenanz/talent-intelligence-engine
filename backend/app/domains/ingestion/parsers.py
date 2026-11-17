"""Streaming readers for job files. Each yields raw dicts one at a time.

Streaming matters: a 100k-row CSV is never fully loaded into memory. JSON arrays are the
exception (the stdlib parser has no streaming mode), so large feeds should use JSON Lines.
"""

import csv
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any


class UnsupportedFileError(ValueError):
    pass


def read_records(path: Path) -> Iterator[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        yield from _read_csv(path)
    elif suffix in {".jsonl", ".ndjson"}:
        yield from _read_jsonl(path)
    elif suffix == ".json":
        yield from _read_json(path)
    else:
        raise UnsupportedFileError(f"Unsupported file type {suffix!r}: use .csv, .json or .jsonl")


def _read_csv(path: Path) -> Iterator[dict[str, Any]]:
    # utf-8-sig transparently drops the BOM that Excel adds to CSV exports.
    with path.open(newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            yield {k.strip(): v for k, v in row.items() if k is not None}


def _read_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with path.open(encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as exc:
                # A corrupt line becomes a record-level failure, not a crash of the whole import.
                yield {"__parse_error__": f"line {line_no}: {exc.msg}", "__raw__": line[:2000]}
                continue
            yield (
                obj
                if isinstance(obj, dict)
                else {"__parse_error__": f"line {line_no}: not an object"}
            )


def _read_json(path: Path) -> Iterator[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data.get("jobs", data) if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise UnsupportedFileError('JSON file must be a list of jobs or {"jobs": [...]}')
    for i, obj in enumerate(items):
        yield obj if isinstance(obj, dict) else {"__parse_error__": f"item {i}: not an object"}
