# Procedimento de homologação e integração da Fase 0 (C5 + T02 + T03 + DEF-002 + hardening)

> **Rascunho de 16/11/2026. NADA aqui foi executado.** Todo passo marcado 🔒 exige autorização explícita do responsável.
> O backup de 22/10/2026 **não** é atual (banco daquela data: `ba6a734a…`, 626.688 bytes; banco de hoje: 671.744 bytes, alterado em 15/11). Nunca o use como substituto dos dados atuais.

## 0. Estado de partida (lido em 16/11, somente leitura)

| Item | Valor |
|---|---|
| Branch operacional | `fix/arquitetura` @ `bf35530` (ancestral de `phase0/integration`) |
| Docker | `checkfiscal-…-checkfiscal-1`, *running*, `127.0.0.1:8145`, `--reload --reload-dir /app`, `Restart=no`, usuário root |
| Mounts (bind, rw) | `<repo>` → `/app` · `<repo>\checkfiscal_data` → `/data` · `CHECKFISCAL_DATA_DIR=/data` · nenhum volume nomeado |
| Banco do Docker | `checkfiscal_data\checkfiscal.db`, 671.744 bytes, mod. 15/11 16:31 |
| Banco nativo | `%LOCALAPPDATA%\CheckFiscal\checkfiscal.db`, 106.496 bytes (app nativa parada; arquivo tocado em 15/11 16:37 por um teste manual de interface com `init_db()`, sem dado de negócio) |
| Worktrees | `base`, `c5`, `t02`, `t03`, `integration` em `C:\Users\Ismael\CheckFiscal-floors\`; nenhum contém `checkfiscal_data/`, nenhum `.db`, nenhum link |
| Sem commit (tracked) | `static/index.html`, `static/app.css`, `tests/test_v139_ui_and_pgdas_plan.py`, `requirements-dev.txt` |
| Sem commit (untracked) | `docs/architecture/`, `docs/decisions/`, `docs/integrations/`, `pytest.ini`, `tests/conftest.py`, `tests/test_t01_isolation.py`, **`pdfs/`** |
| `pdfs/` | 7 PDFs, não ignorada pelo `.gitignore` nem pelo `.dockerignore`, dentro do mount `/app` |

## 1. Regras que valem para todo o procedimento
1. **Nunca** `git add -A` / `git add .` / `git commit -a`: a pasta `pdfs/` seria versionada. Sempre `git add` por caminho.
2. **Nunca** `git stash`, `git reset --hard`, `git clean`, `checkout -f`.
3. Nenhum `.py` muda enquanto o container estiver rodando: `--reload` reinicia o servidor e `init_db()` roda sobre o banco real. **Parar o container antes de tocar no código.**
4. Nenhum comando abaixo abre ou lê os PDFs da pasta `pdfs/`.

## 2. Janela controlada de parada 🔒
Anuncie a janela ao escritório (o serviço fica fora do ar; estimativa 10–20 min).

```powershell
cd C:\Users\Ismael\Desktop\checkfiscal-pipeline-malha-pgdas-v1.45
docker compose stop checkfiscal        # 🔒 encerramento gracioso: fecha conexões e faz checkpoint do WAL
docker compose ps -a                   # esperado: exited
netstat -ano | findstr :8145           # esperado: vazio
```
Não use `down`, `down -v`, `up`, `up --build` nem `iniciar_docker.sh` (recriam o container).

## 3. Backup atualizado e verificável 🔒
Cópia **fria** (container parado). Fora do repositório e fora de qualquer pasta montada.

```powershell
$ts  = Get-Date -Format "yyyyMMdd-HHmmss"
$src = "C:\Users\Ismael\Desktop\checkfiscal-pipeline-malha-pgdas-v1.45\checkfiscal_data"
$bk  = "C:\Users\Ismael\CheckFiscal-backups\docker-checkfiscal_data-$ts"
New-Item -ItemType Directory -Path $bk | Out-Null

# 3.1 manifesto da ORIGEM (antes)
Get-ChildItem $src -Recurse -File | Get-FileHash -Algorithm SHA256 |
  Select-Object @{n='rel';e={$_.Path.Substring($src.Length+1)}},Hash | Sort-Object rel |
  Export-Csv "$bk\MANIFEST-origem-antes.csv" -NoTypeInformation

# 3.2 cópia
robocopy $src "$bk\checkfiscal_data" /E /COPY:DAT /DCOPY:DAT /R:1 /W:1 /NP /LOG:"$bk\robocopy.log"
# código de saída do robocopy < 8 = sucesso

