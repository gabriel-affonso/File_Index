# Local Knowledge Explorer

Explorador local de conhecimento para Windows: indexa ficheiros sem os mover, pesquisa conteúdo e metadados, pré-visualiza documentos/datasets e cria relações manuais. A interface abre localmente no navegador, sem cloud ou servidor externo.

## Instalação no Windows

Pré-requisito: instale o **Python 3.11** e marque a opção “Add Python to PATH” durante a instalação.

Abra o PowerShell na pasta do projeto e instale as dependências uma única vez:

```powershell
py -3.11 -m pip install --user -r requirements.txt
```

Não é necessário criar nem ativar um ambiente virtual.

## Executar

```powershell
py -3.11 -m app.windows_launcher
```

A aplicação abre automaticamente no browser. Mantenha a janela do PowerShell aberta enquanto utiliza o programa; pressione `Ctrl+C` para o encerrar.

## Atalho global

No Windows, `Ctrl + Shift + Espaço` abre a aplicação a partir de qualquer programa enquanto o `windows_launcher` estiver em execução.

## Criar um executável `.exe`

No PowerShell, execute:

```powershell
.\scripts\build-windows.ps1
```

O ficheiro gerado ficará na pasta `dist`.

## Garantias da V1

* Os ficheiros originais nunca são movidos, renomeados ou editados.
* `data/catalog.duckdb` contém apenas índice, conteúdo extraído e relações.
* A indexação é incremental por tamanho e data de modificação.
