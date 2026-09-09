# Execute no Windows, com Python 3.11 instalado.
py -3.11 -m pip install --user -r requirements.txt pyinstaller
py -3.11 -m PyInstaller --noconfirm --clean --onefile --windowed --name LocalKnowledgeExplorer --collect-all duckdb --add-data "database/schema.sql;database" app/windows_launcher.py
