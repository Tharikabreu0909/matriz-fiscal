# T08: fingerprints e estados de atualização

Contrato: `t08-spec.md` (fora do repositório). Este documento descreve o que está no código em `t08/fingerprints` (merge fast-forward de `t08/tests`, base `f8db116`). Os fatos foram conferidos no código e nos testes.

## 1. Problema

- **Antes:** `POST /api/client-report` (app.py, rota `client_report`) só verificava se existia cálculo de imposto e de encargos do cenário. Não conferia se o cálculo ainda correspondia aos documentos. Um PGDAS novo aceito, uma decisão humana nova ou uma malha nova deixavam o relatório emitível com valores antigos.
- **Antes:** `POST /api/calculate-legal-charges` não conferia se o imposto usado era o atual.
- **Antes:** o relatório (GET) gravava `client_reports` e mudava o status do processo.
- **Agora:** os cálculos carregam um fingerprint das entradas. Leituras calculam o estado atual sem gravar nada. Relatório e encargos são bloqueados quando o cálculo está desatualizado.

## 2. Fluxo novo

1. `POST /api/upload-pgdas`, `upload-pgdas-auto` e `confirm-analysis` **não invalidam nada**. Gravam o dado e o estado muda na próxima leitura, porque o fingerprint da análise é recalculado.
2. `POST /api/calculate-tax` grava `input_fingerprint` no JSON do resultado (app.py, `calculate_tax`, ~linha 1954).
3. `POST /api/calculate-legal-charges` recusa com 409 `TAX_OUTDATED` se o imposto do cenário está `DESATUALIZADO` (app.py ~2065). Se aceita, grava `input_fingerprint` nos encargos (app.py ~2086).
4. `GET /api/client-report` calcula `freshness` (somente leitura). Se `block_code` estiver preenchido, responde 409 sem gravar relatório e sem mudar status.
5. `GET /api/process/{id}` devolve `freshness` (parâmetro opcional `scenario`, padrão `CONSERVATIVE_FISCAL_EXPOSURE`).

Nenhuma rota de leitura recalcula nem grava resultado. Não há recálculo automático.

## 3. Os três fingerprints (`services/fingerprints.py`)

Funções puras, sem I/O, rede ou banco. `canonical()` usa JSON ordenado; `float` levanta `TypeError` (centavos são `int`; `Decimal` vira string normalizada).

### 3.1 Análise (`analysis_fingerprint`, linha 87)
| Entra | Não entra | Por quê |
|---|---|---|
| Malha: `(tipo, competência, informado, considerado, divergência)` sem duplicatas (`_malha_rows`, l.52) | id, página, linha da tabela, confiança, células de origem, marcas de duplicata | posição no PDF, não conteúdo fiscal |
| PGDAS aceitos: `document_type` + `assessment` completo, sem duplicatas (`_pgdas_docs`, l.62) | hash do PDF, nome, caminho, leitor, cobertura, métricas derivadas, timestamps | o mesmo conteúdo enviado duas vezes ou em outro arquivo não muda o cálculo |
| Decisões humanas: competência, decisão e campos `*_cents` da recomendação (`_confirmations`, l.69) | timestamps | só o valor que alimenta o cálculo |
| Conclusões do estudo contábil: status e valores validados (`_conclusions`, l.79) | `created_at`, `updated_at`, notas | não entram na conta |
| `RULES["analysis"]` | — | troca de regra invalida tudo |

CNPJ, razão social e nome do processo ficam fora: não mudam o cálculo.

### 3.2 Imposto (`tax_fingerprint`, l.97)
Entra o fingerprint da análise, anexo, cenário, `standard_profile_confirmed`, fim do cálculo (`actual_calculation_end`), fim da reflexão completa, competências futuras pendentes (ordenadas) e `RULES["tax"]`.

### 3.3 Encargos (`charges_fingerprint`, l.109)
Entra o fingerprint do imposto usado, a data-base (`update_date`), a taxa de juros por competência (`selic_used`, extraída das linhas do resultado em `charges_inputs`, l.117), os vencimentos usados e `RULES["charges"]`.

