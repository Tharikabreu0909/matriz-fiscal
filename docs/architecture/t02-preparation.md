# Preparação segura da T02: contenção do Docker e testes de aceitação

> 22/10/2026. Diagnóstico **somente leitura**. Nenhum serviço foi reiniciado, parado ou recriado; nenhum volume foi alterado.
> Todas as sondas rodaram em bancos temporários do scratchpad.

## 1. Diagnóstico da execução Docker

| Item | Valor observado | Fonte |
|---|---|---|
| Serviço ativo | `checkfiscal-pipeline-malha-pgdas-v145-checkfiscal-1` (único do CheckFiscal), *Up* ~2 h | `docker compose ps` |
| Porta | `127.0.0.1:8145 → 8145` | idem |
| Comando | `uvicorn app:app --host 0.0.0.0 --port 8145 --no-access-log --reload --reload-dir /app` | `docker inspect` |
| Usuário | root (`User` vazio) | idem |
| Restart policy | `no` | idem |
| Variáveis | `CHECKFISCAL_DATA_DIR=/data`, `WATCHFILES_FORCE_POLLING=true` | idem |
| Mount 1 | **bind** `…\checkfiscal-pipeline-malha-pgdas-v1.45` → `/app` (rw) | idem |
| Mount 2 | **bind** `…\checkfiscal_data` → `/data` (rw) | idem |
| Volumes nomeados | nenhum do CheckFiscal | `docker volume ls` |
| Dados persistentes | `checkfiscal_data/checkfiscal.db` (626.688 bytes), `documents/`, `backups/`, `logs/` | `ls` (sem ler conteúdo) |
| Reloads desde o início | **37**, disparados por `.py` em `app.py`, `services/`, `tests/` e **`.venv/`** | `docker compose logs` |
| Código executado | **a árvore de trabalho atual** (branch `fix/arquitetura`, com alterações não commitadas) | mount 1 |
| App nativa (`%LOCALAPPDATA%`) | parada (nada em 8141) | `netstat` |

O conteúdo de `checkfiscal_data/` não foi aberto nesta análise. **Ele é tratado como dado real de cliente** (o commit `fe0679b` se chama "dados reais"). Confirme se é esse o caso.

### `init_db()` não é somente leitura

Medido em banco temporário (`scratchpad/t02prep/initdb`):

| Execução | `change_counter` (cabeçalho, offset 24) | `user_version` | SHA-256 | Conteúdo |
|---|---|---|---|---|
| import + 1 empresa | 2 | 2 | `65ae0042…` | 1 empresa |
| `init_db()` #2 | **3** | 2 | `d7d548ce…` | igual |
| `init_db()` #3 | **4** | 2 | `005bffcd…` | igual |
| banco com `user_version = 3` + `init_db()` | — | **3 → 2** | — | — |

Conclusões:

1. Cada inicialização (`database.py:1330` executa `init_db()` **no import**) faz uma transação de escrita: `CREATE TABLE IF NOT EXISTS`, `INSERT OR IGNORE INTO schema_migrations` e `PRAGMA user_version = 2`. O conteúdo de negócio não muda, mas o arquivo muda (cabeçalho, hash, mtime, checkpoint do WAL).
2. **`PRAGMA user_version = 2` incondicional rebaixa a versão do esquema.** Se uma versão futura migrar o banco para 3, qualquer execução do código atual sobre esse banco (reload, `.bat` antigo, executável antigo) o marca de volta como 2, e a próxima migração pode ser reaplicada ou pulada. **É um risco de integridade, não só de "toque" no arquivo.** Proposta registrada como DEF-002.

## 2. Riscos identificados

