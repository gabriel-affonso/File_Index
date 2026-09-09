from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.config import Settings
from core.services import ExplorerService
from database.duckdb import Catalog
from indexing.indexer import Indexer


class IndexerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = (Path(self.tmp.name) / "knowledge").resolve()
        self.root.mkdir()
        self.catalog = Catalog(Path(self.tmp.name) / "catalog.duckdb")
        self.settings = Settings(extensions=[".txt"], ignored_patterns=["ignored/*"], watch=False)

    def tearDown(self):
        self.catalog.close()
        self.tmp.cleanup()

    def test_indexes_files_and_ignores_configured_paths(self):
        (self.root / "note.txt").write_text("POC001234", encoding="utf-8")
        ignored = self.root / "ignored"
        ignored.mkdir()
        (ignored / "secret.txt").write_text("do not index", encoding="utf-8")
        indexed, skipped, errors = Indexer(self.catalog, self.settings).index_directory(self.root)
        self.assertEqual((indexed, skipped, errors), (1, 0, 0))
        results = ExplorerService(self.catalog).search("POC001234")
        self.assertEqual([row[1] for row in results], ["note.txt"])

    def test_marks_missing_file_as_deleted_after_clean_scan(self):
        note = self.root / "note.txt"
        note.write_text("one", encoding="utf-8")
        indexer = Indexer(self.catalog, self.settings)
        indexer.index_directory(self.root)
        note.unlink()
        indexer.index_directory(self.root)
        self.assertEqual(self.catalog.scalar("SELECT count(*) FROM files WHERE deleted=TRUE"), 1)

    def test_excel_graph_links_only_shared_columns(self):
        service = ExplorerService(self.catalog)
        for filename, columns in (("one.xlsx", ["POC", "Area"]), ("two.xlsx", ["poc", "Owner"]), ("three.xlsx", ["Different"])):
            path = self.root / filename
            path.touch()
            file_id = self.catalog.upsert_file({"path": str(path), "directory": str(self.root), "filename": filename, "extension": ".xlsx", "size_bytes": 1, "created_at": None, "modified_at": None, "indexed_at": None, "file_hash": None, "mime_type": None, "file_category": "spreadsheet", "index_status": "indexed", "extraction_status": "complete"})
            dataset_id, sheet_id = self.catalog.new_id(), self.catalog.new_id()
            self.catalog.conn.execute("INSERT INTO datasets VALUES (?, ?, ?)", [dataset_id, file_id, "xlsx"])
            self.catalog.conn.execute("INSERT INTO sheets VALUES (?, ?, ?, ?, ?)", [sheet_id, dataset_id, "Dados", 1, len(columns)])
            for column in columns:
                self.catalog.conn.execute("INSERT INTO dataset_columns VALUES (?, ?, ?, ?, ?, ?)", [self.catalog.new_id(), sheet_id, column, "VARCHAR", 0, 1])
        graph = service.excel_similarity_graph()
        self.assertEqual(len(graph["nodes"]), 2)
        self.assertEqual(graph["edges"][0]["columns"], ["poc"])

    def test_hidden_files_reveals_only_clicked_folder(self):
        first, second = self.root / "first", self.root / "second"
        first.mkdir(); second.mkdir()
        (first / "one.txt").write_text("one", encoding="utf-8")
        (second / "two.txt").write_text("two", encoding="utf-8")
        Indexer(self.catalog, self.settings).index_directory(self.root)
        graph = ExplorerService(self.catalog).folder_graph(str(self.root), include_files=False, files_for_path=str(first))
        file_nodes = [node["label"] for node in graph["nodes"] if node["type"] == "file"]
        self.assertEqual(file_nodes, ["one.txt"])


if __name__ == "__main__":
    unittest.main()
