import os
import sys
from pathlib import Path
from dataclasses import dataclass, field
import tomllib

APP_ROOT = Path(__file__).resolve().parents[1]

# O executável PyInstaller é extraído numa pasta temporária e apagado ao sair.
# Catálogo e configuração devem viver no perfil do utilizador, não ali.
if getattr(sys, 'frozen', False):
    DATA_DIR = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local')) / 'LocalKnowledgeExplorer'
else:
    DATA_DIR = APP_ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
DATABASE_PATH = DATA_DIR / "catalog.duckdb"

SUPPORTED_EXTENSIONS = {".pdf", ".xlsx", ".xls", ".csv", ".docx", ".txt", ".md", ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
IGNORED_NAMES = {
    ".git", "node_modules", "__pycache__", "cache", ".venv", "venv", "env",
    ".tox", ".pytest_cache", ".mypy_cache", "site-packages", "dist", "build",
    "runs", "pilot-payment-rules", ".next", ".nuxt", "coverage", ".coverage",
}
IGNORED_PREFIXES = ("~$",)
CONFIG_PATH = DATA_DIR / "config.toml" if getattr(sys, 'frozen', False) else APP_ROOT / "config.toml"

@dataclass
class Settings:
    directories: list[str] = field(default_factory=list)
    extensions: list[str] = field(default_factory=lambda: sorted(SUPPORTED_EXTENSIONS))
    ignored_patterns: list[str] = field(default_factory=lambda: ['~$*.xlsx', '*.tmp', '*.bak', '.git/', 'node_modules/', 'cache/'])
    watch: bool = True

    @classmethod
    def load(cls):
        if not CONFIG_PATH.exists(): return cls()
        with CONFIG_PATH.open('rb') as file:
            raw = tomllib.load(file)
        indexing = raw.get('indexing', {})
        return cls(indexing.get('directories', []), indexing.get('extensions', sorted(SUPPORTED_EXTENSIONS)), indexing.get('ignored_patterns', []), indexing.get('watch', True))

    def save(self):
        def values(items): return ', '.join('"' + x.replace('"', '\\"') + '"' for x in items)
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text('[database]\n' + f'path = "{DATABASE_PATH.as_posix()}"\n\n[indexing]\n' + f'directories = [{values(self.directories)}]\n' + f'extensions = [{values(self.extensions)}]\n' + f'ignored_patterns = [{values(self.ignored_patterns)}]\n' + f'watch = {str(self.watch).lower()}\n', encoding='utf-8')