| ID | Risco | Gatilho | Gravidade |
|---|---|---|---|
| R-D1 | Toda edição de `.py` no repositório reinicia o container e grava no banco real (DEF-002) | `--reload --reload-dir /app` + bind `.:/app` + `WATCHFILES_FORCE_POLLING` | **Alta** durante a Fase 0 |
| R-D2 | **O código em desenvolvimento roda sobre dados reais imediatamente**, sem revisão nem commit. Na T02 (middleware em `app.py`), cada versão intermediária atenderia a interface real | mount `.:/app` | **Alta** |
| R-D3 | `pip install` no `.venv` (dentro de `/app`) dispara reload | `.venv` dentro do repositório | Média |
| R-D4 | Rebaixamento de `user_version` | `init_db()` | Alta (quando houver migrações) |
| R-D5 | Container como root com escrita no repositório | `User` vazio, mount rw | Média |
| R-D6 | `iniciar_docker.sh` usa `docker compose up --build` (reconstrói e recria) e anuncia "1.45" | script | Média |
| R-D7 | A própria preparação da T01 disparou 4 reloads (criação/edição de `tests/conftest.py` e `tests/test_t01_isolation.py`). Os testes nunca acessaram o banco (0 violações), mas **o container sim**, via `init_db()` | edição de `.py` | Registrado |
| R-D8 | `restore_backup` no Linux (container): apagar `-wal`/`-shm` com conexões abertas **não falha** como no Windows; conexões remanescentes podem continuar escrevendo num WAL desvinculado, com risco de perda ou inconsistência após a restauração (DEF-001) | DEF-001 | Alta |

### Configurações que podem gravar no banco real durante um reload

1. `command: … --reload --reload-dir /app` (`compose.yaml`): observa todo `*.py` sob `/app`, incluindo `tests/` e `.venv/`.
2. `volumes: - .:/app` (`compose.yaml`): edições do host chegam na hora.
3. `volumes: - ./checkfiscal_data:/data` + `CHECKFISCAL_DATA_DIR: /data`: o banco do reload é o real.
4. `WATCHFILES_FORCE_POLLING: "true"`: garante a detecção de toda mudança no Windows.
5. `database.py:1330`, `init_db()` no import: escrita e `user_version = 2`.
6. `services/runtime_paths.py:24–55` no import: `mkdir` dos diretórios. A cópia do banco legado `/app/checkfiscal_local.db` → `/data/checkfiscal.db` ocorre se o banco de `/data` não existir (hoje não dispara).
7. `services/app_logging.py`: `RotatingFileHandler` abre `/data/logs/checkfiscal.log` no import.
8. Encerramento gracioso a cada reload: checkpoint do WAL no arquivo `.db`.
9. GETs com escrita (`/api/process/{id}`, `/api/companies/{id}`, `/api/client-report`) se a interface aberta for recarregada pelo usuário após o reload. Não há polling automático; o único `setTimeout` (`index.html:1426`) recarrega a página após uma restauração.

## 3. Separação proposta: operação, desenvolvimento e teste

Compatibilidade preservada: **`compose.yaml` e os lançadores atuais não são alterados nesta etapa.**

| Ambiente | Como roda | Dados | Reload | Código |
|---|---|---|---|---|
| **Operação do cliente** | `.bat` / executável (Windows) ou, se o canal Docker for mantido, imagem **sem** mount de código e sem `--reload` (`Dockerfile` CMD atual) | `%LOCALAPPDATA%\CheckFiscal` ou volume de dados | Nunca | Versão empacotada e com tag |
| **Desenvolvimento** | `compose.dev.yaml` (novo, proposto abaixo), **projeto e porta distintos** | **Fictícios**, em volume próprio `checkfiscal-dev-data`, ou `tmpfs` | Sim, restrito ao código-fonte | Árvore de trabalho |
| **Teste** | `pytest` local com `tests/conftest.py` (T01) | Diretório temporário por sessão | — | Árvore de trabalho |

### `compose.dev.yaml` proposto (não criado)

