# Dependências para T09 e T11 (a partir do código atual)

Fatos lidos em `t08/tests` após o merge de T08. Nada foi implementado aqui.

## 1. T09: snapshot antes do merge da malha

### O que o código faz hoje
- Ao receber uma malha nova em um processo existente, `analyze-malha` chama `merge_malhas` e `update_process_malha` (app.py ~626-629) e depois `invalidate_process_analysis(process_id)` (app.py ~635).
- `invalidate_process_analysis` (database.py:541-562) apaga com `DELETE` as linhas do processo nas tabelas: `diagnostics`, `analysis_confirmations`, `accounting_study_conclusions`, `tax_profiles`, `tax_calculations`, `legal_charge_calculations` e `client_reports`.
- Não há cópia, backup nem evento antes do `DELETE`. Se o merge falhar no meio, não há como voltar.
- `pgdas_documents` e os processos (`processes`) não são apagados, mas o plano e a malha são sobrescritos (`update_process_malha`, database.py:512).
- Já existe um mecanismo de cópia do banco: `create_backup` (services/backup_service.py:26) usa `sqlite3` com `source.backup(destination)` (linhas 33-38). Não é usado no merge.
- Ponto de atenção: `malha_already_imported` (services/malha_merge.py:74) compara o SHA-256 da malha. Uma malha repetida é ignorada e não chega ao `DELETE` (app.py ~613-618).

### O que T09 precisa garantir
1. **Antes** de qualquer escrita do merge, copiar o banco com a API de backup do SQLite para `backups/pre-merge/` (um arquivo por evento, com nome que contenha o processo e o horário). Só o banco; PDFs e documentos não entram.
2. Registrar no evento de processo (`process_events`) o caminho e o hash do snapshot. Assim o merge é rastreável.
3. **Falha no snapshot aborta o merge:** nenhuma linha é apagada nem atualizada. A exceção sobe antes de `update_process_malha`.
4. O snapshot deve preservar: malha anterior, decisões humanas (`analysis_confirmations`), conclusões do estudo, cálculos (`tax_calculations`, `legal_charge_calculations`), relatórios (`client_reports`) e estado do processo (`processes.status`). Isso é o que `invalidate_process_analysis` apaga.
5. **Consistência:** o snapshot e o merge devem ocorrer dentro da mesma sequência, com `DatabaseBusyError` tratado (database.py `connect`, bloqueio por restauração).
6. **Recuperável:** a restauração deve passar pelo caminho já existente (`restore_backup`, services/backup_service.py:109), com validação de integridade (`_integrity_ok`, linha 100). Restaurar um snapshot de merge não pode apagar arquivos de outros processos.
7. Testes: falha simulada do snapshot deixa todas as tabelas iguais ao estado anterior; sucesso cria o arquivo e o evento com o caminho.

### Relação com T08
Se o merge for feito, `invalidate_process_analysis` continuará apagando cálculos. T08 só marca `DESATUALIZADO` depois que o cálculo existe, então T09 não depende do T08 para proteger dados. O snapshot é o que protege.

## 2. T11: deduplicação de PGDAS

### O que o código faz hoje
- `upload-pgdas` (app.py:710) e `upload-pgdas-auto` (app.py:1028) chamam `save_pgdas_document` (app.py:768 e 1178) **sem checar duplicata**. Cada envio gera uma nova linha em `pgdas_documents`.
- `pgdas_documents` (database.py:224-237) tem `sha256` mas **não tem `UNIQUE`**. Os `UNIQUE` do banco estão em outras tabelas (`stored_documents`, database.py:350: `UNIQUE(process_id, kind, sha256)`).
- A deduplicação por hash existe só no arquivo armazenado: `register_stored_document` (database.py:1332) reaproveita a linha existente com o mesmo `sha256`.
- `list_accepted_pgdas` (database.py:839-846) devolve todas as linhas com `accepted = 1`, ordenadas por `id`. Um reenvio entra duplicado na lista.
- T08 já trata esse caso no fingerprint: `_pgdas_docs` (services/fingerprints.py:62) usa conjunto e ignora duplicatas de conteúdo. Por isso um reenvio idêntico não desatualiza cálculos (teste `test_duplicate_pgdas_upload_does_not_outdate`).

### O que T11 precisa garantir
1. **Identidade pelo conteúdo semântico**, não pelo hash do PDF. Usar a mesma definição de `services/fingerprints.py` (`_pgdas_docs`: tipo de documento + `assessment`). O hash do PDF muda com metadados e não identifica o conteúdo fiscal.
2. **Reenvio idempotente:** um upload com o mesmo conteúdo semântico não cria linha nova com `accepted = 1`. Responde como "repetido ignorado", no mesmo padrão de `duplicate_ignored` da malha (app.py ~613-617).
3. **Original × retificadora:** distinguir pelo identificador da declaração (`assessment`, campo do número da declaração) e pelo horário de transmissão. Isso depende de F3-03 (extração de `declaration_number` e `transmitted_at` no leitor). Sem isso, T11 só deduplica conteúdo idêntico.
4. **Histórico das operações:** cada upload aceito ou repetido vira evento em `process_events` (já existe a tabela e `append_process_event`). Não apagar a linha original.
5. **Esquema:** adicionar um índice único em `pgdas_documents` exige saneamento das duplicatas já gravadas (mesma regra de F3-02). Migração sem apagar histórico: marcar as duplicatas como não aceitas em vez de deletar. Sem mudança de `SCHEMA_VERSION` sem aprovação.
6. **Testes:** mesmo PDF em dois uploads → uma linha aceita; PDF diferente com mesmo período e número → conflito (T12, fora deste escopo); retificadora com número diferente → entra como nova versão.

### Pontos em aberto
- Sem UNIQUE, a identidade é só checagem de aplicação. Um upload concorrente pode passar.
- `upload-pgdas-auto` processa vários arquivos em paralelo (app.py:1028). A deduplicação precisa ser feita dentro da mesma transação de gravação.

## 3. Ordem sugerida
Sugestão minha, não consta do plano: fazer T11 (deduplicação) antes de T09 (snapshot) reduz o que o snapshot precisa guardar. O plano exige só que T10b venha depois de T09 (`phase-0-plan.md` §4).
