# Execute no Windows, com Python 3.11 instalado.
py -3.11 -m pip install --user -r requirements.txt pyinstaller
py -3.11 -m PyInstaller --noconfirm --clean --onefile --windowed --name FileIndexV2 --collect-all duckdb --add-data "database/schema.sql;database" --add-data "app/static;app/static" app/windows_launcher.py
