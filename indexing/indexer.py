from __future__ import annotations
import mimetypes, os, re
from datetime import datetime
from pathlib import Path
from database.duckdb import Catalog
from app.config import SUPPORTED_EXTENSIONS, IGNORED_NAMES, IGNORED_PREFIXES
from .extractors import extract_dataset, extract_text

POC_PATTERN = re.compile(r'\bPOC[\s_-]?(\d{6})\b', re.I)

def category(path: Path):
    return {'pdf': 'document', 'docx': 'document', 'txt': 'document', 'md': 'document', 'xlsx': 'spreadsheet', 'xls': 'spreadsheet', 'csv': 'dataset'}.get(path.suffix[1:].lower(), 'image')

class Indexer:
    def __init__(self, catalog: Catalog): self.catalog = catalog
    def index_directory(self, root: str | Path, progress=lambda *_: None):
        root = Path(root).resolve(); indexed = skipped = errors = 0
        self.catalog.ensure_folder(root, root)
        paths = [path for path in root.rglob('*') if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS and not any(x in path.parts for x in IGNORED_NAMES) and not path.name.startswith(IGNORED_PREFIXES)]
        total = len(paths)
        progress(0, total, 'A preparar indexação…')
        for position, path in enumerate(paths, 1):
            try:
                self.catalog.ensure_folder(path.parent, root)
                changed = self.index_file(path, root)
                indexed += bool(changed); skipped += not changed
                progress(position, total, path.name)
            except Exception: errors += 1
        self.catalog.refresh_folder_stats(root)
        self.catalog.conn.execute("UPDATE files SET deleted = TRUE WHERE directory LIKE ? AND NOT EXISTS (SELECT 1)", [str(root) + '%']) if False else None
        return indexed, skipped, errors
    def index_file(self, path: Path, root: Path | None = None):
        stat = path.stat(); old = self.catalog.conn.execute('SELECT file_id, size_bytes, modified_at FROM files WHERE path = ?', [str(path)]).fetchone()
        modified = datetime.fromtimestamp(stat.st_mtime)
        if old and old[1] == stat.st_size and old[2] == modified:
            if root: self.catalog.attach_file_to_folder(old[0], path.parent, root)
            return False
        file_id = self.catalog.upsert_file({'path':str(path), 'directory':str(path.parent), 'filename':path.name, 'extension':path.suffix.lower(), 'size_bytes':stat.st_size, 'created_at':datetime.fromtimestamp(stat.st_ctime), 'modified_at':modified, 'indexed_at':datetime.now(), 'mime_type':mimetypes.guess_type(str(path))[0], 'file_category':category(path), 'index_status':'indexed', 'extraction_status':'complete'})
        if root: self.catalog.attach_file_to_folder(file_id, path.parent, root)
        self.catalog.clear_extraction(file_id)
        if path.suffix.lower() in {'.pdf','.docx','.txt','.md'}:
            text, pages, method = extract_text(path)
            self.catalog.conn.execute('INSERT INTO document_content VALUES (?, ?, ?, ?, ?, ?)', [file_id, path.stem, text, len(pages) or None, len(text.split()), method])
            for number, page in enumerate(pages, 1): self.catalog.conn.execute('INSERT INTO document_pages VALUES (?, ?, ?)', [file_id, number, page])
            self._poc_relations(file_id, text + ' ' + path.name)
        elif path.suffix.lower() in {'.xlsx','.xls','.csv'}:
            dataset_id = self.catalog.new_id(); self.catalog.conn.execute('INSERT INTO datasets VALUES (?, ?, ?)', [dataset_id, file_id, path.suffix[1:]])
            for name, frame in extract_dataset(path):
                sheet_id = self.catalog.new_id(); self.catalog.conn.execute('INSERT INTO sheets VALUES (?, ?, ?, ?, ?)', [sheet_id, dataset_id, name, len(frame), len(frame.columns)])
                for col in frame.columns:
                    series = frame[col]; self.catalog.conn.execute('INSERT INTO dataset_columns VALUES (?, ?, ?, ?, ?, ?)', [self.catalog.new_id(), sheet_id, str(col), str(series.dtype), int(series.isna().sum()), int(series.nunique())])
                self._poc_relations(file_id, ' '.join(map(str, frame.astype(str).head(1000).to_numpy().flatten())) + ' ' + path.name)
        return True
    def _poc_relations(self, file_id, source):
        for number in set(POC_PATTERN.findall(source)):
            label = f'POC{number}'; resource = self.catalog.scalar("SELECT resource_id FROM resources WHERE resource_type='poc' AND label=?", [label])
            if not resource:
                resource = self.catalog.new_id(); self.catalog.conn.execute('INSERT INTO resources VALUES (?, ?, ?, ?)', [resource, 'poc', label, '{}'])
            exists = self.catalog.scalar("SELECT relation_id FROM relations WHERE source_id=? AND target_id=? AND relation_type='references'", [file_id, resource])
            if not exists: self.catalog.conn.execute('INSERT INTO relations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)', [self.catalog.new_id(), 'file', file_id, 'references', 'poc', resource, 'automatic', .8, datetime.now()])
