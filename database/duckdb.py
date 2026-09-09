from __future__ import annotations
import uuid
import sys
import threading
from pathlib import Path
import duckdb
from app.config import DATABASE_PATH


class Catalog:
    def __init__(self, path: Path = DATABASE_PATH):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = duckdb.connect(str(path))
        # A ligação DuckDB é partilhada pelo indexador e pelo servidor local.
        # Serializar acesso evita que uma query troque a metadata da outra.
        self.lock = threading.RLock()
        # Em modo PyInstaller, schema.sql é carregado de sys._MEIPASS.
        asset_root = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
        schema = (asset_root / 'database' / 'schema.sql').read_text(encoding='utf-8')
        self.conn.execute(schema)

    @staticmethod
    def new_id() -> str: return str(uuid.uuid4())

    def scalar(self, query, params=()):
        row = self.conn.execute(query, params).fetchone()
        return row[0] if row else None

    def file_at(self, path: str):
        return self.conn.execute("SELECT * FROM files WHERE path = ?", [path]).fetchone()

    def upsert_file(self, values: dict) -> str:
        existing = self.scalar("SELECT file_id FROM files WHERE path = ?", [values['path']])
        if existing:
            columns = [k for k in values if k != 'file_id']
            self.conn.execute(f"UPDATE files SET {', '.join(f'{c} = ?' for c in columns)}, deleted = FALSE WHERE file_id = ?", [values[c] for c in columns] + [existing])
            return existing
        values['file_id'] = self.new_id()
        cols = list(values)
        self.conn.execute(f"INSERT INTO files ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})", [values[c] for c in cols])
        return values['file_id']

    def ensure_folder(self, path: Path, root: Path) -> str:
        """Regista um diretório sem mover nem alterar conteúdo no disco."""
        path = path.resolve(); root = root.resolve()
        existing = self.scalar('SELECT folder_id FROM folders WHERE path = ?', [str(path)])
        if existing: return existing
        if path != root:
            self.ensure_folder(path.parent, root)
        parent = None if path == root else str(path.parent)
        try: depth = len(path.relative_to(root).parts)
        except ValueError: depth = 0
        folder_id = self.new_id()
        self.conn.execute('INSERT INTO folders VALUES (?, ?, ?, ?, ?, 0, 0, current_timestamp)', [folder_id, str(path), parent, path.name or str(path), depth])
        return folder_id

    def attach_file_to_folder(self, file_id: str, folder: Path, root: Path):
        folder_id = self.ensure_folder(folder, root)
        self.conn.execute('INSERT OR IGNORE INTO folder_items VALUES (?, ?)', [folder_id, file_id])

    def refresh_folder_stats(self, root: Path):
        root_text = str(root.resolve())
        self.conn.execute('''UPDATE folders AS fo SET file_count = coalesce(stats.file_count, 0), total_bytes = coalesce(stats.total_bytes, 0), indexed_at = current_timestamp
            FROM (SELECT directory, count(*) AS file_count, sum(size_bytes) AS total_bytes FROM files WHERE deleted = FALSE AND excluded = FALSE GROUP BY directory) stats
            WHERE fo.path = stats.directory AND fo.path LIKE ?''', [root_text + '%'])

    def clear_extraction(self, file_id: str):
        for table in ('document_pages', 'document_content'):
            self.conn.execute(f'DELETE FROM {table} WHERE file_id = ?', [file_id])
        dataset_ids = self.conn.execute('SELECT dataset_id FROM datasets WHERE file_id = ?', [file_id]).fetchall()
        for (dataset_id,) in dataset_ids:
            self.conn.execute('DELETE FROM dataset_columns WHERE sheet_id IN (SELECT sheet_id FROM sheets WHERE dataset_id = ?)', [dataset_id])
            self.conn.execute('DELETE FROM sheets WHERE dataset_id = ?', [dataset_id])
        self.conn.execute('DELETE FROM datasets WHERE file_id = ?', [file_id])

    def close(self): self.conn.close()
