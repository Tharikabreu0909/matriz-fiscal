# Backlog de implementação

> Itens pequenos e independentes, em ordem de prioridade. Nenhum foi iniciado.
> Tamanho: **P** ≤ 0,5 dia · **M** ≤ 2 dias · **G** ≤ 5 dias.

## Fase 0 — Estabilização

| ID | Tarefa | Tam. | Critério de aceite |
|---|---|---|---|
| F0-01 | Decidir D1 a D4 (`migration-plan.md`) e registrar em `jarvis_docs/activeContext.md` | P | Decisões escritas e datadas |
| F0-02 | Criar a tag `baseline-1.41-bf35530` | P | A tag existe no remoto |
| F0-03 | Adicionar `httpx` e `pytest-cov` a `requirements-dev.txt` | P | **PARCIAL:** `httpx==0.28.1` feito (T01); `pytest-cov` não adicionado. Zero erros de coleta por `httpx` |
| F0-04 | `tests/conftest.py` com fixture `autouse` que define `CHECKFISCAL_DATA_DIR` e `CHECKFISCAL_DB_PATH` em `tmp_path` **antes** de importar `database` | P | **FEITO (T01, `0a1b7e6`/`4b496c7`).** Rodar a suíte não cria nem altera nada em `%LOCALAPPDATA%\CheckFiscal` (verificar o mtime) |
| F0-05 | Versionar PDFs **sanitizados** (malha de 1 e de 2 páginas; extrato; declaração) em `tests/fixtures/pdf/` e trocar `/mnt/data/...` | M | Nenhum teste referencia `/mnt/data`; `test_v143` usa a fixture e **falha** no HEAD atual |
| F0-06 | Trocar os `return` silenciosos por `pytest.skip("motivo")` ou por falha | P | `grep -n "return$" tests` não encontra guarda de fixture |
| F0-07 | Restaurar a leitura de avisos multipágina (`64c9578:readers/malha_reader.py`) | M | `raw_rows` traz as linhas da página 2 com `page = 2`; teste novo de continuação de tipo entre páginas |
| F0-08 | Trava no leitor: contar as linhas de todas as tabelas de aviso e falhar se a contagem divergir das linhas convertidas | P | PDF com linha ilegível → erro 422 com o número da linha |
| F0-09 | Restaurar as duas travas 409 de `calculate_tax` e adicionar o bloqueio de `pgdas_plan.validation.status != "VALID"` | P | Três testes de API retornam 409 com a mensagem esperada |
| F0-10 | Restaurar "todas as competências da malha no relatório" (`64c9578:services/client_report.py`) | P | Relatório de uma malha com 19 competências mostra 19 linhas |
| F0-11 | Backup automático antes do merge de malha (mitigação de P0-4 até a ADR-003) | P | Um evento registra o caminho do backup criado |
| F0-12 | Fonte única da versão (`checkfiscal/__version__`) lida por API, UI, `.bat`, launcher e compose; porta única | M | Um teste compara a versão nas 5 fontes |
| F0-13 | Reescrever os ~17 testes de UI por trecho de CSS minificado para verificar `id`/rotas estáveis, ou marcá-los `xfail` com motivo | M | Suíte verde sem depender de formatação do CSS |
| F0-14 | Remover o teste de hash de arquivo-fonte (`test_tax_calculator_files_were_not_changed`) e substituí-lo por casos de regressão fiscal | P | Mudança de CRLF não quebra a suíte |
| F0-15 | Corrigir `checkfiscal.spec` (`hiddenimports` com `app`, `database`, `readers.*`, `services.*`) e validar o build no Windows | M | O executável responde em `/api/health` em uma VM limpa |
| F0-16 | Primeiros 3 casos de regressão fiscal aprovados por contador (Tipo 17 simples; Tipo 17 com reflexo; só Tipo 01) | M | `tests/regression/cases/*/expected.json` assinados |
| T02 | Middleware Host/Origin/Sec-Fetch-Site (P0-S1), plano §6 | P | **FEITO** (`2974e87`, `e1f1c0b`, `0eba842`, `79ded57`). Ver [t02-implementation.md](t02-implementation.md) |
| T03 | Conexões SQLite sempre fechadas; restauração segura (DEF-001) | P | **FEITO** (`048aef5`). Ver [t03-sqlite-connections.md](t03-sqlite-connections.md). Divergência do plano: 409 em vez de `restart_required` |

## Fase 1 — Fundação

| ID | Tarefa | Tam. | Critério de aceite |
|---|---|---|---|
| F1-01 | Testes de caracterização: snapshot JSON das 15 rotas usadas pela UI para os casos de regressão | M | Os snapshots são comparados no CI |
| F1-02 | `shared_kernel.Competencia` e `Centavos` (com `Decimal`) e troca das 6 cópias de `month_index` | M | `grep month_index` restrito ao `shared_kernel`; testes de propriedade |
| F1-03 | `infrastructure/db.py`: unidade de trabalho com fechamento de conexão | M | Teste: exceção no meio do caso de uso → nada persistido |
| F1-04 | Máquina de estados única do processo; remover as 3 cópias de `app.py` | M | Uma tabela de transições testada; `confirm_analysis` passa a cobrir todos os estados |
| F1-05 | `pgdas.domain.LinhaDoTempoReceitas`: uma implementação da precedência, usada por análise, cobertura e imposto | M | As três funções antigas delegam; os testes existentes passam |
| F1-06 | Caso de uso `ImportPgdas` (manual e lote compartilham o código) | G | `upload_pgdas` e `upload_pgdas_auto` com menos de 30 linhas cada |
| F1-07 | Mover a mutação de `confirm_analysis` para `analysis.domain.apply_human_decision` | M | A rota não altera campos aninhados |
| F1-08 | Tornar o recálculo de plano explícito (`POST /api/process/{id}/refresh-plan`), com `GET` só de leitura | M | Nenhum `GET` grava; a UI chama o refresh ao abrir |
| F1-09 | Isolar `tax_segregation`, `tax_revenue_lines` (cálculo) e `annex_columns_profile` em `taxation/experimental` | P | Teste arquitetural impede import a partir de `api/` |
| F1-10 | Teste arquitetural de camadas (AST) | P | Falha se `domain` importar fastapi, sqlite3 ou pdfplumber |
| F1-11 | `TrustedHostMiddleware` + exigência de `X-CheckFiscal` nas rotas que alteram estado + verificação de `Origin` | P | POST simulando outra origem → 403; a UI continua funcionando |

