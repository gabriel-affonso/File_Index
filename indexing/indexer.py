from __future__ import annotations
import fnmatch
import mimetypes
import os
import re
from datetime import datetime
from pathlib import Path
from database.duckdb import Catalog
from app.config import IGNORED_NAMES, IGNORED_PREFIXES, Settings, SUPPORTED_EXTENSIONS
from .extractors import extract_dataset, extract_text

POC_PATTERN = re.compile(r'\bPOC[\s_-]?(\d{6})\b', re.I)

def category(path: Path):
    return {'pdf': 'document', 'docx': 'document', 'txt': 'document', 'md': 'document', 'xlsx': 'spreadsheet', 'xls': 'spreadsheet', 'csv': 'dataset'}.get(path.suffix[1:].lower(), 'image')

class Indexer:
    def __init__(self, catalog: Catalog, settings: Settings | None = None):
        self.catalog = catalog
        self.settings = settings or Settings.load()
        self.extensions = {extension.lower() for extension in self.settings.extensions} or SUPPORTED_EXTENSIONS
        self.last_errors: list[dict[str, str]] = []

    def should_ignore(self, path: Path, root: Path | None = None) -> bool:
        parts = {part.casefold() for part in path.parts}
        if parts.intersection(IGNORED_NAMES) or path.name.startswith(IGNORED_PREFIXES):
            return True
        relative = str(path.relative_to(root)) if root and path.is_relative_to(root) else str(path)
        normalised = relative.replace('\\', '/').casefold()
        for pattern in self.settings.ignored_patterns:
            candidate = pattern.replace('\\', '/').casefold().rstrip('/')
            if fnmatch.fnmatch(normalised, candidate) or any(part == candidate for part in normalised.split('/')):
                return True
        return False

    def iter_paths(self, root: Path):
        for directory, names, filenames in os.walk(root):
            folder = Path(directory)
            names[:] = [name for name in names if not self.should_ignore(folder / name, root)]
            for filename in filenames:
                path = folder / filename
                if path.suffix.lower() in self.extensions and not self.should_ignore(path, root):
                    yield path

    def index_directory(self, root: str | Path, progress=lambda *_: None):
        root = Path(root).resolve(); indexed = skipped = errors = 0
        self.last_errors = []
        with self.catalog.lock: self.catalog.ensure_folder(root, root)
        # Duas passagens evitam manter uma lista inteira de caminhos em memória,
        # mas ainda permitem apresentar percentagem precisa na interface.
        total = sum(1 for _ in self.iter_paths(root))
        progress(0, total, 'A preparar indexação…')
        seen_paths: set[str] = set()
        for position, path in enumerate(self.iter_paths(root), 1):
            try:
                with self.catalog.lock:
                    self.catalog.ensure_folder(path.parent, root)
                    changed = self.index_file(path, root)
                seen_paths.add(str(path))
                indexed += bool(changed); skipped += not changed
                progress(position, total, path.name)
            except Exception as error:
                errors += 1
                self.last_errors.append({'path': str(path), 'error': str(error) or type(error).__name__})
        # Aplica regras novas, e só marca ficheiros removidos depois de um scan
        # completo sem falhas — assim uma pasta temporariamente inacessível não
        # faz desaparecer resultados do catálogo.
        with self.catalog.lock:
            prefix = str(root).rstrip('\\/') + os.sep + '%'
            existing = self.catalog.conn.execute('SELECT file_id,path FROM files WHERE path = ? OR path LIKE ?', [str(root), prefix]).fetchall()
            for file_id, indexed_path in existing:
                excluded = self.should_ignore(Path(indexed_path), root)
                deleted = errors == 0 and not excluded and indexed_path not in seen_paths
                self.catalog.conn.execute('UPDATE files SET excluded = ?, deleted = ? WHERE file_id = ?', [excluded, deleted, file_id])
        with self.catalog.lock: self.catalog.refresh_folder_stats(root)
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
        try:
            if path.suffix.lower() in {'.pdf','.docx','.txt','.md'}:
                text, pages, method = extract_text(path)
                self.catalog.conn.execute('INSERT INTO document_content VALUES (?, ?, ?, ?, ?, ?)', [file_id, path.stem, text, len(pages) or None, len(text.split()), method])
                for number, page in enumerate(pages, 1): self.catalog.conn.execute('INSERT INTO document_pages VALUES (?, ?, ?)', [file_id, number, page])
                self._poc_relations(file_id, text + ' ' + path.name)
            elif path.suffix.lower() in {'.xlsx','.xls','.csv'}:
                dataset_id = self.catalog.new_id(); self.catalog.conn.execute('INSERT INTO datasets VALUES (?, ?, ?)', [dataset_id, file_id, path.suffix[1:]])
                for name, frame, row_count in extract_dataset(path):
                    sheet_id = self.catalog.new_id(); self.catalog.conn.execute('INSERT INTO sheets VALUES (?, ?, ?, ?, ?)', [sheet_id, dataset_id, name, row_count if row_count is not None else len(frame), len(frame.columns)])
                    for col in frame.columns:
                        series = frame[col]; self.catalog.conn.execute('INSERT INTO dataset_columns VALUES (?, ?, ?, ?, ?, ?)', [self.catalog.new_id(), sheet_id, str(col), str(series.dtype), int(series.isna().sum()), int(series.nunique())])
                    self._poc_relations(file_id, ' '.join(map(str, frame.astype(str).head(1000).to_numpy().flatten())) + ' ' + path.name)
        except Exception:
            self.catalog.conn.execute("UPDATE files SET extraction_status = 'failed' WHERE file_id = ?", [file_id])
            raise
        return True
    def _poc_relations(self, file_id, source):
        for number in set(POC_PATTERN.findall(source)):
            label = f'POC{number}'; resource = self.catalog.scalar("SELECT resource_id FROM resources WHERE resource_type='poc' AND label=?", [label])
            if not resource:
                resource = self.catalog.new_id(); self.catalog.conn.execute('INSERT INTO resources VALUES (?, ?, ?, ?)', [resource, 'poc', label, '{}'])
            exists = self.catalog.scalar("SELECT relation_id FROM relations WHERE source_id=? AND target_id=? AND relation_type='references'", [file_id, resource])
            if not exists: self.catalog.conn.execute('INSERT INTO relations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)', [self.catalog.new_id(), 'file', file_id, 'references', 'poc', resource, 'automatic', .8, datetime.now()])
