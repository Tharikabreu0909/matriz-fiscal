# ADR-003 — Auditabilidade fiscal: revisões, snapshots imutáveis e proveniência

- **Status:** Proposta (aguarda aprovação)
- **Data:** 22/10/2026
- **Evidência:** P0-4, P0-5, P0-7, P0-8 e C-8 em `docs/architecture/risk-assessment.md`

## Contexto

- Uma nova malha **apaga** cálculos, decisões humanas e relatórios (`database.invalidate_process_analysis`).
- O cálculo não registra de quais entradas veio; o relatório combina o cálculo antigo com a análise nova.
- A Selic usada não é gravada; o resultado não pode ser reproduzido nem auditado.
- O relatório é regravado a cada `GET`; não existe "relatório emitido" imutável.
- `pgdas_documents` aceita duplicatas, e a precedência original × retificadora depende da ordem de upload.

## Decisão

### 1. Processo com revisões

```
fiscal_process (id, company_id, status, current_revision_id)
process_revision (id, process_id, number, created_at, reason,
                  malha_snapshot_json, pgdas_plan_json, planner_version,
                  input_fingerprint, status)   -- imutável após "SEALED"
revision_document (revision_id, document_id)   -- PDFs que compõem a revisão
```

- Nova malha ⇒ **nova revisão** (`number + 1`) que **herda** os documentos ainda válidos. Nada é apagado.
- Revisões anteriores ficam seladas quando há cálculo ou relatório emitido.
- Exemplo do processo 125: a revisão 1 guarda a malha A, os PGDAS, as decisões, o cálculo e o relatório emitido. A revisão 2 guarda a malha A+B consolidada, os mesmos PGDAS mais os novos, as decisões reaplicadas onde a competência não mudou, e um novo cálculo. **O valor fiscal não duplica**, porque cada revisão é uma visão completa e os totais nunca somam revisões.

### 2. Documentos idempotentes

- `stored_documents` passa a ser **por empresa**, com `UNIQUE(company_id, sha256)`; a revisão referencia o documento.
- `pgdas_documents` ganha `UNIQUE(process_id, sha256)`, `declaration_number`, `transmitted_at` e `is_rectification`. A precedência usa `transmitted_at` (ou o índice `CONSDECLARACAO13`, Fase 4), **nunca** a ordem de upload.
- Reimportar o mesmo arquivo é uma operação nula, com evento "repetido ignorado".

### 3. Snapshot de cálculo

Cada `tax_calculation` e `legal_charge_calculation` grava:

- `revision_id`, `input_fingerprint` (SHA-256 de: hashes dos PGDAS aceitos, malha consolidada, decisões, anexo, cenário);
- `rule_versions`: `{"planner": "2.4.0", "annex_tables": "LC155-2018", "tax_engine": "x.y", "charges": "lei9430-art61-v1"}`;
- `parameters`: as **séries Selic usadas mês a mês**, a fonte (`BCB SGS 4390`), a data da consulta e a data de atualização;
- `warnings` e `assumptions` (vencimento estimado, anexo único, sem sublimite).

O relatório só é emitido se o `input_fingerprint` do cálculo for igual ao da revisão atual; caso contrário, aparece "cálculo desatualizado — recalcule".

### 4. Relatório emitido imutável

- `POST /reports` emite e grava `issued_report` (`revision_id`, `calculation_ids`, `html_sha256`, `html` ou o arquivo, `issued_at`). O `GET` apenas lê.
- Um relatório emitido nunca é regravado; a reemissão gera outro registro.

### 5. Decisões humanas e trilha

- `analysis_decision` (append-only): competência, valor anterior → valor decidido, motivo padronizado, nota, `decided_at`, revisão. A decisão em vigor é a mais recente; as anteriores permanecem.
- `process_events` continua como trilha legível; passa a ser gravada **na mesma transação** da mudança.

### 6. Proveniência de dados

Cada valor fiscal exibido carrega a origem: `MALHA:<sha>:linha`, `PGDAS:<sha>:PA`, `HISTORICO:<sha>:competência`, `DECISAO:<id>`, `SELIC:<mês>`. O relatório lista as fontes e as premissas.

### 7. Integridade referencial

Migração aditiva com `ON DELETE RESTRICT` nas tabelas fiscais; exclusão de empresa vira arquivamento; a exclusão física por LGPD é um procedimento explícito que registra o que foi removido, sem os dados.

## Alternativas

- *Event sourcing completo*: rejeitado, porque é complexo demais para o tamanho do projeto. Revisões e snapshots resolvem a auditabilidade necessária.
- *Só backup automático antes do merge*: aceito como **mitigação imediata** (Fase 0), não como solução.

## Consequências

- (+) Todo número entregue ao cliente pode ser reproduzido e explicado.
- (+) Fim da perda de decisões do contador.
- (−) O banco cresce (snapshots JSON); compressão e retenção podem ser avaliadas depois.
- (−) A migração dos processos existentes vira "revisão 1" de cada processo.