# 3.3 manifesto da CÓPIA e da ORIGEM (depois); os três devem ser idênticos
$dst = "$bk\checkfiscal_data"
Get-ChildItem $dst -Recurse -File | Get-FileHash -Algorithm SHA256 |
  Select-Object @{n='rel';e={$_.Path.Substring($dst.Length+1)}},Hash | Sort-Object rel |
  Export-Csv "$bk\MANIFEST-copia.csv" -NoTypeInformation
Get-ChildItem $src -Recurse -File | Get-FileHash -Algorithm SHA256 |
  Select-Object @{n='rel';e={$_.Path.Substring($src.Length+1)}},Hash | Sort-Object rel |
  Export-Csv "$bk\MANIFEST-origem-depois.csv" -NoTypeInformation
Compare-Object (Get-Content "$bk\MANIFEST-origem-antes.csv") (Get-Content "$bk\MANIFEST-copia.csv")        # esperado: vazio
Compare-Object (Get-Content "$bk\MANIFEST-origem-antes.csv") (Get-Content "$bk\MANIFEST-origem-depois.csv") # esperado: vazio
```

Verificação de integridade **da cópia** (nunca do banco vivo), em modo somente leitura:

```powershell
$py = "C:\Users\Ismael\Desktop\checkfiscal-pipeline-malha-pgdas-v1.45\.venv\Scripts\python.exe"
& $py -I -c "import sqlite3,sys; c=sqlite3.connect('file:'+sys.argv[1]+'?mode=ro',uri=True); print('integrity=',c.execute('pragma integrity_check').fetchone()[0],'| user_version=',c.execute('pragma user_version').fetchone()[0],'| empresas=',c.execute('select count(*) from companies').fetchone()[0],'| processos=',c.execute('select count(*) from processes').fetchone()[0])" "$bk\checkfiscal_data\checkfiscal.db" | Tee-Object "$bk\VERIFICACAO-INTEGRIDADE.txt"
```
Aceite do backup: manifestos idênticos, `integrity= ok`, `user_version= 2`, contagens registradas (são a referência "antes" do passo 8), e `documents\` com a mesma contagem de arquivos da origem.

### 3.1 Preservar as alterações não commitadas (sem stash)
```powershell
cd C:\Users\Ismael\Desktop\checkfiscal-pipeline-malha-pgdas-v1.45
git diff > "$bk\fix-arquitetura-tracked.patch"
$u = "$bk\untracked-sem-pdfs"; New-Item -ItemType Directory $u | Out-Null
git ls-files -o --exclude-standard | Where-Object { $_ -notlike 'pdfs/*' } | ForEach-Object {
  $d = Join-Path $u (Split-Path $_ -Parent); New-Item -ItemType Directory $d -Force | Out-Null; Copy-Item $_ (Join-Path $u $_) }
