# Execute no Windows, com Python 3.11 instalado.
python -m pip install -r requirements.txt pyinstaller
pyinstaller --noconfirm --onefile --name LocalKnowledgeExplorer --collect-all duckdb app/windows_launcher.py
