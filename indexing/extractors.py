from __future__ import annotations
from pathlib import Path
import csv
import warnings
from itertools import islice

DATASET_SAMPLE_ROWS = 1000

def extract_text(path: Path) -> tuple[str, list[str], str]:
    ext = path.suffix.lower()
    if ext == '.pdf':
        import pymupdf
        doc = pymupdf.open(path); pages = [page.get_text() for page in doc]
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
        return [('Dados', pd.read_csv(path, nrows=DATASET_SAMPLE_ROWS, encoding_errors='replace'), None)]
    if ext == '.xlsx':
        # read_only evita carregar o workbook inteiro em memória. Só a primeira
        # linha e uma amostra pequena alimentam o catálogo de schema.
        from openpyxl import load_workbook
        with warnings.catch_warnings():
            warnings.filterwarnings('ignore', message='Data Validation extension is not supported.*', category=UserWarning)
            workbook = load_workbook(path, read_only=True, data_only=True)
        results = []
        for sheet in workbook.worksheets:
            rows = sheet.iter_rows(values_only=True)
            headers = next(rows, ())
            headers = [str(value) if value not in (None, '') else f'Coluna_{index + 1}' for index, value in enumerate(headers)]
            sample = list(islice(rows, DATASET_SAMPLE_ROWS))
            results.append((sheet.title, pd.DataFrame(sample, columns=headers), max(0, (sheet.max_row or 1) - 1)))
        workbook.close()
        return results
    # Ficheiros .xls não suportam o modo read_only do openpyxl; ainda assim a
    # leitura limita-se à amostra definida acima.
    book = pd.ExcelFile(path)
    return [(name, pd.read_excel(path, sheet_name=name, nrows=DATASET_SAMPLE_ROWS), None) for name in book.sheet_names]
