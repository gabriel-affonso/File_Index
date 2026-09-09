"""Servidor local e API da interface V2 do Local Knowledge Explorer."""
from __future__ import annotations

import json
import mimetypes
import os
import subprocess
import sys
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from app.config import Settings
from core.services import ExplorerService
from database.duckdb import Catalog
from indexing.indexer import Indexer
from indexing.watcher import IndexWatcher

BUILD_ID = "2.0.0"
STATIC_DIR = Path(__file__).with_name("static")
catalog = Catalog()
service = ExplorerService(catalog)
progress_lock = threading.Lock()
progress = {"active": False, "current": 0, "total": 0, "name": "", "result": "", "errors": []}
watcher = IndexWatcher(catalog)


def open_local_file(path: Path) -> None:
    if sys.platform.startswith("win"):
        os.startfile(path)  # noqa: S606
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def reveal_local_file(path: Path) -> None:
    if sys.platform.startswith("win"):
        subprocess.Popen(["explorer.exe", "/select,", str(path)])
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path.parent)])


def record_for(file_id: str) -> dict | None:
    with catalog.lock:
        return service.detail_record(file_id)


def json_value(value):
    if value is None:
        return None
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
        return None
    return str(value) if not isinstance(value, (str, int, float, bool, list, dict)) else value


