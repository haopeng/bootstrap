"""Turn uploaded files into plain text.  PDF via pypdf, everything else as UTF-8."""
from __future__ import annotations

import io
import os
from dataclasses import dataclass


@dataclass
class Doc:
    name: str
    text: str
    pages: int = 1

    @property
    def kind(self) -> str:
        t = self.text.lower()
        if "invoice" in t and ("amount due" in t or "total" in t or "invoice #" in t or "invoice no" in t):
            return "invoice"
        if any(k in t for k in ("agreement", "hereby", "party", "terminate", "governing law")):
            return "contract"
        return "other"


def load_bytes(name: str, data: bytes) -> Doc:
    if name.lower().endswith(".pdf"):
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        text = "\n".join((p.extract_text() or "") for p in reader.pages)
        return Doc(name=name, text=text, pages=len(reader.pages))
    return Doc(name=name, text=data.decode("utf-8", errors="replace"))


def load_path(path: str) -> Doc:
    with open(path, "rb") as f:
        return load_bytes(os.path.basename(path), f.read())
