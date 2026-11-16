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


## Revisão técnica (QA, 16/11)

> Revisão **somente leitura**. Nenhum comando do procedimento foi executado; os passos acima não foram alterados. Base: `phase0/rc` (`9e5aa81`) em `phase0/qa-backlog`.

### Tabela de itens

| # | Item verificado | Resultado | Evidência |
|---|---|---|---|
| 1.1 | Commits e branches citados existem (`phase0/rc`, `phase0/ui`, `phase0/integration`, `bf35530`, `79ded57`, `0eba842`, `e1f1c0b`, `2974e87`) | OK | `git rev-parse --verify` em todos |
| 1.2 | `backup/pre-fase0` ainda não existe (criada no 3.1) | OK | esperado |
| 1.3 | Arquivos e pastas citados existem em `phase0/rc` | OK | `git ls-tree` / `cat-file`: runbook, backlog, t02/t03, `security-policy.md`, `docs/decisions`, `docs/integrations`, `pytest.ini`, `tests/conftest.py`, `tests/test_t01_isolation.py`, `tests/test_v139_…`, `requirements-dev.txt`, `static/*`, `compose.yaml`, `iniciar_docker.sh`, `Dockerfile`, `.gitignore`, `.dockerignore` |
| 1.4 | Lista de worktrees da seção 0 | **PROBLEMA P6** | ver P6 |
| 2 | Sintaxe dos 8 blocos ```powershell (linhas 30, 41, 70, 77, 92, 100, 109, 119) | OK | `Parser::ParseInput`, 0 erros em todos. Feito in-process, não pela forma `powershell -Command`; resultado equivalente |
| 3.1 | Container parado antes de qualquer mudança em `.py` | OK | passo 2 antes do 4 |
| 3.2 | Backup antes de mover arquivos | OK no tempo; **ver P2 e P3** | 3.1 antes de 4.2 |
| 3.3 | Verificação antes e depois | OK | manifestos 3.1 a 3.3 e seção 6 |
| 3.4 | `git add -A`, `stash`, `reset --hard`, `clean`, `checkout -f`, `docker compose up/down/--build` só em frase de proibição | OK | busca por padrão; linhas 21, 22, 35, 119 |
| 3.5 | Nenhum comando destrutivo sem cópia prévia | **PROBLEMA P2** | `git checkout -- requirements-dev.txt` (4.2) depende do patch |
| 3.6 | Move só o que é não versionado | **PROBLEMA P1** | 4.2 manda mover `docs/` inteiro |
| 3.7 | Seção 10 coerente com o passo 4.3 | **PROBLEMA P5** | seção 10 cita `phase0/integration` |
| 4.1 | Comando `git diff --quiet $base -- …` existe e aponta `f154929` | OK | git 2.50.0; `rc..ui` = só `f154929` |
| 4.1b | Semântica do `git diff --quiet` | OK | testado no worktree: idêntico = 0, diferente = 1 |
| 4.1c | Afirmação "os três arquivos já estão copiados no backup do 3.1" | **PROBLEMA P3** | 3.1 copia só não versionados |
| 4.3 | "`phase0/ui` inclui rc" | **PROBLEMA P4** | ver P4 |
| 5 | Aceite: mesma lista de 33 falhas, 0 novas | OK no rc (no worktree) | rc: 276 passam / 33 falham; lista idêntica à do integration; violações = 0 |
| 0a | Serviço, porta, mounts, `--reload --reload-dir /app`, `CHECKFISCAL_DATA_DIR=/data`, sem política de restart, sem `USER` no Dockerfile (root) | OK | `compose.yaml`, `Dockerfile` (em `phase0/rc`) |
| 0b | Não versionados em `bf35530`: `docs/architecture`, `docs/decisions`, `docs/integrations`, `pytest.ini`, `tests/conftest.py`, `tests/test_t01_isolation.py`; versionados: `requirements-dev.txt`, `static/*`, `tests/test_v139_…` | OK | `git ls-tree bf35530` |
| 0c | Estado da pasta operacional (git status, branch, `docker compose ps -a`, `docker inspect`, hash e tamanho do banco, `pdfs/`, backup de 22/10) | **NÃO VERIFICADO** | ver "Não verificado" |

### PROBLEMAS

**P1 (alto), passo 4.2: mover `docs/` inteiro.** `bf35530` versiona 23 arquivos sob `docs/`, entre eles `docs/CHECKLIST_BETA_COMERCIAL.md`, `docs/POLITICA_LOCAL_DE_DADOS.md` e `docs/TERMO_BETA_COMERCIAL_MODELO.md`. Movê-los deixa deleções de arquivos versionados. **Correção sugerida:** mover só `docs/architecture`, `docs/decisions` e `docs/integrations`, que são os não versionados.

**P2 (médio), passo 3.1: patch como única cópia do `requirements-dev.txt`.** O 4.2 faz `git checkout -- requirements-dev.txt`, que descarta a alteração. A única cópia dela é `git diff > …patch`. Dois problemas: (a) neste ambiente o redirecionamento do PowerShell 5.1 gravou **UTF-8 com BOM** (`EF BB BF`); não testei se `git apply` aceita isso; (b) `git diff` não mostra mudanças já em stage. **Correção sugerida:** `git diff HEAD --output="$bk\fix-arquitetura-tracked.patch"` (grava bytes sem BOM) e conferir o arquivo antes do checkout.

**P3 (médio), passo 4.1: "os três arquivos já estão copiados no backup do passo 3.1" é falso.** O 3.1 copia só `git ls-files -o` (não versionados). Os três arquivos (`static/index.html`, `static/app.css`, `tests/test_v139_…`) são versionados em `bf35530`; neles só existe o diff do patch (ver P2). **Correção sugerida:** copiar esses três explicitamente para `$bk` antes de mover.

**P4 (médio), passo 4.3: `phase0/ui` não contém o commit `9e5aa81`.** `merge-base(rc, ui)` = `3b74dda`; `rc..ui` = só `f154929`. O conteúdo de código de `ui` é igual ao de `rc`; diferem só `docs/architecture/homologation-runbook.md` e os três arquivos de interface (`git diff --name-only`). O runbook dentro de `ui` **não tem a linha `git diff --quiet`** do passo 4.1 (ver `git show phase0/ui:docs/architecture/homologation-runbook.md`). Um ff para `ui` traz o runbook antigo e um histórico diferente do `rc`. O comentário "inclui rc" só vale para o código. **Correção sugerida:** escolher `rc` ou fazer `ui` absorver `rc` antes do ff, e ajustar o comentário.

**P5 (médio), seção 10: `git merge --ff-only phase0/integration`.** O passo 4.3 usa `phase0/ui` ou `phase0/rc`. `phase0/integration` é ancestral de ambos, mas a seção 10 não corresponde ao passo. **Correção sugerida:** trocar por `phase0/ui` ou `phase0/rc`, conforme a escolha do responsável.

**P6 (baixo), seção 0, "Worktrees".** A lista é `base, c5, t02, t03, integration`. Os worktrees reais são `base` (`phase0/base`), `c5` (`phase0/qa-backlog` nesta revisão), `integration` (`phase0/integration`), `rc` (`phase0/rc`), `t02` (`phase0/hardening`), `t03` (`phase0/def002`) e `ui` (`phase0/ui`). `rc` e `ui` faltam, e os nomes de `t02`/`t03` não batem com as branches. **Correção sugerida:** atualizar a lista. Não há dado nos worktrees (`checkfiscal_data/` e `*.db` ausentes em todos).

**P7 (baixo), seção 9: "o commit do frontend … continuam em `$bk`".** O commit fica em `phase0/ui` (f154929). `$bk` tem as cópias e o patch, não o commit. **Correção sugerida:** trocar o texto.

**P8 (a verificar), passo 4.2: deleções antes do ff.** Mover os três arquivos de interface (rastreados) deixa deleções no status. Não verifiquei se `git merge --ff-only` aceita isso. **Sugestão:** conferir `git status --short` antes do merge; o esperado é só `pdfs/` e as deleções movidas.

**P9 (a verificar), passo 3.3: sqlite com URI Windows.** `sqlite3.connect('file:'+caminho+'?mode=ro', uri=True)` com caminho `C:\…` não foi testado. Não rodei o comando do procedimento.

### Não verificado (exige autorização)

- **Estado de partida da pasta operacional (0c):** `git status`/`git branch` da pasta operacional, `docker compose ps -a`, `docker inspect` dos mounts, hash e tamanho do banco, `pdfs/`, backup de 22/10 e a afirmação "Verificado em 16/11: 0 para os três arquivos" do passo 4.1 (que depende do estado operacional). Não executei: as regras do papel proíbem comandos `docker` e a leitura da pasta operacional. Preciso de autorização explícita para leituras somente leitura.
- **Afirmação do passo 4.1 sobre `app.py`** ("1 para um arquivo que sabidamente difere"): não reproduzida, porque `app.py` não está entre os três arquivos do teste.
- **Equivalência da pasta operacional com `f154929`:** só é verificável na pasta operacional.

### Correções feitas nesta revisão

Nenhuma. Não encontrei erro de digitação óbvio. Os passos não foram alterados.
