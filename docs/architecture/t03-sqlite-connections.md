# T03 — Conexões SQLite e restauração segura (DEF-001)

> Correção do DEF-001 descrito em [t02-preparation.md](t02-preparation.md) (§7). Plano: [phase-0-plan.md](phase-0-plan.md).
> Commit: `048aef5`, em `phase0/c5` e `phase0/integration` (via `0722144`).

## Problema

`with connect() as connection:` fazia commit/rollback mas não fechava a conexão. O fechamento dependia do coletor de lixo. No Windows, o `-wal` ficava preso e a restauração falhava. No Linux, conexões remanescentes podiam escrever num WAL apagado.

## O que mudou

- `database.connect()` é um `contextmanager` que sempre fecha (`commit`/`rollback` e `close`).
- `DatabaseBusyError` e `exclusive_access()`, com contador de conexões abertas.
- Backup faz checkpoint do WAL antes de copiar.
- Restauração:
  - valida o zip e roda `integrity_check` antes de tocar em qualquer arquivo;
  - trava contra restauração concorrente;
  - cria cópia de segurança;
  - em caso de falha, reverte o banco e os documentos;
  - roda `integrity_check` após a troca;
  - apaga `-wal`/`-shm` só sem conexão aberta.
- Rota de restauração roda em `run_in_threadpool` e responde **409** quando o banco está ocupado.
- Testes: `tests/test_t03_connections_restore.py`. `test_backup_and_restore_preserve_database_and_documents` passou a **passar**. `gc.collect()` removido do canário em `tests/test_t01_isolation.py`.

**Divergência do plano:** §4 previa `restart_required`. Implementado: 409 com a restauração ocupada.

## Residuais

- Trava por processo, não multi-processo.
- Documentos trocados por `rename`, com pastas `.new` e `.old`.
- DEF-002: tratado, ver seção abaixo.

## Como reverter

`git revert 048aef5`. Isso reabre o DEF-001: o teste de restauração volta a falhar no Windows e o canário volta a depender de `gc.collect()`. Sem migração de banco.

## DEF-002 (init_db / `PRAGMA user_version`)

**Regra de classificação** (`init_db()`, antes de qualquer escrita, sem `connect()`): `read_user_version()` lê o cabeçalho do arquivo (bytes 60-63; com `-wal` pendente, usa SQLite `mode=ro`).
- Inexistente/vazio ou versão 0 → cria o esquema e grava `SCHEMA_VERSION` (2).
- `0 <= versão < 2` → migrações aditivas de sempre; só **eleva** `user_version` (escrita condicional em `_run_migrations`).
- `versão == 2` → `init_db()` retorna sem abrir transação (arquivo idêntico em hash).
- `versão > 2` → `DatabaseSchemaTooNewError`; nada é escrito (sem `-wal`/`-shm`, bytes idênticos).
- Restore (`backup_service`): backup com `user_version > SCHEMA_VERSION` é rejeitado com `ValueError` (422) antes de tocar no banco.

**Não mudou:** `init_db()` continua rodando no import; `app.py`, rotas, esquema, colunas, regras fiscais, `database_status()` (sem campos novos); linhas de `schema_migrations` (version=1 vs `user_version`=2 é divergência pré-existente, não corrigida).

**Residuais:**
- `init_db()` no import: um banco mais novo faz o import falhar (intencional). Mover para startup explícito é recomendado, mas muda testes/scripts.
- Com `user_version == 2` as migrações aditivas não rodam: coluna nova exige subir `SCHEMA_VERSION`.
- Backup de versão menor é aceito e fica no esquema antigo até a próxima inicialização.
- Leitura do cabeçalho ignora `user_version` alterado só em WAL não consolidado sem arquivo `-wal` (caso impossível em operação normal).

**Como reverter:** `git revert` do commit de DEF-002; volta o `PRAGMA user_version = 2` incondicional.
