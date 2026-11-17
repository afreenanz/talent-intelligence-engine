"""Download and verify TalentCLEF 2026 Task A (CC BY 4.0) into data/external/ (git-ignored).

Source: Zenodo record 19652670, "TalentCLEF 2026 corpus: Skill and Job Title Intelligence for
Human Capital Management", v0.3.0. Licence: CC BY 4.0, which requires attribution (see
data/README.md). Per the organisers, the CVs are synthetic ("the data we utilize inherently
excludes any personal information") and relevance labels were assigned by human experts.

Usage (from backend/):  uv run python -m scripts.fetch_talentclef
"""

import hashlib
import urllib.request
import zipfile
from pathlib import Path

URL = "https://zenodo.org/records/19652670/files/TaskA.zip?download=1"
# Pinned 2026-11-17. MD5 matches the checksum Zenodo publishes for this file.
EXPECTED_MD5 = "431ec3b693ae1ba24fe04793f9c1f750"
EXPECTED_SHA256 = "3437ef0437b0f603a15c5e3f8e62e3450ba24cb2bbbdbc5ad328829bbce0e179"
TARGET = Path(__file__).resolve().parents[2] / "data" / "external" / "talentclef2026"


def _verify(data: bytes) -> None:
    md5 = hashlib.md5(data, usedforsecurity=False).hexdigest()
    sha = hashlib.sha256(data).hexdigest()
    if md5 != EXPECTED_MD5 or sha != EXPECTED_SHA256:
        raise SystemExit(f"checksum mismatch (md5={md5}, sha256={sha}); refusing to use the file")


def _safe_extract(archive: Path, dest: Path) -> int:
    count = 0
    with zipfile.ZipFile(archive) as z:
        for info in z.infolist():
            target = (dest / info.filename).resolve()
            if not str(target).startswith(str(dest.resolve())):  # zip-slip guard
                raise SystemExit(f"unsafe path in archive: {info.filename}")
            if info.is_dir():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(z.read(info))
            count += 1
    return count


def main() -> None:
    TARGET.mkdir(parents=True, exist_ok=True)
    archive = TARGET / "TaskA.zip"
    if archive.exists():
        data = archive.read_bytes()
    else:
        with urllib.request.urlopen(URL, timeout=120) as resp:
            data = resp.read()
    _verify(data)
    archive.write_bytes(data)
    n = _safe_extract(archive, TARGET)
    print(f"verified and extracted {n} files to {TARGET}")


if __name__ == "__main__":
    main()
