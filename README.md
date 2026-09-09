# Local Knowledge Explorer

Explorador local de conhecimento: indexa ficheiros sem os mover, pesquisar conteúdo e metadados, pré-visualizar documentos/datasets e criar relações manuais. A interface abre localmente no navegador, sem cloud ou servidor externo.

## Executar

```bash
python3.11 -m venv .venv311
.venv311/bin/pip install -r requirements.txt
.venv311/bin/python -m app.main
```

No Windows, substitua `.venv311/bin/python` por `.venv311\\Scripts\\python.exe`.

O browser abre automaticamente. Deixe o Terminal em execução enquanto utiliza a app e pressione `Ctrl+C` para a encerrar.

## Windows

No Windows, execute `python -m app.windows_launcher`. O atalho global `Ctrl+Shift+Espaço` abre a app no browser. Para gerar um `.exe`, execute [build-windows.ps1](scripts/build-windows.ps1) num computador Windows.

## Garantias da V1

* Os ficheiros originais nunca são movidos, renomeados ou editados.
* `data/catalog.duckdb` contém apenas índice, conteúdo extraído e relações.
* A indexação é incremental por tamanho e data de modificação.
