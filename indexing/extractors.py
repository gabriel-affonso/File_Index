from __future__ import annotations
from pathlib import Path
import csv

def extract_text(path: Path) -> tuple[str, list[str], str]:
    ext = path.suffix.lower()
    if ext == '.pdf':
        import fitz
        doc = fitz.open(path); pages = [page.get_text() for page in doc]
        return '\n'.join(pages), pages, 'pymupdf'
    if ext == '.docx':
        from docx import Document
        document = Document(path); text = '\n'.join(p.text for p in document.paragraphs)
        return text, [], 'python-docx'
    if ext in {'.txt', '.md'}:
        return path.read_text(encoding='utf-8', errors='replace'), [], 'text'
    return '', [], 'none'

def extract_dataset(path: Path):
    import pandas as pd
    ext = path.suffix.lower()
    if ext == '.csv':
        return [('Dados', pd.read_csv(path, nrows=10000, encoding_errors='replace'))]
    book = pd.ExcelFile(path)
    return [(name, pd.read_excel(path, sheet_name=name, nrows=10000)) for name in book.sheet_names]