**Consequência:** mudar só a Selic ou a data-base invalida os encargos, nunca o imposto nem a análise. Coberto por `test_selic_change_outdates_only_charges_fingerprint` em `test_t08_api.py` (troca a taxa simulada e confere que só `charges` muda). Limite: a Selic é simulada (ver R1 e R8).

## 4. Persistência

- Sem migração. `SCHEMA_VERSION` continua 2. As chaves ficam dentro do JSON já gravado em `tax_calculations.calculation_json` e `legal_charge_calculations.calculation_json`.
- Imposto: `input_fingerprint = {version: 1, analysis, tax, calculated_at}`.
- Encargos: `input_fingerprint = {version: 1, tax, charges, calculated_at}`.
- Cálculos antigos (sem a chave) são **LEGADO**. Ficam gravados para auditoria; nada é apagado.

## 5. Estados e reasons

| Objeto | Estado | Reason | Condição |
|---|---|---|---|
| analysis | `ATUALIZADO` / `PENDENTE_DE_DADOS` | — | `PENDENTE_DE_DADOS` se falta PGDAS do plano ou se há meses não fechados |
| tax | `PENDENTE_DE_DADOS` | `MISSING_DOCUMENTS` | sem cálculo e o gating de `calculate_tax` recusaria |
| tax | `NAO_CALCULADO` | `NO_CALCULATION` | sem cálculo e o gating passaria |
| tax | `ATUALIZADO` | `CURRENT` | fingerprint gravado == recalculado agora |
| tax | `DESATUALIZADO` | `INPUTS_CHANGED` | fingerprint diferente |
| tax | `DESATUALIZADO` | `LEGACY_NO_FINGERPRINT` | cálculo sem a chave |
| charges | `NAO_CALCULADO` | `NO_CALCULATION` | sem encargos |
| charges | `ATUALIZADO` | `CURRENT` | imposto atual **e** `charges.input_fingerprint.tax` == fingerprint do imposto atual |
| charges | `DESATUALIZADO` | `TAX_OUTDATED` | imposto desatualizado ou refeito depois |
| charges | `DESATUALIZADO` | `LEGACY_NO_FINGERPRINT` | encargos sem a chave |

`report.can_emit = tax ATUALIZADO e charges ATUALIZADO`.

`block_code` (campo interno, presente também na resposta) vale `NOT_CALCULATED`, `CALCULATION_OUTDATED` ou `null`. Usado pelas rotas para decidir o 409.

Estado não é valor: um cálculo atualizado pode dar R$ 0,00. Uma competência pendente nunca é R$ 0,00.

## 6. API

| Rota | Mudança |
|---|---|
| `GET /api/process/{id}` | nova chave `freshness` (`scenario` opcional na query) |
| `POST /api/calculate-tax` | resposta com `freshness` (pós-gravação) |
| `POST /api/calculate-legal-charges` | resposta com `freshness`; **409 `TAX_OUTDATED`** se o imposto está `DESATUALIZADO` |
| `GET /api/client-report` | **409** com `code` `CALCULATION_OUTDATED` (cálculo desatualizado) ou `NOT_CALCULATED` (falta cálculo); não grava relatório nem muda status |

Formato de `freshness`: `{scenario, analysis{state,fingerprint}, tax{state,reason,calculated_at}, charges{state,reason,calculated_at,base_date}, report{can_emit,message}, block_code}`.

## 7. Mensagens

Constantes em `services/fingerprints.py` (l.14-19) e `services/client_report.py` (l.8-16):
- Contador, desatualizado: "Cálculo desatualizado. Os documentos ou parâmetros deste processo foram alterados após o último cálculo. Recalcule o imposto e os encargos antes de emitir um novo relatório."
- Cliente, competência pendente: título "Cálculo pendente de documentação" com o detalhe aprovado e a faixa "faltam PGDAS que cubram …". Nunca R$ 0,00.
- Os textos "Calcule primeiro…" (409 de falta de cálculo) foram mantidos.

## 8. Interface (`static/index.html`)

