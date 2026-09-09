# File Index V2

O File Index é uma interface local para navegar, pesquisar e pré-visualizar os seus ficheiros sem os mover, renomear ou copiar. Os documentos continuam nas pastas normais; o catálogo local guarda apenas metadados, conteúdo extraído, tags, coleções e relações.

## O que a V2 inclui

* Explorador de três painéis: pastas, lista/grelha e preview.
* Navegação por breadcrumbs, voltar, subir um nível, recentes e pesquisa global (`Ctrl+K`).
* Preview de PDF renderizado, imagens, Word/texto e tabelas Excel/CSV.
* Tags, relações e coleções sem alterar os ficheiros de origem.
* Indexação incremental com percentagem, erros visíveis, exclusões configuráveis e deteção de ficheiros removidos.
* Monitorização opcional das pastas configuradas com `watchdog`.
* Grafo estrutural com pastas como âncoras e ficheiros como nós físicos.

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

## Criar um executável `.exe` da V2

No PowerShell, execute:

```powershell
.\scripts\build-windows.ps1
```

O ficheiro gerado ficará em `dist/FileIndexV2.exe`. Reconstrua o `.exe` depois de atualizar o repositório: um executável antigo não recebe mudanças através de `git pull`.

## Garantias da V1

* Os ficheiros originais nunca são movidos, renomeados ou editados.
* `data/catalog.duckdb` contém apenas índice, conteúdo extraído e relações. No executável, ele fica em `%LOCALAPPDATA%\LocalKnowledgeExplorer`.
* A indexação é incremental por tamanho e data de modificação.
* A exclusão de uma pasta do catálogo não elimina os ficheiros do disco.
