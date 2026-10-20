"""Bounded document parsing, row profiling, and section-aware text chunks."""

import csv
import io
import math
import re
import statistics
import zipfile
from pathlib import Path
from fastapi import HTTPException

MAX_BYTES = 10 * 1024 * 1024
MAX_ROWS = 20000


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None


def profile(rows):
    columns = sorted({key for row in rows for key in row})
    result = {}
    for column in columns:
        values = [r.get(column) for r in rows]
        present = [v for v in values if v is not None and str(v).strip()]
        nums = [number(v) for v in present]
        numeric = bool(present) and all(v is not None for v in nums)
        dates = [
            str(v)[:10] for v in present if re.fullmatch(r"\d{4}-\d{2}-\d{2}.*", str(v))
        ]
        stats = {
            "missing": len(values) - len(present),
            "type": "number"
            if numeric
            else "date"
            if len(dates) == len(present) and present
            else "text",
        }
        if numeric:
            mean = statistics.mean(nums)
            sd = statistics.pstdev(nums)
            stats.update(
                min=min(nums),
                max=max(nums),
                mean=round(mean, 3),
                outliers=sum(abs(x - mean) > 3 * sd for x in nums) if sd else 0,
            )
        if dates:
            stats["date_range"] = [min(dates), max(dates)]
        result[column] = stats
    fingerprints = [tuple(sorted((k, str(v)) for k, v in row.items())) for row in rows]
    return {
        "rows": len(rows),
        "columns": result,
        "duplicates": len(rows) - len(set(fingerprints)),
        "outlier_method": "absolute deviation > 3 population standard deviations; diagnostic only",
    }


def parse(name, raw):
    if len(raw) > MAX_BYTES:
        raise HTTPException(413, "Maximum upload is 10 MB")
    ext = Path(name).suffix.lower()
    if ext in {".docx", ".xlsx"}:
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                if sum(i.file_size for i in archive.infolist()) > 50 * 1024 * 1024:
                    raise HTTPException(413, "Expanded archive exceeds 50 MB")
        except zipfile.BadZipFile:
            raise HTTPException(400, "Invalid Office document")
    rows, pages = None, []
    try:
        if ext == ".csv":
            reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig")))
            rows = []
            for row in reader:
                if len(rows) >= MAX_ROWS:
                    raise HTTPException(413, "Maximum 20,000 rows")
                if None in row:
                    raise HTTPException(400, "CSV row has more cells than headers")
                rows.append(row)
        elif ext == ".xlsx":
            from openpyxl import load_workbook

            book = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
            sheet = book.active
            values = iter(sheet.values)
            header = [str(v or f"column_{i + 1}") for i, v in enumerate(next(values))]
            if len(set(header)) != len(header):
                raise HTTPException(400, "Duplicate column names")
            rows = []
            for values_row in values:
                if len(rows) >= MAX_ROWS:
                    raise HTTPException(413, "Maximum 20,000 rows")
                rows.append(
                    {
                        k: v.isoformat() if hasattr(v, "isoformat") else v
                        for k, v in zip(header, values_row)
                    }
                )
            book.close()
        elif ext == ".pdf":
            from pypdf import PdfReader

            doc = PdfReader(io.BytesIO(raw))
            if len(doc.pages) > 200:
                raise HTTPException(413, "Maximum 200 PDF pages")
            pages = [
                {"page": i + 1, "text": p.extract_text() or ""}
                for i, p in enumerate(doc.pages)
            ]
        elif ext == ".docx":
            from docx import Document

            doc = Document(io.BytesIO(raw))
            pages = [
                {
                    "page": None,
                    "text": "\n".join(
                        ("# " if p.style.name.startswith("Heading") else "") + p.text
                        for p in doc.paragraphs
                    ),
                }
            ]
        elif ext in {".txt", ".md"}:
            pages = [{"page": None, "text": raw.decode("utf-8-sig")}]
        else:
            raise HTTPException(415, "Use CSV, XLSX, PDF, DOCX, TXT, or MD")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(
            400, "The file could not be parsed; check its format and encoding"
        )
    if rows is not None:
        if not rows:
            raise HTTPException(400, "No data rows found")
        return {"rows": rows, "profile": profile(rows)}
    if not any(p["text"].strip() for p in pages):
        raise HTTPException(
            400, "No extractable text. Scanned PDFs need OCR before upload."
        )
    if sum(len(p["text"]) for p in pages) > 1500000:
        raise HTTPException(413, "Extracted text exceeds 1.5 million characters")
    return {"pages": pages, "chunks": chunk(pages)}


def chunk(pages):
    chunks = []
    section = "Document"
    for page in pages:
        blocks = re.split(r"(?m)^(#{1,6} .+)$", page["text"])
        for block in blocks:
            if block.startswith("#"):
                section = block.lstrip("# ").strip()
                continue
            words = block.split()
            for start in range(0, len(words), 180):
                text = " ".join(words[start : start + 220])
                if not text:
                    continue
                injection = bool(
                    re.search(
                        r"ignore (all |previous |prior )*instructions|system prompt|override.*approval|act as (system|admin)",
                        text,
                        re.I,
                    )
                )
                chunks.append(
                    {
                        "key": f"C{len(chunks) + 1:04}",
                        "page": page["page"],
                        "section": section,
                        "text": text,
                        "injection_flag": injection,
                    }
                )
    return chunks