```yaml
# Desenvolvimento com dados fictícios. Não substitui compose.yaml.
# Uso: docker compose -f compose.dev.yaml up --build
name: checkfiscal-dev            # projeto distinto: não toca o container operacional
services:
  checkfiscal-dev:
    build: .
    ports:
      - "127.0.0.1:8146:8146"    # porta distinta da operação (8145)
    environment:
      CHECKFISCAL_DATA_DIR: /data-dev
      WATCHFILES_FORCE_POLLING: "true"
    volumes:
      - ./app.py:/app/app.py:ro
      - ./database.py:/app/database.py:ro
      - ./readers:/app/readers:ro
      - ./services:/app/services:ro
      - ./static:/app/static:ro
      - checkfiscal-dev-data:/data-dev   # volume nomeado com dados fictícios
    command: >
      python -m uvicorn app:app --host 0.0.0.0 --port 8146 --no-access-log
      --reload --reload-dir /app/readers --reload-dir /app/services
      --reload-include app.py --reload-include database.py
volumes:
  checkfiscal-dev-data: {}
```

Propriedades:

- Código montado **somente leitura** e **sem** `tests/`, `.venv/` ou `checkfiscal_data/`; nenhum caminho real é visível dentro do container.
- O `name:` distinto impede que `up` ou `down` desse arquivo afetem o container operacional.
- Dados fictícios: um script de carga (`tools/seed_dev_data.py`, a criar) com empresas de CNPJ válido e fictício e PDFs sintéticos, nunca cópias de clientes.
- Validação antes do primeiro uso: `docker compose -f compose.dev.yaml config` e `docker inspect` dos mounts.

## 4. Estratégia de proteção dos dados

1. **Congelar o operacional:** parar o container antes de qualquer edição de `.py` (§5).
2. **Cópia fria:** com o container parado, copiar `checkfiscal_data/` para **fora** do repositório e registrar o SHA-256 de cada arquivo.
3. **Hash de referência:** guardar o SHA-256 de `checkfiscal_data/checkfiscal.db` após a parada; durante a T02 ele **não pode mudar**. Verificar antes e depois de cada sessão.
4. **Isolamento dos testes:** a T01 já bloqueia `checkfiscal_data/` dentro do pytest.
5. **Nenhum código em desenvolvimento sobre dados reais:** se o escritório precisar usar o Docker durante a Fase 0, subir a operação a partir de um **worktree** fixado no último commit estável, fora desta pasta, apontando para os dados. Nunca a partir da árvore de trabalho.

## 5. Plano de contenção antes da T02

**O Docker está em execução com dados que devem ser tratados como reais.** Comando seguro para interrompê-lo, **aguardando sua autorização**:

```powershell
cd C:\Users\Ismael\Desktop\checkfiscal-pipeline-malha-pgdas-v1.45
docker compose stop checkfiscal
```

- `stop` só encerra o processo: **não remove** o container, a imagem nem os bind mounts, e não toca em `checkfiscal_data/`. O encerramento gracioso fecha as conexões e faz o checkpoint do WAL (comportamento normal).
- **Não usar** `down -v` (destrutivo para volumes), `down` (remove o container), `up --build` (recria) nem `iniciar_docker.sh` (recria com o código atual).
- Para retomar depois, **sem rebuild**: `docker compose start checkfiscal`. Atenção: ele volta a executar a árvore de trabalho atual (R-D2).

Sequência, cada passo com autorização:

| Passo | Ação | Verificação |
|---|---|---|
| C1 | `docker compose stop checkfiscal` | `docker compose ps` mostra *exited*; `netstat` sem `:8145` |
| C2 | Cópia fria de `checkfiscal_data/` para fora do repositório + manifesto SHA-256 | Hashes da cópia iguais aos da origem |
| C3 | Registrar o hash de referência de `checkfiscal_data/checkfiscal.db` | Arquivo de referência no scratchpad |
| C4 | (Opcional) Criar `compose.dev.yaml` + carga fictícia; subir em 8146 | `docker inspect` sem mounts reais |
| C5 | Materializar os testes da §6 em `tests/test_t02_request_guard.py` (vermelhos antes da T02) | Os testes "bloquear" falham; os "permitir" passam |
| C6 | Rodar a suíte da T01 | 0 violações; hash C3 inalterado |

## 6. Testes de aceitação do middleware (T02)

Comportamento especificado:

