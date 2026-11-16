# Backlog das falhas pré-existentes (33 + 1 não coletado)

> Levantamento de 16/11/2026 sobre `phase0/integration` (`79ded57`), rodado em `phase0/qa-backlog`. Suíte: `--ignore=tests/test_v145_last_declared_cutoff.py`, `247 passam / 33 falham`.
> **Não tem relação com a Fase 0 C5/T02/T03.** São falhas que já existiam na baseline (`bf35530`). Nenhuma foi alterada para melhorar métrica. A categoria sai só da primeira linha do erro. Nada foi corrigido.
> Verificação de baseline: `static/`, `requirements.txt`, `VERSION` e os `.bat` não mudaram desde `bf35530`. Só `app.py` mudou (T02/T03). Não rodei a suíte em `bf35530`.

## Categorias

| Cat. | Critério (pela evidência do erro) | Item do backlog |
|---|---|---|
| **A** | `FileNotFoundError` para um PDF em `\mnt\data\…` (caminho fora do repo) | F0-05 |
| **B** | `assert '<trecho>' in '<!doctype html>…'`: procura string no HTML/CSS/JS do frontend | F0-13 |
| **C** | Versão, porta, launcher ou `requirements` (`uvicorn[standard]`, `py -3.13`, `APP_VERSION`) | F0-12, F6-01 |
| **D** | Hash de arquivo-fonte (`test_tax_calculator_files_were_not_changed`) | F0-14 |
| **E** | Função ou tabela ausente da linha 1.44/1.45 | D1, F3-08, F3-09 |
| **F** | Nenhuma das anteriores: **não classificada** | — |

## Tabela (33 falhas)

Gerada a partir do JUnit XML da rodada (`--tb=line`). A coluna de erro é a mensagem do pytest, que ele mesmo trunca com `...`.