def dataset_rows(record: dict, sheet_name: str | None, offset: int, limit: int, query: str):
    import pandas as pd

    path = Path(record["path"])
    limit = max(1, min(limit, 250))
    if path.suffix.lower() == ".csv":
        frame = pd.read_csv(path, nrows=offset + limit, encoding_errors="replace").iloc[offset:]
        sheet_name = "Dados"
    else:
        workbook = pd.ExcelFile(path)
        sheet_name = sheet_name or workbook.sheet_names[0]
        frame = pd.read_excel(path, sheet_name=sheet_name, nrows=offset + limit).iloc[offset:]
    frame = frame.fillna("")
    if query.strip():
        term = query.casefold()
        frame = frame[frame.astype(str).apply(lambda row: row.str.casefold().str.contains(term, regex=False).any(), axis=1)]
    columns = [str(column) for column in frame.columns]
    rows = [[json_value(value) for value in row] for row in frame.itertuples(index=False, name=None)]
    return {"sheet": sheet_name, "columns": columns, "rows": rows, "offset": offset, "limit": limit}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def send_json(self, payload, status=HTTPStatus.OK):
        data = json.dumps(payload, default=str, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def send_file(self, path: Path, mime_type: str | None = None):
        if not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mime_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def body(self):
        size = int(self.headers.get("Content-Length", "0"))
        try:
            return json.loads(self.rfile.read(size) or b"{}")
        except json.JSONDecodeError:
            return {}

    def static(self, route: str):
        target = STATIC_DIR / ("index.html" if route == "/" else route.removeprefix("/static/"))
        try:
            target.resolve().relative_to(STATIC_DIR.resolve())
        except ValueError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self.send_file(target)

    def do_GET(self):
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        route = parsed.path
        if route == "/" or route.startswith("/static/"):
            return self.static(route)
        if route == "/api/status":
            with catalog.lock:
                files = catalog.scalar("SELECT count(*) FROM files WHERE deleted=FALSE AND excluded=FALSE") or 0
                folders = catalog.scalar("SELECT count(*) FROM folders") or 0
            return self.send_json({"version": BUILD_ID, "files": files, "folders": folders, "settings": Settings.load().__dict__})
        if route == "/api/search":
            text = query.get("q", [""])[0]
            category = query.get("category", [None])[0]
            with catalog.lock:
                rows = service.search(text, category)
            return self.send_json([{"id": row[0], "name": row[1], "path": row[2], "extension": row[3], "kind": row[4], "size": row[5], "score": row[6]} for row in rows[:300]])
        if route == "/api/recent":
            with catalog.lock:
                rows = catalog.conn.execute("""SELECT file_id,filename,path,file_category,size_bytes,modified_at
                    FROM files WHERE deleted=FALSE AND excluded=FALSE ORDER BY indexed_at DESC NULLS LAST LIMIT 80""").fetchall()
            return self.send_json([{"id": row[0], "name": row[1], "path": row[2], "kind": row[3], "size": row[4], "modified": row[5]} for row in rows])
        if route == "/api/folders":
            with catalog.lock:
                roots = service.folder_roots()
            return self.send_json([{"id": row[0], "path": row[1], "name": row[2], "files": row[3], "bytes": row[4] or 0} for row in roots])
        if route == "/api/collections":
            with catalog.lock:
                rows = service.collections()
                payload = []
                for collection_id, name, description, created_at in rows:
                    items = service.collection_items(collection_id)
                    payload.append({"id": collection_id, "name": name, "description": description or "", "created_at": created_at, "items": [{"type": item[0], "id": item[1], "label": item[2]} for item in items]})
            return self.send_json(payload)
        if route == "/api/folder":
            path = query.get("path", [""])[0]
            with catalog.lock:
                folders, files = service.folder_children(path)
            return self.send_json({"path": path, "folders": [{"id": row[0], "path": row[1], "name": row[2], "files": row[3], "bytes": row[4] or 0} for row in folders], "files": [{"id": row[0], "name": row[1], "path": row[2], "kind": row[3], "size": row[4]} for row in files]})
        if route == "/api/details":
            record = record_for(query.get("id", [""])[0])
            if not record:
                return self.send_json({"error": "Ficheiro não encontrado."}, HTTPStatus.NOT_FOUND)
            with catalog.lock:
                pages = catalog.conn.execute("SELECT page_number,text_content FROM document_pages WHERE file_id=? ORDER BY page_number", [record["file_id"]]).fetchall()
                datasets = service.dataset_preview(record["file_id"])
                tags = [tag[0] for tag in service.tags(record["file_id"])]
                relations = [{"type": item[0], "label": item[1], "target_type": item[2]} for item in service.relations(record["file_id"])]
            return self.send_json({"file": record, "pages": [{"number": page[0], "text": page[1]} for page in pages], "datasets": [{"sheet": row[0], "rows": row[1], "columns": row[2], "schema": row[3] or ""} for row in datasets], "tags": tags, "relations": relations})
        if route == "/api/dataset":
            record = record_for(query.get("id", [""])[0])
            if not record:
                return self.send_json({"error": "Dataset não encontrado."}, HTTPStatus.NOT_FOUND)
            try:
                return self.send_json(dataset_rows(record, query.get("sheet", [None])[0], int(query.get("offset", [0])[0]), int(query.get("limit", [100])[0]), query.get("q", [""])[0]))
            except Exception as error:
                return self.send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
        if route == "/api/pdf-page":
            record = record_for(query.get("id", [""])[0])
            if not record or Path(record["path"]).suffix.lower() != ".pdf":
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            try:
                import pymupdf
                document = pymupdf.open(record["path"])
                page = document.load_page(max(0, int(query.get("page", [1])[0]) - 1))
                png = page.get_pixmap(matrix=pymupdf.Matrix(1.4, 1.4), alpha=False).tobytes("png")
                document.close()
                self.send_response(HTTPStatus.OK); self.send_header("Content-Type", "image/png"); self.send_header("Content-Length", str(len(png))); self.end_headers(); self.wfile.write(png)
            except Exception as error:
                self.send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)
            return
        if route == "/api/image":
            record = record_for(query.get("id", [""])[0])
            if not record:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            return self.send_file(Path(record["path"]))
        if route in {"/api/open", "/api/reveal"}:
            record = record_for(query.get("id", [""])[0])
            path = Path(record["path"]) if record else None
            if not path or not path.exists():
                return self.send_json({"ok": False, "error": "Ficheiro não encontrado."}, HTTPStatus.NOT_FOUND)
            (open_local_file if route == "/api/open" else reveal_local_file)(path)
            return self.send_json({"ok": True})
        if route == "/api/graph":
            include_files = query.get("files", ["1"])[0] != "0"
            focus = query.get("focus", [None])[0]
            with catalog.lock:
                data = service.root_graph(include_files, focus) if not query.get("path") else service.folder_graph(query["path"][0], include_files, files_for_path=focus)
            return self.send_json(data)
        if route == "/api/excel-graph":
            columns = [value.strip() for value in query.get("columns", [""])[0].split(",") if value.strip()]
            with catalog.lock:
                data = service.excel_similarity_graph(columns)
            return self.send_json(data)
        if route == "/api/progress":
            with progress_lock:
                return self.send_json(progress)
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self):
        route = urlparse(self.path).path
        data = self.body()
        if route == "/api/index":
            folder = Path(str(data.get("path", ""))).expanduser()
            if not folder.is_dir():
                return self.send_json({"error": "Pasta inválida."}, HTTPStatus.BAD_REQUEST)
            with progress_lock:
                if progress["active"]:
                    return self.send_json({"error": "Já existe uma indexação em curso."}, HTTPStatus.CONFLICT)
                progress.update(active=True, current=0, total=0, name="", result="", errors=[])
            settings = Settings.load()
            if str(folder.resolve()) not in settings.directories:
                settings.directories.append(str(folder.resolve()))
                settings.save()
                watcher.start(settings)
            def run():
                indexer = Indexer(catalog, Settings.load())
                def update(current, total, name):
                    with progress_lock:
                        progress.update(current=current, total=total, name=name)
                indexed, skipped, errors = indexer.index_directory(folder, update)
                with progress_lock:
                    progress.update(active=False, result=f"{indexed} indexados, {skipped} inalterados, {errors} erros.", errors=indexer.last_errors[-20:])
            threading.Thread(target=run, daemon=True).start()
            return self.send_json({"ok": True})
        if route == "/api/config":
            settings = Settings.load()
            settings.directories = [str(Path(path)) for path in data.get("directories", settings.directories) if str(path).strip()]
            settings.ignored_patterns = [str(pattern) for pattern in data.get("ignored_patterns", settings.ignored_patterns)]
            settings.extensions = [str(extension) for extension in data.get("extensions", settings.extensions)]
            settings.watch = bool(data.get("watch", settings.watch))
            settings.save()
            watcher.start(settings)
            return self.send_json({"ok": True, "settings": settings.__dict__})
        if route == "/api/tags":
            with catalog.lock:
                service.add_tag(str(data.get("file_id", "")), str(data.get("name", "")))
            return self.send_json({"ok": True})
        if route == "/api/relations":
            with catalog.lock:
                service.create_relation(str(data.get("file_id", "")), str(data.get("target_type", "other")), str(data.get("label", "")), str(data.get("relation_type", "related_to")))
            return self.send_json({"ok": True})
        if route == "/api/collections":
            with catalog.lock:
                name = str(data.get("name", "")).strip()
                collection_id = catalog.scalar("SELECT collection_id FROM collections WHERE name=?", [name])
                if not collection_id:
                    collection_id = service.create_collection(name, str(data.get("description", "")))
            return self.send_json({"ok": True, "id": collection_id})
        if route == "/api/collections/items":
            with catalog.lock:
                service.add_to_collection(str(data.get("collection_id", "")), "file", str(data.get("file_id", "")))
            return self.send_json({"ok": True})
        self.send_error(HTTPStatus.NOT_FOUND)


def start_server():
    server = None
    for port in range(8765, 8776):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
            break
        except OSError:
            continue
    if server is None:
        raise RuntimeError("Não foi possível abrir uma porta local entre 8765 e 8775.")
    watcher.start(Settings.load())
    return server, f"http://127.0.0.1:{port}"


def main():
    server, url = start_server()
    print(f"Local Knowledge Explorer V{BUILD_ID}: {url}")
    webbrowser.open(url)
    try:
        server.serve_forever()
    finally:
        watcher.stop()