- `Host` fora da lista → **400**.
- Requisição que altera estado (`POST`, `PUT`, `PATCH`, `DELETE`) **ou** GET com efeito colateral, com `Origin` fora da lista, `Origin: null`, ou `Sec-Fetch-Site` diferente de `same-origin`/`none` → **403** com `{"code": "CROSS_ORIGIN_BLOCKED"}`, **antes** do handler.
- Sem `Origin` e sem `Sec-Fetch-Site` (CLI, testes) → permitido.
- Lista de hosts e origens configurável (`CHECKFISCAL_ALLOWED_HOSTS`); padrão `127.0.0.1:<porta>`, `localhost:<porta>`, mais `testserver` nos testes.

`same-site` também é bloqueado: em `localhost`, outra porta (ex.: um servidor de desenvolvimento qualquer em `:3000`) é *same-site*, mas não *same-origin*.

Toda verificação de bloqueio confirma também **a ausência de efeito**: contagem de empresas, de eventos, de backups e de relatórios inalterada; o banco não foi substituído.

| # | Grupo | Requisição | Cabeçalhos | Esperado |
|---|---|---|---|---|
| A1 | Host | `GET /api/health` | `Host: evil.example` | 400 |
| A2 | Host | `GET /api/health` | `Host: 127.0.0.1:8141` | 200 |
| A3 | Host | `GET /api/health` | `Host: localhost:8145` | 200 (se 8145 configurada) |
| A4 | Host | `POST /api/system/restore` (multipart) | `Host: rebind.attacker.example`, sem Origin | 400; banco não substituído |
| B1 | Multipart | `POST /api/system/restore` | `Origin: https://evil.example` | 403; empresa-sentinela continua existindo |
| B2 | Multipart | `POST /api/analyze-malha?company_id=…` | `Origin: https://evil.example` | 403; nenhum processo criado |
| B3 | Multipart | `POST /api/upload-pgdas?process_id=…&competence=…` | `Sec-Fetch-Site: cross-site` | 403 |
| B4 | Multipart | `POST /api/upload-pgdas-auto?process_id=…` | `Origin: null` | 403 |
| C1 | URL | `POST /api/confirm-analysis?process_id=…&competence=…` | `Origin: https://evil.example` | 403; nenhuma confirmação gravada |
| C2 | URL | `POST /api/calculate-legal-charges?process_id=…&update_date=…` | `Sec-Fetch-Site: cross-site` | 403; nenhum cálculo gravado; nenhuma tentativa de rede |
| D1 | JSON sem `Content-Type` | `POST /api/companies` com `content=` bytes JSON | `Origin: https://evil.example` | 403; **0 empresas** (hoje: 201) |
| D2 | JSON sem `Content-Type` | `POST /api/calculate-tax` | `Sec-Fetch-Site: cross-site` | 403 |
| D3 | JSON | `PATCH /api/companies/{id}`, `DELETE /api/companies/{id}` | `Origin: https://evil.example` | 403 (defesa em profundidade) |
| E1 | GET com efeito | `GET /api/system/backup` | `Sec-Fetch-Site: cross-site` | 403; **0 arquivos** em `backups/` |
| E2 | GET com efeito | `GET /api/system/support-bundle` | `Sec-Fetch-Site: cross-site` | 403; 0 arquivos em `support/` |
| E3 | GET com efeito | `GET /api/client-report?process_id=…` | `Sec-Fetch-Site: same-site` | 403; 0 relatórios; 0 eventos |
| E4 | GET com efeito | `GET /api/process/{id}`, `GET /api/companies/{id}` | `Sec-Fetch-Site: cross-site` | 403; `updated_at` inalterado |
| F1 | Permitido | Todas as rotas acima | `Origin: http://127.0.0.1:8141`, `Sec-Fetch-Site: same-origin` | Chega ao handler (status do próprio handler) |
| F2 | Permitido | `POST /api/companies` | sem Origin, sem Sec-Fetch-Site | 201 |
| F3 | Permitido | `GET /api/system/backup` | `Sec-Fetch-Site: none` (digitado na barra) | 200 |
| F4 | Permitido | `GET /api/health`, `GET /`, `GET /static/app.css` | `Sec-Fetch-Site: cross-site` | 200 (somente leitura, sem dados) |
| F5 | Restauração permitida | `POST /api/system/restore` com ZIP inválido | same-origin | **422** (chegou ao handler sem apagar nada; evita o DEF-001) |
| G1 | Redirecionamento | `POST /api/system/restore/` (barra final) | `Origin: https://evil.example` | 403, **não** 307 |
| G2 | Preflight | `OPTIONS /api/companies` | `Origin`, `Access-Control-Request-Method: POST` | Sem `Access-Control-Allow-Origin` na resposta |
| G3 | Método | `HEAD /api/system/backup` | — | 405 (não cria backup) |
| H1 | Chave de suporte | B1 com `CHECKFISCAL_ORIGIN_CHECK=0` | — | Passa (documentado só para suporte) |
| H2 | Interface | Varredura de `static/index.html` | — | Toda chamada `fetch`/`location.href`/`window.open` usa caminho relativo `/api/...` (a UI continua same-origin) |
| H3 | Log | Bloqueio registrado | — | Linha de log com método, rota e motivo, **sem** query string nem corpo |