- Faixa discreta `data-freshness-banner` nas etapas Cálculo e Relatório, visível só com `DESATUALIZADO`. Mostra `report.message`.
- Rótulo "Desatualizado" no stepper das etapas Cálculo e Relatório.
- Botão do relatório (`openClientReport`) desabilitado quando `can_emit` é falso; o título do botão traz a mensagem.
- Nenhum controle novo. O dashboard não foi redesenhado.
- Há um ajuste visual pequeno do Selo previsto para `static/index.html` que não afeta os documentos (ainda não está neste commit).

## 9. Arquivos alterados

- Novos: `services/fingerprints.py`, `tests/test_t08_fingerprints.py`, `tests/test_t08_api.py`, `tests/test_t08_flow.py`, este documento, `t08-test-report.md`, `t08-t09-t11-dependencias.md`.
- Alterados: `app.py` (`build_freshness`, rotas listadas na seção 6, `input_fingerprint` em `calculate_tax` e `calculate_legal_charges_endpoint`), `services/client_report.py` (textos de pendência; célula de diferença de imposto mostra "—" na competência pendente), `static/index.html`, `tests/test_fix_report_missing.py` (três asserções trocaram o texto antigo "Não calculado" pelo novo, conforme §5 do contrato), `docs/architecture/t08-janela-pgdas-d.md` (registro da janela PGDAS-D), `phase-0-plan.md`, `implementation-backlog.md`.

## 10. Decisões onde o contrato deixava margem

1. `input_fingerprint` guarda também `calculated_at` (não previsto na spec; campo informativo).
2. `freshness` tem `block_code` no nível superior (campo aditivo, usado pelas rotas).
3. `analysis.state` é `PENDENTE_DE_DADOS` também quando há meses não fechados (não só PGDAS faltando).
4. `selic_used` é a taxa por competência lida das linhas do resultado, porque `legal_charges` não expõe a série.
5. `build_freshness` recalcula o fingerprint do imposto com `standard_profile_confirmed=True` fixo (app.py ~333). O cálculo grava o valor da requisição. Hoje não há divergência: o motor recusa `False` com 422 (verificado por sonda descartável). Se isso mudar, o imposto nasce desatualizado. Ver risco R3.
6. A competência pendente oculta a célula de diferença de imposto com "—", não com R$ 0,00.
7. O 409 de encargos (`TAX_OUTDATED`) é checado antes do cálculo e só quando o imposto está `DESATUALIZADO`, não quando está pendente.

## 11. Riscos e limitações

- **R1. Selic publicada depois do cálculo não é detectada offline.** Exigiria cache da Selic (F3-04). O relatório mostra a data-base usada (`charges.base_date`).
- **R2. O estado depende do calendário.** `build_freshness` calcula a cobertura com a data de hoje (`as_of_date=None`). O "último mês vencido" muda com o tempo, então um cálculo pode virar `DESATUALIZADO` sem nenhum documento novo. Lido no código; não reproduzido com data simulada. Os testes de API fixam a data em 15/05/2026 (`TODAY` em `test_t08_api.py`), então esta dependência não é coberta por teste.
- **R3. Acoplamento de `standard_profile_confirmed`** (decisão 5 acima).
- **R4. `GET /api/process/{id}` refaz a análise a cada leitura** (`analyze_process`, cobertura e planejador). Custo de CPU por leitura; não grava resultado de cálculo, mas `ensure_current_pgdas_plan` pode regravar o plano (comportamento que já existia).
- **R5. Cálculo legado passa a `DESATUALIZADO`** e exige recalculo. Afeta processos calculados antes do merge.
- **R6. Upload e confirmação não invalidam nada.** A diferença aparece só no estado. Os PGDAS duplicados continuam como linhas em `pgdas_documents` (sem UNIQUE; ver `t08-t09-t11-dependencias.md`). Duplicatas com o mesmo conteúdo não alteram o fingerprint.
- **R7. Mudar a malha (`analyze-malha`) apaga resultados derivados** (`invalidate_process_analysis`, database.py:541). Isso é T09, fora deste trabalho. Diagnósticos, decisões humanas, conclusões, perfis, cálculos e relatórios somem.
- **R8. Os testes usam processo sintético com divergência zero** (ver `t08-test-report.md`). Provam estados, não valores.
