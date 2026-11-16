# T02 — Política de requisições (Host / Origin / Sec-Fetch-Site)

> Implementação da T02 do [plano da Fase 0](phase-0-plan.md) (P0-S1). Política normativa: [security-policy.md](security-policy.md). Não repete o que está lá.
> Estado: `phase0/integration` (`79ded57`), local, sem push.

## Arquivos

| Arquivo | Papel |
|---|---|
| `services/request_guard.py` (novo) | Middleware ASGI puro. Nunca lê o corpo da requisição |
| `app.py` | Registro do middleware (mais externo, após `log_requests`); restore responde 409 quando ocupado |
| `tests/test_t02_guard_unit.py` | Testes unitários do guard |
| `tests/test_t02_request_guard.py` | Testes de API dos vetores do plano §2.4 |
| `tests/test_t02_restore_and_ui.py` | Restore cross-origin e UI sem alteração |

`static/index.html` **não foi alterado**.

## Regras

1. **Host:** nas portas 8141, 8145 e 8146, só `127.0.0.1` e `localhost`. Outro host → `400 HOST_NOT_ALLOWED` em toda requisição. `CHECKFISCAL_ALLOWED_HOSTS` acrescenta hosts (aditivo).
2. **Guardadas:** `POST`, `PUT`, `PATCH`, `DELETE` e `GET` sob `/api/`, exceto `GET /api/health`. Motivo: há GETs que gravam (`/api/system/backup`, `/api/system/support-bundle`, `/api/client-report`, `/api/process/{id}`, `/api/companies/{id}`).
3. **Origin:** precisa ser `http://host:porta` permitido. `null` e `https://` são inválidos.
4. **Sec-Fetch-Site:** só `same-origin` ou `none`. Vazio é inválido.
5. **Contradição** entre Origin e Sec-Fetch-Site → `403 CROSS_ORIGIN_BLOCKED`.
6. **Cross-site permitido** só em `GET /`, `GET /static/app.css` e `GET /api/health`.
7. **Sem token e sem interruptor de desativação.** O `CHECKFISCAL_ORIGIN_CHECK=0` do plano antigo foi descartado.

## Testes

- Suíte dos três arquivos `tests/test_t02_*.py`, com `test_t01_isolation.py`: **122 passam** (ver o "Status de execução" em [phase-0-plan.md](phase-0-plan.md)).
- Os xfail da C5 foram removidos em `0eba842`.
- Bugs encontrados pela C5 e corrigidos na T02: `Origin: https://…` passava; `PUT /api/health` escapava pela isenção de caminho.
- Revisão Ponytail: log forging por caminho com quebra de linha. Corrigido com `%r`, com teste novo, provado por mutação.
- Validação do restore rodava em dobro: corrigido para uma vez (`79ded57`).
- **Navegador real (Chrome, porta 8146, banco temporário):** POST same-origin → 201; POST cross-site enviado pelo navegador não criou nada.
- **curl:** `Host: evil.com` → 400; `Origin` externo → 403; restore cross-origin → 403; `GET /api/health` cross-site → 200.

## Falhas pré-existentes (33)

Rodada em 16/11/2026, `phase0/integration` (`79ded57`), comando `--ignore=tests/test_v145_last_declared_cutoff.py`: **247 passam, 33 falham**. A mesma lista na ordem invertida dos arquivos.

- **`FileNotFoundError`:** 7 linhas de erro para `'\\mnt\\data\\malha fiscal aconchego(3).pdf'`.
- **`AssertionError` / `ValueError`:** as demais, sobre a presença de um trecho de texto ou de um valor no fonte ou no HTML. Não classificadas além disso.

Lista completa:

- `test_central_malha_upload.py`: `test_file_selection_processes_malha_automatically`, `test_summary_replaces_balloon_after_upload`
- `test_commercial_hardening.py`: `test_wrong_company_blocks_malha_and_override_is_audited`, `test_matching_malha_is_stored_and_can_be_downloaded`
- `test_fast_pgdas_batch.py`: `test_frontend_sends_all_files_in_one_request`
- `test_guided_journey_null_safety.py`: `test_removed_legacy_requests_is_rendered_safely`, `test_pgdas_grid_has_explicit_guard`
- `test_malha_reader_ui_regression.py`: `test_removed_pgdas_cta_is_null_safe_after_malha_reader`, `test_reflection_coverage_does_not_create_new_document_requests`, `test_central_balloon_remains_in_place`
- `test_one_click_complete_estimate.py`: `test_tax_handler_automatically_requests_legal_charges`, `test_complete_result_unlocks_report`
- `test_simplified_analysis_ui.py`: `test_tax_calculator_files_were_not_changed`
- `test_v129_stability.py`: `test_analysis_has_only_one_visible_competence_list`, `test_malha_stage_is_forced_to_full_width`, `test_calculation_has_local_visible_feedback`
- `test_v132_stability.py`: `test_same_malha_source_is_recognized_before_merge`, `test_visible_notices_remain_unique_while_raw_rows_are_preserved`, `test_planner_requests_old_and_recent_reflections_upfront`, `test_documents_use_one_central_upload_and_compact_status_rows`, `test_new_malha_locks_old_documents_until_upload_finishes`, `test_technical_memory_has_dark_theme_override`, `test_old_three_document_plan_is_refreshed_without_reupload`
- `test_v139_ui_and_pgdas_plan.py`: `test_analysis_dark_fix_is_final`, `test_aconchego_plan_is_complete_upfront`
- `test_v141_pgdas_plan_guard.py`: `test_ui_blocks_analysis_when_pgdas_plan_is_incomplete`
- `test_v142_install_compatibility.py`: `test_runtime_requirements_do_not_install_uvicorn_standard_extra`, `test_windows_launcher_selects_supported_python_and_unique_port`, `test_current_version_matches_api_and_ui`
- `test_v144_missing_pgdas.py`: `test_marking_missing_declarations_and_partial_report`
- `test_workspace_visual_harmony.py`: `test_workspace_uses_one_visual_system_for_the_three_bands`, `test_summary_metrics_are_one_unified_module`, `test_step_buttons_have_equal_height_and_flexible_width`

Não coletado: `tests/test_v145_last_declared_cutoff.py` → `ImportError: cannot import name 'adapt_plan_to_last_transmitted' from 'services.pgdas_planner'`.

## Residuais

- Trava de Host duplicado: valida o primeiro cabeçalho.
- WebSocket não é checado (o app não tem rota WebSocket).
- `https` bloqueado como `Origin`: se houver proxy TLS, ajustar.
- Navegador sem `Sec-Fetch-*` e GET sem `Origin` passam só pela regra de `Host`.

## Como reverter

`git revert` dos commits da T02 (`79ded57`, `0eba842`, `e1f1c0b`, `2974e87`), em ordem inversa. Sem migração de banco e sem dado novo gravado. Não há variável de desligamento.