git rev-parse HEAD > "$bk\HEAD-antes.txt"
git branch backup/pre-fase0 bf35530     # 🔒 ponteiro de segurança (não altera arquivos)
```
`pdfs/` não é copiada nem lida: continua exatamente onde está. Se quiser uma cópia, ela é decisão sua.

## 4. Integração sem perder o frontend 🔒
O frontend sem commit (`static/index.html`, `static/app.css`, `tests/test_v139_ui_and_pgdas_plan.py`) **não** é commitado na pasta operacional: um commit ali geraria conflito certo com a branch `phase0/ui` (mesmo arquivo, mesma base, conteúdo diferente). Em vez disso:

1. **Provar que a pasta operacional ainda tem o mesmo frontend** que serviu de ponto de partida da `phase0/ui` (o primeiro commit dela, o "baseline"). Use o próprio Git, que já normaliza o fim de linha do Windows (comparar hash de arquivo cru dá falso "diferente" por causa do `autocrlf`):
   ```powershell
   $base = git log --reverse --format=%h phase0/rc..phase0/ui | Select-Object -First 1
   git diff --quiet $base -- static/index.html static/app.css tests/test_v139_ui_and_pgdas_plan.py
   $LASTEXITCODE        # 0 = idênticos ao baseline; 1 = alguém editou depois
   ```
   Se der 1, **pare**: trate a diferença antes de seguir (`git diff $base -- <arquivo>` mostra o que mudou). Verificado em 16/11 somente leitura: 0 para os três arquivos e 1 para um arquivo que sabidamente difere (`app.py`), ou seja, o teste detecta diferença. Os três arquivos já estão copiados no backup do passo 3.1.
2. **Liberar o caminho do fast-forward sem descartar nada** 🔒: mover (não apagar) para `$bk\movidos\` os três arquivos de interface, `docs/`, `pytest.ini`, `tests/conftest.py`, `tests/test_t01_isolation.py`; depois `git checkout -- requirements-dev.txt` (a alteração `httpx` vem na branch).
3. **Integrar** (container ainda parado):
   ```powershell
   git merge --ff-only phase0/ui        # 🔒 inclui rc (C5+T02+T03+DEF-002+hardening+docs) e a interface
   ```
   Se o responsável quiser liberar o backend sem a interface nova, use `git merge --ff-only phase0/rc`: a branch `rc` não toca em `static/*`, então o frontend sem commit continua intacto na pasta (o passo 2 então move só `docs/`, `pytest.ini`, `tests/conftest.py`, `tests/test_t01_isolation.py` e restaura `requirements-dev.txt`).
   Se não for fast-forward, **pare**: não resolva conflito às pressas; reporte.
4. Commit próprio 🔒 adicionando `pdfs/` ao `.gitignore`, antes de qualquer outro `git add` amplo.

## 5. Testes de compatibilidade (ainda com o container parado)
Somente dados temporários (o `tests/conftest.py` define `CHECKFISCAL_DATA_DIR`/`CHECKFISCAL_DB_PATH` em diretório temporário e bloqueia o acesso ao `checkfiscal_data/` real).
```powershell
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --ignore=tests/test_v145_last_declared_cutoff.py
```
Aceite: **mesma lista de 33 falhas pré-existentes** (ver `preexisting-failures-backlog.md`), 0 novas; `Tentativas de acesso a dados reais (violações): 0`.

## 6. Verificação **antes** da retomada (banco ainda sem uso)
- Hash do `checkfiscal.db` e de `-wal`/`-shm` iguais aos do manifesto do passo 3 (o código novo não pode ter tocado no banco durante os testes).
- `git status` limpo (exceto `pdfs/`) e `git log -3` com os commits esperados.

## 7. Retomada segura do serviço 🔒
```powershell
docker compose start checkfiscal      # 🔒 usa a imagem existente; NÃO usar up/--build
docker compose logs --tail 80 checkfiscal
```
Critérios para considerar a retomada segura (todos):
1. `GET http://127.0.0.1:8145/api/health` → 200; `GET /api/system/status` → `integrity: ok`, `user_version: 2`, contagens de empresas e processos **iguais** às do passo 3.
2. Interface abre, lista as empresas e abre uma empresa existente (somente leitura; não enviar documento).
3. Sondas do guard: `Host: evil.com` → 400; `POST /api/companies` com `Origin: https://evil.example` → 403; `GET /api/health` com `Sec-Fetch-Site: cross-site` → 200.
4. Log sem `Traceback`, sem `DatabaseSchemaTooNewError` e **sem laço de reload** (mais de uma reinicialização em 2 min = parar e investigar).

## 8. Verificação **depois** (24 h de observação)
Repita o item 1 do passo 7 após um dia de uso e compare a contagem com o esperado pela operação do dia (novas empresas/processos entram; nada some).

## 9. Rollback 🔒
**Gatilhos:** `integrity != ok`; contagem menor que a do backup sem explicação; erro de inicialização; laço de reload; guard bloqueando acesso legítimo.
- **Só código** (dados íntegros): `docker compose stop checkfiscal`; `git switch -C fix/arquitetura backup/pre-fase0` (volta a branch ao ponto de segurança; o commit do frontend e os arquivos movidos continuam em `$bk`); `docker compose start checkfiscal`. A imagem não muda, então não há rebuild.
- **Dados** (banco inconsistente): `docker compose stop checkfiscal`; renomear (não apagar) `checkfiscal_data` para `checkfiscal_data.quebrado-<ts>`; `robocopy "$bk\checkfiscal_data" "<repo>\checkfiscal_data" /E /COPY:DAT`; repetir o manifesto e a verificação de integridade do passo 3; `docker compose start checkfiscal`. O banco quebrado fica preservado para análise.
- Dados criados **depois** do backup só voltam se o banco quebrado ainda estiver legível (não os descarte).

## 10. Comandos que exigem autorização operacional (resumo)
`docker compose stop|start checkfiscal` · cópia fria e manifestos (leem a pasta operacional) · `git branch backup/pre-fase0` · mover arquivos sem commit para o backup · `git checkout -- requirements-dev.txt` · `git merge --ff-only phase0/integration` · commit do `.gitignore` · qualquer rollback do passo 9.

## 11. Riscos conhecidos
- O container roda como root com escrita em `/app`: o código que ele executa é a árvore de trabalho; qualquer edição de `.py` com ele ligado reinicia o servidor.
- O código antigo que está rodando hoje **não** tem a proteção do DEF-002 (ela só vale para as versões novas): só a partir da integração um banco de versão superior deixa de ser rebaixado.
- Backup restaurado de versão de esquema **menor** fica no esquema antigo até a próxima inicialização (risco residual do DEF-002).
- Trava de restore vale por processo; WebSocket não é checado; `https` bloqueado como `Origin`.
