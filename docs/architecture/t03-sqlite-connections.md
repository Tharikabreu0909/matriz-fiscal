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
- DEF-002 (`init_db()` a cada import, `user_version` rebaixado) **não tratado**.

## Como reverter

`git revert 048aef5`. Isso reabre o DEF-001: o teste de restauração volta a falhar no Windows e o canário volta a depender de `gc.collect()`. Sem migração de banco.