## Fase 2 — Cadastro inteligente

| ID | Tarefa | Tam. | Critério de aceite |
|---|---|---|---|
| F2-01 | `integrations/http.py` (timeout, retry com backoff e jitter, `Retry-After`, token bucket, UA versionado) | M | Testes de falha com transporte falso |
| F2-02 | Migração `company_registry_lookups` + `company_field_provenance` + colunas opcionais | P | Banco 1.41 migra sem perda |
| F2-03 | Adaptador BrasilAPI + normalizador (incluindo a regra das datas do Simples sem opção) | M | Fixtures 200/404/503 sanitizadas |
| F2-04 | Adaptador ViaCEP (e fallback BrasilAPI CEP v2) | P | CEP divergente gera alerta, não sobrescreve |
| F2-05 | Caso de uso `LookupCnpj` com cache de 30 dias e fallback configurável | M | Offline → formulário manual em menos de 1 s |
| F2-06 | UI: preencher, indicar a fonte e a data, e revisar campo a campo; diff ao atualizar | M | Correção manual nunca é sobrescrita |
| F2-07 | (Opcional) Adaptador cnpj.ai com chave do operador em `keyring` | M | Sem chave → provedor ignorado; a chave nunca aparece em log nem no pacote de suporte |

## Fase 3 — Regras e auditabilidade

| ID | Tarefa | Tam. | Critério de aceite |
|---|---|---|---|
| F3-01 | Tabelas `process_revision` e `revision_document`; migrar os processos existentes para a "revisão 1" | G | Nova malha cria a revisão 2 sem apagar nada |
| F3-02 | `UNIQUE(process_id, sha256)` em `pgdas_documents` com saneamento das duplicatas | M | Reenvio do mesmo PDF → "repetido ignorado" |
| F3-03 | Extrair `declaration_number` e `transmitted_at` no leitor e definir a precedência por eles | M | Caso de regressão original × retificadora em ordem inversa produz a mesma RBT12 |
| F3-04 | Cache SQLite da Selic + valores mensais gravados no snapshot + paginação de 10 anos | M | Cálculo offline com meses em cache; reprodução idêntica |
| F3-05 ✅ | `input_fingerprint` e `rule_versions` no cálculo; bloquear relatório desatualizado (T08 concluída: `input_fingerprint.version` e `RULES`, sem campo `rule_versions` separado) | M | Upload posterior de PGDAS → relatório bloqueado com aviso. Ver `t08-fingerprints.md`. |
| F3-06 | Decisões humanas append-only (`analysis_decision`) | M | O histórico de decisões fica visível; a decisão em vigor é a mais recente |
| F3-07 | Conferência Tipo 01 × PGDAS exibida (sem imposto) | M | Divergência é exibida na análise; nenhum valor entra no cálculo |
| F3-08 | (Se aprovado em D1) Situação do PGDAS, 1.44 | M | Testes 1.44 restaurados e verdes |
| F3-09 | (Se aprovado em D1) Corte do último PGDAS transmitido, 1.45, reescrito de forma legível | G | Testes 1.45 restaurados e verdes; hipótese "zero" nunca alimenta o DAS |
| F3-10 | Tabelas do Simples versionadas por vigência (`annex_tables_2018`) | P | O cálculo grava a versão da tabela |

## Fase 4 — Integra Contador (prova de conceito)

| ID | Tarefa | Tam. | Critério de aceite |
|---|---|---|---|
| F4-01 | Estimar o custo com a tabela vigente da Loja Serpro para o volume do escritório | P | Planilha aprovada |
| F4-02 | Adaptador somente leitura `CONSDECLARACAO13` + `CONSULTIMADECREC14` | G | 10 declarações reais lidas pelo `pgdas_reader` com o mesmo resultado do upload manual |
| F4-03 | Verificação prévia de procuração (`OBTERPROCURACAO41`) | M | Procuração ausente → pendência clara, sem chamada paga desnecessária |

## Fase 5 e 6

| ID | Tarefa | Tam. | Critério de aceite |
|---|---|---|---|
| F5-01 | Relatório emitido imutável (`POST` emite, `GET` lê) com fontes e premissas | M | Reemissão gera uma versão nova; o hash é guardado |
| F5-02 | Aviso multa de mora × ofício e "anexo único" no relatório | P | Texto aprovado por contador |
| F6-01 | `requirements.lock` com hashes; seletor de Python no `.bat` | M | Instalação reprodutível |
| F6-02 | Dockerfile de distribuição não-root; compose de desenvolvimento separado | P | `docker compose -f compose.dev.yaml` mantém o reload |
| F6-03 | Retenção de backups + modo manutenção na restauração | M | Restaurar com a UI aberta não deixa conexões órfãs |
| F6-04 | Runbook de diagnóstico e recuperação | P | Documento revisado pelo suporte |