| # | arquivo::teste | primeira linha do erro (copiada do pytest) | categoria |
|---|---|---|---|
| 1 | `tests/test_central_malha_upload.py::test_file_selection_processes_malha_automatically` | `assert 'async function processMalhaFile(file,confirmIdentityMismatch=false)' in '<!doctype html>\n<html lang="pt-BR">\n\n<head>\n  <meta charset="utf-8">\n  <meta name="viewport" content="width=devi...\'goToPgdasUploads\') {\n        showWorkflowStep(\'documents\');\n      }\n    });\n\n  </script>\n</body>\n\n</html>'` | B |
| 2 | `tests/test_central_malha_upload.py::test_summary_replaces_balloon_after_upload` | `assert '#malhaStageContent.has-malha #workspaceMalhaSection' in '<!doctype html>\n<html lang="pt-BR">\n\n<head>\n  <meta charset="utf-8">\n  <meta name="viewport" content="width=devi...\'goToPgdasUploads\') {\n        showWorkflowStep(\'documents\');\n      }\n    });\n\n  </script>\n</body>\n\n</html>'` | B |
| 3 | `tests/test_commercial_hardening.py::test_wrong_company_blocks_malha_and_override_is_audited` | `FileNotFoundError: [Errno 2] No such file or directory: '\\mnt\\data\\malha fiscal aconchego(3).pdf'` | A |
| 4 | `tests/test_commercial_hardening.py::test_matching_malha_is_stored_and_can_be_downloaded` | `FileNotFoundError: [Errno 2] No such file or directory: '\\mnt\\data\\malha fiscal aconchego(3).pdf'` | A |
| 5 | `tests/test_fast_pgdas_batch.py::test_frontend_sends_all_files_in_one_request` | `assert "pdfs.forEach(file=>form.append('files',file))" in '<!doctype html>\n<html lang="pt-BR">\n\n<head>\n  <meta charset="utf-8">\n  <meta name="viewport" content="width=devi...\'goToPgdasUploads\') {\n        showWorkflowStep(\'documents\');\n      }\n    });\n\n  </script>\n</body>\n\n</html>'` | B |
| 6 | `tests/test_guided_journey_null_safety.py::test_removed_legacy_requests_is_rendered_safely` | `assert "const legacyRequests=document.getElementById('requests');" in '<!doctype html>\n<html lang="pt-BR">\n\n<head>\n  <meta charset="utf-8">\n  <meta name="viewport" content="width=devi...\'goToPgdasUploads\') {\n        showWorkflowStep(\'documents\');\n      }\n    });\n\n  </script>\n</body>\n\n</html>'` | B |
| 7 | `tests/test_guided_journey_null_safety.py::test_pgdas_grid_has_explicit_guard` | `assert "const pgdasGrid=document.getElementById('pgdasUploadGrid');" in '<!doctype html>\n<html lang="pt-BR">\n\n<head>\n  <meta charset="utf-8">\n  <meta name="viewport" content="width=devi...\'goToPgdasUploads\') {\n        showWorkflowStep(\'documents\');\n      }\n    });\n\n  </script>\n</body>\n\n</html>'` | B |
| 8 | `tests/test_malha_reader_ui_regression.py::test_removed_pgdas_cta_is_null_safe_after_malha_reader` | `assert "const cta=document.getElementById('pgdasCta');" in '<!doctype html>\n<html lang="pt-BR">\n\n<head>\n  <meta charset="utf-8">\n  <meta name="viewport" content="width=devi...\'goToPgdasUploads\') {\n        showWorkflowStep(\'documents\');\n      }\n    });\n\n  </script>\n</body>\n\n</html>'` | B |
| 9 | `tests/test_malha_reader_ui_regression.py::test_reflection_coverage_does_not_create_new_document_requests` | `ValueError: substring not found` | F |
| 10 | `tests/test_malha_reader_ui_regression.py::test_central_balloon_remains_in_place` | `assert 'async function processMalhaFile(file,confirmIdentityMismatch=false)' in '<!doctype html>\n<html lang="pt-BR">\n\n<head>\n  <meta charset="utf-8">\n  <meta name="viewport" content="width=devi...\'goToPgdasUploads\') {\n        showWorkflowStep(\'documents\');\n      }\n    });\n\n  </script>\n</body>\n\n</html>'` | B |
| 11 | `tests/test_one_click_complete_estimate.py::test_tax_handler_automatically_requests_legal_charges` | `assert 'const chargesPayload=await requestAutomaticLegalCharges(' in '<!doctype html>\n<html lang="pt-BR">\n\n<head>\n  <meta charset="utf-8">\n  <meta name="viewport" content="width=devi...\'goToPgdasUploads\') {\n        showWorkflowStep(\'documents\');\n      }\n    });\n\n  </script>\n</body>\n\n</html>'` | B |
| 12 | `tests/test_one_click_complete_estimate.py::test_complete_result_unlocks_report` | `assert "setAnalysisTabEnabled('report',true)" in '<!doctype html>\n<html lang="pt-BR">\n\n<head>\n  <meta charset="utf-8">\n  <meta name="viewport" content="width=devi...\'goToPgdasUploads\') {\n        showWorkflowStep(\'documents\');\n      }\n    });\n\n  </script>\n</body>\n\n</html>'` | B |
| 13 | `tests/test_simplified_analysis_ui.py::test_tax_calculator_files_were_not_changed` | `AssertionError: assert '8873432e7fdf...a63763679782a' == 'b4eaaf54b631...c8722acda31ac'      - b4eaaf54b6312edd37cf488121e003783842271e89232f0bfdbc8722acda31ac   + 8873432e7fdff08fb21c181f5fe9774190ac8e23c6c5cbad253a63763679782a` | D |
| 14 | `tests/test_v129_stability.py::test_analysis_has_only_one_visible_competence_list` | `assert '#analysisSummarySection #analysisCompetenceList{display:none!important}' in '<!doctype html>\n<html lang="pt-BR">\n\n<head>\n  <meta charset="utf-8">\n  <meta name="viewport" content="width=devi... grid-template-columns: 1fr\n      }\n\n      .history-event-type {\n        justify-self: start\n      }\n    }\n  \n'` | B |
| 15 | `tests/test_v129_stability.py::test_malha_stage_is_forced_to_full_width` | `assert 'max-width:none!important' in '<!doctype html>\n<html lang="pt-BR">\n\n<head>\n  <meta charset="utf-8">\n  <meta name="viewport" content="width=devi... grid-template-columns: 1fr\n      }\n\n      .history-event-type {\n        justify-self: start\n      }\n    }\n  \n'` | B |
| 16 | `tests/test_v129_stability.py::test_calculation_has_local_visible_feedback` | `assert 'currentReflectionCoverage?.closed_months_complete===true' in '<!doctype html>\n<html lang="pt-BR">\n\n<head>\n  <meta charset="utf-8">\n  <meta name="viewport" content="width=devi... grid-template-columns: 1fr\n      }\n\n      .history-event-type {\n        justify-self: start\n      }\n    }\n  \n'` | B |
| 17 | `tests/test_v132_stability.py::test_same_malha_source_is_recognized_before_merge` | `FileNotFoundError: [Errno 2] No such file or directory: '\\mnt\\data\\malha fiscal aconchego(3).pdf'` | A |
| 18 | `tests/test_v132_stability.py::test_visible_notices_remain_unique_while_raw_rows_are_preserved` | `FileNotFoundError: [Errno 2] No such file or directory: '\\mnt\\data\\malha fiscal aconchego(3).pdf'` | A |
| 19 | `tests/test_v132_stability.py::test_planner_requests_old_and_recent_reflections_upfront` | `FileNotFoundError: [Errno 2] No such file or directory: '\\mnt\\data\\malha fiscal aconchego(3).pdf'` | A |
| 20 | `tests/test_v132_stability.py::test_documents_use_one_central_upload_and_compact_status_rows` | `assert "showWorkflowStep('documents',true)" in '<!doctype html>\n<html lang="pt-BR">\n\n<head>\n  <meta charset="utf-8">\n  <meta name="viewport" content="width=devi... grid-template-columns: 1fr\n      }\n\n      .history-event-type {\n        justify-self: start\n      }\n    }\n  \n'` | B |
| 21 | `tests/test_v132_stability.py::test_new_malha_locks_old_documents_until_upload_finishes` | `assert 'let awaitingNewMalhaUpload=false;' in '<!doctype html>\n<html lang="pt-BR">\n\n<head>\n  <meta charset="utf-8">\n  <meta name="viewport" content="width=devi... grid-template-columns: 1fr\n      }\n\n      .history-event-type {\n        justify-self: start\n      }\n    }\n  \n'` | B |
| 22 | `tests/test_v132_stability.py::test_technical_memory_has_dark_theme_override` | `assert '#calculationStageContent .memory{' in '<!doctype html>\n<html lang="pt-BR">\n\n<head>\n  <meta charset="utf-8">\n  <meta name="viewport" content="width=devi... grid-template-columns: 1fr\n      }\n\n      .history-event-type {\n        justify-self: start\n      }\n    }\n  \n'` | B |
| 23 | `tests/test_v132_stability.py::test_old_three_document_plan_is_refreshed_without_reupload` | `FileNotFoundError: [Errno 2] No such file or directory: '\\mnt\\data\\malha fiscal aconchego(3).pdf'` | A |
| 24 | `tests/test_v139_ui_and_pgdas_plan.py::test_analysis_dark_fix_is_final` | `assert 'background:#0d141f!important' in '<!doctype html>\n<html lang="pt-BR">\n\n<head>\n  <meta charset="utf-8">\n  <meta name="viewport" content="width=devi... grid-template-columns: 1fr\n      }\n\n      .history-event-type {\n        justify-self: start\n      }\n    }\n  \n'` | B |
| 25 | `tests/test_v139_ui_and_pgdas_plan.py::test_aconchego_plan_is_complete_upfront` | `FileNotFoundError: [Errno 2] No such file or directory: '\\mnt\\data\\malha fiscal aconchego(3).pdf'` | A |
| 26 | `tests/test_v141_pgdas_plan_guard.py::test_ui_blocks_analysis_when_pgdas_plan_is_incomplete` | `assert "currentPgdasPlanError=plan.validation?.status==='ERROR'" in '<!doctype html>\n<html lang="pt-BR">\n\n<head>\n  <meta charset="utf-8">\n  <meta name="viewport" content="width=devi...\'goToPgdasUploads\') {\n        showWorkflowStep(\'documents\');\n      }\n    });\n\n  </script>\n</body>\n\n</html>'` | B |
| 27 | `tests/test_v142_install_compatibility.py::test_runtime_requirements_do_not_install_uvicorn_standard_extra` | `AssertionError: assert 'uvicorn==0.35.0' in 'fastapi==0.116.1\nuvicorn[standard]==0.35.0\npython-multipart==0.0.20\npdfplumber==0.11.7\n'` | C |
| 28 | `tests/test_v142_install_compatibility.py::test_windows_launcher_selects_supported_python_and_unique_port` | `assert 'py -3.13' in '@echo off\nsetlocal\ncd /d "%~dp0"\ntitle Matriz Fiscal 1.41\n\nwhere py >nul 2>nul\nif %errorlevel%==0 (\n  set "PYT...l iniciar o Matriz Fiscal.\necho Confira a conexao com a internet e a instalacao do Python.\necho.\npause\nexit /b 1\n'` | C |
| 29 | `tests/test_v142_install_compatibility.py::test_current_version_matches_api_and_ui` | `assert 'APP_VERSION = "1.45.0"' in 'from __future__ import annotations\n\nfrom pathlib import Path\nimport asyncio\nfrom io import BytesIO\nimport json\n...      render_client_report(model),\n        headers={\n            "Cache-Control": "no-store",\n        },\n    )\n\n'` | C |
| 30 | `tests/test_v144_missing_pgdas.py::test_marking_missing_declarations_and_partial_report` | `AssertionError: {"detail":"Not Found"} assert 404 == 200  +  where 404 = <Response [404 Not Found]>.status_code` | F |
| 31 | `tests/test_workspace_visual_harmony.py::test_workspace_uses_one_visual_system_for_the_three_bands` | `assert '--workspace-radius:14px' in '<!doctype html>\n<html lang="pt-BR">\n\n<head>\n  <meta charset="utf-8">\n  <meta name="viewport" content="width=devi... grid-template-columns: 1fr\n      }\n\n      .history-event-type {\n        justify-self: start\n      }\n    }\n  \n'` | B |
| 32 | `tests/test_workspace_visual_harmony.py::test_summary_metrics_are_one_unified_module` | `assert '#companyWorkspace .work-summary{\n  min-height:var(--workspace-cell-height);' in '<!doctype html>\n<html lang="pt-BR">\n\n<head>\n  <meta charset="utf-8">\n  <meta name="viewport" content="width=devi... grid-template-columns: 1fr\n      }\n\n      .history-event-type {\n        justify-self: start\n      }\n    }\n  \n'` | B |
| 33 | `tests/test_workspace_visual_harmony.py::test_step_buttons_have_equal_height_and_flexible_width` | `assert 'flex:1 1 0' in '<!doctype html>\n<html lang="pt-BR">\n\n<head>\n  <meta charset="utf-8">\n  <meta name="viewport" content="width=devi... grid-template-columns: 1fr\n      }\n\n      .history-event-type {\n        justify-self: start\n      }\n    }\n  \n'` | B |

