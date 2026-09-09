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


if __name__ == "__main__":
    unittest.main()
