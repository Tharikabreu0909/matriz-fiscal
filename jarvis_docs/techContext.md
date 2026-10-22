# Contexto técnico

## Stack verificada em `requirements.txt`

- Python. O inicializador 1.42 (nota, não o `.bat` atual) pretende aceitar 3.13, 3.12 ou 3.11 e recusar escolha automática de 3.15. O `.bat` em execução não aplica esse seletor: usa `python` do PATH e o venv local.
- FastAPI `0.116.1`
- Uvicorn `0.35.0` com extra `standard` no `requirements.txt`. A nota 1.42 diz que o extra foi removido para evitar compilar PyYAML; o arquivo de requisitos **ainda declara** `uvicorn[standard]==0.35.0`.
- `python-multipart==0.0.20` (upload de PDF)
- `pdfplumber==0.11.7`
- SQLite da biblioteca padrão
- Pytest `8.4.1` em `requirements-dev.txt`
- Interface: HTML e JavaScript em `static/index.html`, CSS em `static/app.css`, sem framework frontend. A rota `/` lê o HTML; `GET /static/app.css` entrega a folha com o mesmo `Cache-Control: no-store` da página.

## Como sobe

Windows, código atual:

1. `INICIAR_CHECKFISCAL_WINDOWS.bat`
2. Cria `.venv` se faltar e instala `requirements.txt` marcado por `.venv/.checkfiscal-deps-1.41`
3. Abre `http://127.0.0.1:8141`
4. `python -m uvicorn app:app --host 127.0.0.1 --port 8141 --no-access-log`

`desktop_launcher.py` abre a mesma URL e porta.

Docker (`compose.yaml`): serviço `checkfiscal`, bind `127.0.0.1:8145:8145`, `CHECKFISCAL_DATA_DIR=/data`, volume `./checkfiscal_data:/data` e o código em `/app`, reload com `WATCHFILES_FORCE_POLLING=true` porque volume Windows não dispara inotify. A porta do compose não é a porta do `.bat`.

## Dados locais

`services/runtime_paths.py`:

- `CHECKFISCAL_DATA_DIR` se existir.
- No Windows, sem essa variável: `%LOCALAPPDATA%\CheckFiscal` (fallback `%APPDATA%`).
- Fora do Windows: `checkfiscal_data/` na raiz do projeto.
- Banco: `CHECKFISCAL_DB_PATH` ou `checkfiscal.db` dentro do diretório de dados.
- Se o banco novo não existe e `checkfiscal_local.db` está na raiz, ele é copiado uma vez.
- Subpastas: `documents`, `backups`, `logs`, `support`.
- Log: `logs/checkfiscal.log`.

Não apagar essa pasta para “atualizar” a versão. O banco é o histórico do escritório.

## Consulta externa

Juros: API SGS do Banco Central, série **4390** (Selic mensal), em `services/legal_charges.py`. User-Agent ainda diz `CheckFiscal/1.11`. Sem internet, o cálculo de juros falha com erro explícito; o restante do fluxo é local.

## Context7

Consulta feita em 22/10/2026 pelo MCP `user-context7` (`query-docs`). O servidor não expôs `resolve-library-id`. `/fastapi/fastapi` redirecionou para `/websites/fastapi_tiangolo`.

O que a documentação atual confirma e o projeto já segue:

- FastAPI recebe PDF com `UploadFile` / `File()`. Vários arquivos no mesmo campo usam `list[UploadFile]`. Em endpoint síncrono (`def`), o arquivo bruto é `upload.file`.
- Arquivos estáticos se publicam com `StaticFiles`. A UI deste projeto é servida pela rota `/` a partir de `static/index.html`.
- pdfplumber abre com `with pdfplumber.open(caminho) as pdf`. Texto: `page.extract_text()`. Tabelas: `page.extract_tables()` (lista de tabelas, cada uma lista de linhas, cada linha lista de células) ou `extract_table()` para a maior tabela. `close()` libera páginas e o arquivo; o `with` já faz isso. Há parâmetros opcionais `password`, `laparams`, `unicode_norm` e `strict_metadata`.

`readers/malha_reader.py` usa esse contrato: `extract_text` para CFDF e razão social, `extract_tables` até achar o cabeçalho com “Tipo de Divergência”, “Referência”, “Informado” e “Divergência”.

## Restrições

- Sem autenticação, sem multiusuário e sem sincronização.
- Leitores cobrem os padrões de PDF já validados em `docs/validacao-leitor-pgdas-v2.json` e nos testes. PDF fora do padrão quebra a leitura em vez de inventar campo.
- Declaração PGDAS não traz o quadro de DAS. Vencimento para multa/juros cai na regra do dia 20, com aviso de conferência.
- Executável Windows, quando existir, precisa ser compilado e assinado fora deste fluxo.
- Não há cobertura de CBS/IBS nem de PGDAS da transição a partir de 2027.
- Não gravar segredo de MCP, chave ou dado fiscal de cliente dentro de `jarvis_docs/`.

## Testes

Pytest na pasta `tests/`. Há testes de planejador, leitor, motor, segregação, encargos, jornada, backup e versões. Os arquivos `test_v144_missing_pgdas.py` e `test_v145_last_declared_cutoff.py` descrevem API que o código de produção ainda não tem; não usá-los como prova de que a 1.44/1.45 está pronta.
