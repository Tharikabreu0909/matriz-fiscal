# T08: relatório de testes

Implementação: `docs/architecture/t08-fingerprints.md`. Branch `t08/tests` com o merge de `t08/fingerprints` (`b73dee9`, correções do Selo `e76c0e4`, `620287a`, `d4df4d1`). Commit deste relatório: ver histórico de `t08/tests`.

## 1. Arquivos de teste

| Arquivo | Testes | O que prova |
|---|---|---|
| `tests/test_t08_fingerprints.py` | 15 | Unidade de `services/fingerprints.py`: forma canônica e tipos (`test_canonical_is_ordered_and_types`, `test_float_raises`, `test_decimal_precision_preserved`); sensibilidade (`test_digest_depends_on_kind`, `test_same_inputs_same_fingerprint`); invariância a ordem, duplicata e dado irrelevante (`test_order_of_documents_and_rows_irrelevant`, `test_duplicate_document_and_rows_do_not_change`, `test_irrelevant_changes_do_not_change`); mudança de dado relevante (`test_relevant_changes_change`, `test_tax_fingerprint_sensitivity`); normalização de competência (`test_competence_normalized`); Selic/data-base só mexe em encargos (`test_only_selic_or_base_date_changes_charges`); leitura dos encargos (`test_charges_inputs_from_result`); tabela de estados (`test_states`); **virada de calendário versus mudança de dados** (`test_period_advanced_vs_inputs_changed`, novo). |
| `tests/test_t08_api.py` | 8 | Fluxo pela API com processo real (divergência de 500.000 centavos e confirmação): ciclo completo (`test_full_cycle`); PGDAS relevante novo desatualiza e bloqueia o relatório, e recalcular recupera (`test_new_relevant_pgdas_outdates_and_blocks_report_then_recovers`); PGDAS duplicado não desatualiza (`test_duplicate_pgdas_upload_does_not_outdate`); GET do processo é somente leitura (`test_process_status_is_read_only`); cálculo legado vira desatualizado (`test_legacy_calculation_is_outdated`); relatório sem cálculo mantém o 409 de antes (`test_report_without_calculation_keeps_not_calculated_409`); Selic muda só `charges` (`test_selic_change_outdates_only_charges_fingerprint`); **virada do calendário diz `PERIOD_ADVANCED`, não `INPUTS_CHANGED`, e o relatório não grava** (`test_calendar_advance_says_period_advanced_not_inputs_changed`, novo). |
| `tests/test_t08_flow.py` | 13 | Os 13 casos de fluxo do contrato §8: estados sem PGDAS, com PGDAS sem cálculo e depois do cálculo; relatório 409 sem gravar; recálculo só do imposto; recálculo completo; Selic; legado; 409 de encargos; GET sem escrita; histórico preservado; competência pendente no HTML. |

Total dos três: **36 testes**, todos passando (`36 passed`).

## 2. Resultado da suíte geral

Comando: `.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider -rfE --ignore=tests/test_v145_last_declared_cutoff.py tests/`, comparação por nome com `LC_ALL=C sort -u`.

- **325 passam, 33 falham**. Violações de isolamento: 0.
- Comparação com `docs/architecture/preexisting-failures-backlog.md`: **33 falhas, 0 novas, 0 sumidas**.
- Os 325 = 289 da baseline + 36 desta frente.

Os 33 são os pré-existentes. Nenhum foi corrigido nem teve o teste alterado para passar.

## 3. Alteração de teste existente

`tests/test_fix_report_missing.py`: três asserções trocaram o texto "Não calculado" pelo novo "Cálculo pendente de documentação" (contrato §3). O HTML sem competência pendente continua byte a byte igual (`HTML_SHA256_BEFORE_FIX`).

## 4. Mutações

Cada mutação foi revertida depois do teste, e o arquivo voltou ao estado do commit.

| Mutação | Quem rodou | Resultado |
|---|---|---|
| **P. `PERIOD_ADVANCED` vira `INPUTS_CHANGED`** em `services/fingerprints.py` (linha 144) | **Eu, reproduzi** | **2 falhas**: `test_period_advanced_vs_inputs_changed` (unidade) e `test_calendar_advance_says_period_advanced_not_inputs_changed` (API). Revertida: os 23 testes de unidade e API voltaram a passar. |
| Ignorar o anexo no fingerprint do imposto | Maestro (relato) | 2 falhas |
| Tratar cálculo legado como `ATUALIZADO` | Maestro (relato) | 3 falhas, em unidade, API e fluxo |
| `_pgdas_docs` devolvendo lista vazia | Selo (relato) | 7 falhas |
| Relatório sem bloqueio por `can_emit` | Selo (relato) | 4 falhas |

As mutações do Maestro e do Selo não foram repetidas por mim. Só a mutação P foi reproduzida nesta tarefa.

## 5. Limitações dos testes

1. **Processo sintético em `test_t08_flow.py`** com divergência zero: imposto e encargos saem R$ 0,00 e a lista de encargos fica vazia. Esses testes provam **estados**, não **valores**.
2. **`test_t08_api.py` tem valores reais** (divergência de 500.000 centavos e confirmação). A data de cobertura é fixada em 15/05/2026 (`TODAY`), exceto no teste de virada, que simula 25/06/2026.
3. **Selic simulada** em todos os testes (`fetch_bcb_monthly_selic` com taxas fixas). Não há teste com a série publicada.
4. **Competência pendente (flow, teste 13):** testado com `render_client_report` e modelo sintético. Não há processo real que gere competência pendente com relatório liberado.
5. **Testes 10 e 11 do fluxo** (GET sem escrita, histórico preservado): a invariante de não escrita já valia antes; o teste também exige `freshness` na resposta.
6. **Feriados bancários** não estão nos testes nem na regra de vencimento (`standard_due_date`). O teste de virada usa 25/06/2026 e não cobre feriados.
7. **Dados fabricados:** não há teste com malha ou PGDAS reais de cliente (fora do escopo).
