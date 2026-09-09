"""Monitorização local, com debounce, para manter o catálogo atualizado."""
from __future__ import annotations

import threading
from pathlib import Path

from app.config import Settings
from database.duckdb import Catalog
from indexing.indexer import Indexer


class IndexWatcher:
    def __init__(self, catalog: Catalog):
        self.catalog = catalog
        self._observer = None
        self._timers: dict[Path, threading.Timer] = {}
        self._lock = threading.Lock()

    def start(self, settings: Settings):
        self.stop()
        if not settings.watch or not settings.directories:
            return
        try:
            from watchdog.events import FileSystemEventHandler
            from watchdog.observers import Observer
        except ImportError:
            return
        watcher = self

        class Changes(FileSystemEventHandler):
            def __init__(self, root: Path):
                self.root = root

            def on_any_event(self, event):
                if event.event_type not in {"created", "modified", "deleted", "moved"}:
                    return
                watcher.schedule(self.root)

        observer = Observer()
        for raw_path in settings.directories:
            root = Path(raw_path).expanduser()
            if root.is_dir():
                observer.schedule(Changes(root.resolve()), str(root), recursive=True)
        observer.start()
        self._observer = observer

    def schedule(self, root: Path):
        """Agrupa várias alterações próximas numa única reindexação incremental."""
        with self._lock:
            timer = self._timers.pop(root, None)
            if timer:
                timer.cancel()
            timer = threading.Timer(2.0, self._scan, [root])
            timer.daemon = True
            self._timers[root] = timer
            timer.start()

    def _scan(self, root: Path):
        try:
            if root.is_dir():
                Indexer(self.catalog, Settings.load()).index_directory(root)
        finally:
            with self._lock:
                self._timers.pop(root, None)

    def stop(self):
        with self._lock:
            for timer in self._timers.values():
                timer.cancel()
            self._timers.clear()
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=3)
            self._observer = None
