from pathlib import Path
from dataclasses import dataclass, field
import tomllib

APP_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = APP_ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
DATABASE_PATH = DATA_DIR / "catalog.duckdb"

SUPPORTED_EXTENSIONS = {".pdf", ".xlsx", ".xls", ".csv", ".docx", ".txt", ".md", ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
IGNORED_NAMES = {".git", "node_modules", "__pycache__", "cache"}
IGNORED_PREFIXES = ("~$",)
CONFIG_PATH = APP_ROOT / "config.toml"

@dataclass
class Settings:
    directories: list[str] = field(default_factory=list)
    extensions: list[str] = field(default_factory=lambda: sorted(SUPPORTED_EXTENSIONS))
    ignored_patterns: list[str] = field(default_factory=lambda: ['~$*.xlsx', '*.tmp', '*.bak', '.git/', 'node_modules/', 'cache/'])

    @classmethod
    def load(cls):
        if not CONFIG_PATH.exists(): return cls()
        with CONFIG_PATH.open('rb') as file:
            raw = tomllib.load(file)
        return cls(raw.get('indexing', {}).get('directories', []), raw.get('indexing', {}).get('extensions', sorted(SUPPORTED_EXTENSIONS)), raw.get('indexing', {}).get('ignored_patterns', []))

    def save(self):
        def values(items): return ', '.join('"' + x.replace('"', '\\"') + '"' for x in items)
        CONFIG_PATH.write_text('[database]\npath = "./data/catalog.duckdb"\n\n[indexing]\n' + f'directories = [{values(self.directories)}]\n' + f'extensions = [{values(self.extensions)}]\n' + f'ignored_patterns = [{values(self.ignored_patterns)}]\n')