**Não coletado (categoria E):** `tests/test_v145_last_declared_cutoff.py`: `ImportError: cannot import name 'adapt_plan_to_last_transmitted' from 'services.pgdas_planner'`. Função ausente da linha 1.45, por isso E.

## Resumo por categoria

| Cat. | Falhas | Itens |
|---|---|---|
| A | 7 | F0-05 |
| B | 20 | F0-13 |
| C | 3 | F0-12, F6-01 |
| D | 1 | F0-14 |
| E | 0 falhas + 1 não coletado (v145) | D1, F3-08, F3-09 |
| **F (não classificadas)** | **2** | — |

Total: 7 + 20 + 3 + 1 + 0 + 2 = 33.

**Não classificadas (F):**
- `test_malha_reader_ui_regression.py::test_reflection_coverage_does_not_create_new_document_requests`: `ValueError: substring not found`. A mensagem não diz qual substring.
- `test_v144_missing_pgdas.py::test_marking_missing_declarations_and_partial_report`: `{"detail":"Not Found"} assert 404 == 200`. A mensagem não diz qual requisição retornou 404. O teste faz `POST /api/process/{pid}/pgdas-situation` e depois `GET /partial-report`. Essa rota não existe em `app.py` nem em `bf35530` (grep). Se o 404 for dessa rota, o caso seria E. Não classifiquei porque o erro não confirma isso.

## Ordem sugerida de tratamento

1. **A (F0-05):** versionar PDFs sanitizados. Destrava os testes de malha reais.
2. **C (F0-12, F6-01):** alinhar versão, launcher e `requirements` a uma fonte única.
3. **D (F0-14):** trocar o teste de hash por casos de regressão fiscal.
4. **E (D1, F3-08, F3-09):** depende da decisão D1. Inclui o v145.
5. **B (F0-13):** reescrever os testes de trecho por `id` ou rota estável. É o maior grupo e não depende de A a E.
6. **F:** primeiro obter a mensagem completa (`pytest -x --tb=long` no teste), depois classificar.

Nada disso foi implementado nesta rodada.