Os testes "bloquear" ficam marcados `xfail(strict=True)` até a T02; os "permitir" já passam hoje e não podem regredir.

## 7. Defeitos registrados separadamente

### DEF-001: conexões SQLite fechadas só pelo coletor de lixo; restauração falha (Windows) ou fica insegura (Linux)

- **Evidência:** `test_commercial_hardening.py::test_backup_and_restore_preserve_database_and_documents` falha com `PermissionError [WinError 32]` ao apagar `checkfiscal.db-wal` (`backup_service.py:122`). Sonda isolada: 2 objetos `sqlite3.Connection` vivos; a restauração só funciona após `gc.collect()`, que deixa 1.
- **Causa:** `database.connect()` é usado como `with connect() as connection:`. O gerenciador de contexto do `sqlite3.Connection` faz **commit/rollback, mas não fecha**. O fechamento depende do coletor, e ciclos de referência atrasam esse fechamento.
- **Efeito:** no Windows, a restauração com o servidor ativo falha com 500. No Linux/Docker, `unlink` do `-wal` com conexões abertas é permitido: conexões remanescentes podem escrever num WAL órfão, e há risco de perda ou corrupção após a restauração.
- **Correção proposta (T03):** `connect()` como `contextmanager` que fecha sempre (`try/finally: connection.close()`); restauração em modo manutenção (bloqueia novas requisições, aguarda as conexões em uso, troca o arquivo, reabre); não apagar `-wal`/`-shm` com conexões abertas; checkpoint explícito antes do backup.
- **Paliativo atual:** `gc.collect()` em `tests/test_t01_isolation.py` (canário), apenas para testar o destino da restauração. **Não é solução**: remover quando o DEF-001 for corrigido.

### DEF-002: `init_db()` grava a cada import e rebaixa `user_version`

- **Evidência:** §1 (contador 2 → 3 → 4; `user_version` 3 → 2).
- **Correção proposta (Fase 0, junto da T13, ou Fase 1):** `init_db()` explícito no startup (não no import); `user_version` só é **elevado**, nunca rebaixado; abortar com mensagem clara se o banco for mais novo que o código.

## 8. Critérios objetivos para autorizar a T02

1. `docker compose ps` mostra o serviço `checkfiscal` **parado**, ou existe evidência de que nenhum container monta este repositório **e** `checkfiscal_data/` ao mesmo tempo.
2. Cópia fria de `checkfiscal_data/` fora do repositório, com manifesto SHA-256 conferido.
3. Hash de referência de `checkfiscal_data/checkfiscal.db` registrado (C3).
4. Suíte da T01: 0 violações, 0 arquivos reais alterados, mesmos 141/33/1.
5. Testes da §6 materializados: "bloquear" vermelhos (xfail estrito), "permitir" verdes.
6. Decisões tomadas: portas e hosts permitidos (8141 e/ou 8145); política para GET somente leitura vindo de outro site (proposta: permitido, F4).
7. DEF-001 e DEF-002 registrados (este documento) e fora do escopo da T02.
8. Autorização explícita sua para a T02.
