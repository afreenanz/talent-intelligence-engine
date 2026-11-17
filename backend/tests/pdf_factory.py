"""Build small, valid text PDFs for tests (no extra dependency).

Writes a one-page PDF with Helvetica text, a correct xref table and byte offsets, which is
enough for pypdf to extract the text exactly like a real resume export.
"""


def _escape(line: str) -> str:
    return line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def make_pdf(lines: list[str]) -> bytes:
    text_ops = ["BT", "/F1 11 Tf", "14 TL", "50 780 Td"]
    for line in lines:
        text_ops.append(f"({_escape(line)}) Tj T*")
    text_ops.append("ET")
    stream = "\n".join(text_ops).encode("latin-1")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n"
    ).encode()
    return bytes(out)


SAMPLE_RESUME_LINES = [
    "Asha Verma",
    "Bengaluru, India",
    "Summary: Backend engineer who enjoys building reliable APIs.",
    "Skills: Python, FastAPI, Postgres, Docker, Kafka",
    "Experience",
    "Software Engineer, Kestrel Labs, 2021-06 to 2023-05",
    "Built payment APIs in Python and FastAPI.",
    "Senior Software Engineer, Bluefin Systems, 2023-06 to Present",
    "Owns event pipelines on Kafka.",
    "Education",
    "B.Tech Computer Science, IIT Madras, 2017 - 2021",
    "Projects",
    "Job search engine: hybrid retrieval with PostgreSQL and pgvector.",
]
