# Execute no Windows, com Python 3.11 instalado.
python -m pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm --clean --onefile --windowed --name LocalKnowledgeExplorer --collect-all duckdb --add-data "database/schema.sql;database" app/windows_launcher.py
