# Fase 0 — Estabilização e recuperação da confiabilidade fiscal

> Plano de 22/10/2026, sobre `bf35530` (branch `fix/arquitetura`). Implementação parcial: ver **Status de execução** abaixo.
> Base: comparação integral `git diff 64c9578 fe0679b` (19 arquivos, +100/−553) e releitura das rotas afetadas.
> Decisões de entrada: restauração **seletiva**; sem migração de esquema; sem integrações externas; frontend intocado.

---

## Status de execução (16/11/2026)

- **Branches locais `phase0/*`** (sem merge em `fix/arquitetura`, sem push). Integração: `phase0/integration` em `79ded57`.
- **Concluídas:** T01 (`0a1b7e6`, `4b496c7`); C5 (`529fa2d`); T03 (`048aef5`, DEF-001 corrigido); T02 (`2974e87`, `e1f1c0b`, `0eba842`, `79ded57`).
- **Pendentes:** T04 a T14, D1 a D4, casos fiscais C1 a C15, DEF-002, fixtures de PDF sanitizadas, mudanças de interface.
- **Testes em `phase0/integration`:** alvo T01–T03 = 122 passam; suíte geral (`--ignore` do v145) = 247 passam / 33 falham; ordem invertida com a mesma lista de falhas; violações de isolamento = 0. Detalhes: [t02-implementation.md](t02-implementation.md), [t03-sqlite-connections.md](t03-sqlite-connections.md).
- **Política de origem/host:** [security-policy.md](security-policy.md) (não duplicada aqui).

---

## 1. Comparação `64c9578` (1.45) × `fe0679b` (1.41)

Cada trecho removido foi classificado em uma de quatro categorias:

- **CF**: correção fiscal comprovada; candidata à Fase 0.
- **FN**: funcionalidade nova, incompleta ou sem regra aprovada; adiada.
- **DS**: distribuição ou instalação; adiada (canais mantidos).
- **TV**: rótulo de versão ou teste.

| # | Arquivo | Trecho removido em `fe0679b` | Cat. | Finalidade original | Decisão Fase 0 |
|---|---|---|---|---|---|
| 1 | `readers/malha_reader.py:86–117` | Leitura de tabelas de aviso em **todas** as páginas; `page` real | CF | Não perder avisos que continuam na página 2 (1.43) | **Reimplementar** (não copiar; ver §2.1) |
| 2 | `app.py` `calculate_tax` | Trava 409: Tipo 17 com `AWAITING_PGDAS` | CF | Impedir "cálculo concluído = zero" quando o histórico do PGDAS não cobre o mês (1.43) | **Restaurar** |
| 3 | `app.py` `calculate_tax` | Trava 409: incremento esperado e `visible_impacts` vazio | CF | Impedir resultado vazio quando há diferença de faturamento (1.43) | **Restaurar adaptada** (ver §2.2) |
| 4 | `services/client_report.py` | Todas as competências da malha no relatório; ação "Tipo 17 pendente" | CF | Relatório não omitir competência (1.43) | **Restaurar** |
| 5 | `database.py` | Tabela e funções `pgdas_missing_status` | FN | Marcar o PGDAS como "não declarado / não localizado" (1.44) | Adiar (Fase 3); **não apagar** tabela existente |
| 6 | `database.py` | Tabela e funções `pgdas_last_transmitted` | FN | Corte no último PGDAS transmitido (1.45) | Adiar (Fase 3); **não apagar** tabela existente |
| 7 | `services/pgdas_planner.py` | `adapt_plan_to_last_transmitted` | FN | Não exigir PGDAS que não existe (empresa omissa) | Adiar; reescrever (código comprimido, depende da premissa de 24 meses) |
| 8 | `app.py` | `POST /last-transmitted-pgdas`, `POST /pgdas-situation`, `GET /partial-report` | FN | Interface das funcionalidades 5–7 e relatório parcial | Adiar com 5–7 |
| 9 | `app.py` `ensure_current_pgdas_plan`, uploads, `process_status` | Uso do corte e da situação | FN | Integração de 5–7 | Adiar |
| 10 | `static/index.html` | Seletor do último PGDAS, situação por cartão, botão de relatório parcial | FN | UI de 5–8 | Adiar (frontend fora da Fase 0) |
| 11 | `requirements.txt` | `uvicorn` (sem `[standard]`) | DS | Evitar compilação de dependências no Windows (1.42) | Adiar (Fase 6) |
| 12 | `INICIAR_*.bat`, `iniciar_linux_mac.sh`, `desktop_launcher.py` | Seletor de Python 3.11–3.13; porta 8145 | DS | Instalação robusta (1.42) | Adiar; manter canais |
| 13 | `app.py`, HTML, README, docs | Rótulos 1.45 | TV | — | Substituir por versão única nova (§4, T13) |
| 14 | `tests/*` | Asserções 1.45 trocadas para 1.41 | TV | — | Reescrever os testes por comportamento, não por número de versão |

Entre `fe0679b` e o HEAD (`bf35530`), só houve mudanças de cache/CSS em `app.py` e de marca em três serviços. **Não há conflito** com os trechos acima.

---

## 2. Achados novos desta comparação (não cobertos pela auditoria)

### 2.1 A leitura multipágina da 1.45 não pode ser copiada

| Defeito na 1.45 | Linha (`64c9578`) | Efeito |
|---|---|---|
| Se nenhuma página tem a tabela, `notice_tables = []` e a malha volta **vazia sem erro** | `malha_reader.py:89–93` | Hoje (1.41), `find_notice_table(pages[0])` lança "Tabela de Avisos não encontrada". A 1.45 **removeu essa falha explícita**: um PDF errado vira um processo sem competências e um plano "VALID" (`pgdas_planner.py:561`, `not malha_competences`) |
| `page_number` enumera **tabelas encontradas**, não páginas | `:116` | Uma página sem tabela no meio desloca a numeração; a proveniência fica errada |
| Detecta a continuação **só se a página 2 repetir o cabeçalho** | `:89–93` | Uma tabela de continuação sem cabeçalho continua sendo descartada em silêncio. **NÃO VERIFICADO** em quais PDFs da SEEC-DF o cabeçalho se repete |
| `notice_table[1:]` descarta a 1ª linha de cada tabela | `:117` | Correto só se toda tabela tiver cabeçalho |

### 2.2 A trava "incremento esperado sem impacto" da 1.45 tem falso positivo e falso negativo

- **Falso positivo:** com incremento pequeno, `money_times_rate` arredonda a diferença de DAS para 0 → `visible_impacts` vazio → 409 indevido.
- **Falso negativo:** se **uma** de várias competências corrigidas cair em `missing_months` e outra gerar impacto, `visible_impacts` não fica vazio e o resultado parcial é gravado.
- **Correção proposta:** exigir que **toda** competência com incremento esteja em `hidden_timeline` (calculada) e nenhuma em `missing_months`. É mais estrita, então exige o caso contábil C8/C9 (§7).

### 2.3 P0-9 (novo): a malha analisada difere entre as rotas

`build_analysis_context`/`analyze_process` recebem `process["malha"]` **sem** `normalize_malha_data` em cinco rotas:

| Rota | Linha | Malha usada |
|---|---|---|
| `POST /api/upload-pgdas`, `/upload-pgdas-auto`, `GET /api/process/{id}` | 675, 971, 1314 | normalizada (`ensure_current_pgdas_plan`) |
| `POST /api/confirm-analysis` | 1389 | **bruta** |
| `GET /api/tax-setup` | 1657 | **bruta** |
| `POST /api/calculate-tax` | 1747 | **bruta** |
| `POST /api/calculate-legal-charges` | 1932 | **bruta** (via contexto) |
| `GET /api/client-report` | 2028 | **bruta** |

`normalize_malha_data` existe justamente para que "a presença do Tipo 17 em uma linha bruta não desapareça porque `work_months` ficou desatualizada" (`pgdas_planner.py:62–67`). Para processos importados antes da normalização, **a tela pode mostrar uma competência Tipo 17 que o cálculo e o relatório não veem**. Malhas importadas pelo código atual já são gravadas normalizadas (`app.py:510`, `:551`), então o impacto depende dos dados existentes. Medir isso exige o diagnóstico somente leitura da T10.

### 2.4 CSRF: o vetor é mais amplo e a correção não exige mudar o frontend

FastAPI 0.116 só interpreta o corpo como JSON se o `Content-Type` for `application/json` (`.venv/.../fastapi/routing.py:253–265`). Situação por rota:

| Rota | Forma | Alcançável por *simple request* de outro site |
|---|---|---|
| `POST /api/system/restore` | multipart | **Sim**: substitui o banco |
| `POST /api/analyze-malha`, `/upload-pgdas`, `/upload-pgdas-auto` | multipart + query | **Sim** |
| `POST /api/confirm-analysis` | query | **Sim**: grava decisão "humana" |
| `POST /api/calculate-legal-charges` | query | **Sim** |
| `GET /api/system/backup`, `/support-bundle`, `/client-report` | GET com escrita | **Sim** (`<img src>`): enche o disco de backups e grava relatórios |
| `POST /api/companies`, `/calculate-tax` | JSON | **Sim** (correção de 22/10/2026): sem `Content-Type` (corpo `Blob`/`ArrayBuffer`), o FastAPI interpreta o corpo como JSON (`routing.py:255`); comprovado com 201 em banco temporário. Ver `t02-preparation.md` §6 |
| `PATCH /api/companies/{id}` | JSON | Não (PATCH exige preflight) |
| `DELETE /api/companies/{id}` | DELETE | Não (exige preflight) |

A UI chama tudo pela mesma origem com `fetch`/`location.href` (`static/index.html:880`, `1049`, `1182`, `1243`, `1404`, `1435`). Por isso, uma defesa **só no servidor** basta:

1. `Host` permitido (`127.0.0.1:<porta>`, `localhost:<porta>`; configurável por `CHECKFISCAL_ALLOWED_HOSTS`): bloqueia DNS rebinding.
2. Para métodos que alteram estado **e** para os GETs com escrita: se `Origin` estiver presente, precisa ser de um host permitido; se `Sec-Fetch-Site` estiver presente, precisa ser `same-origin` ou `none`. Requisições sem esses cabeçalhos (CLI, testes) passam. Navegadores modernos sempre enviam `Sec-Fetch-Site`.

### 2.5 Corrigir o leitor não corrige processos existentes

Uma malha já importada não é relida. `ensure_current_pgdas_plan` só recalcula o plano a partir do `malha_json` gravado. Reenviar o mesmo PDF é **ignorado** por SHA-256 (`malha_merge.malha_already_imported`). E se fosse aceito, o merge chamaria `invalidate_process_analysis` e **apagaria** os cálculos (P0-4). Daí a cadeia de dependências T09 → T10 (§4).

### 2.6 Precedência original × retificadora (P0-7): há evidência para detectar, não para decidir

O leitor já extrai `assessment_type` (Original/Retificadora) nos dois formatos, `transmitted_at` na declaração e `assessed_at` no extrato (`pgdas_reader.py:741–830`, `884–1013`). As datas são de natureza diferente: a regra de precedência automática fica para a Fase 3, com o caso C7. **Na Fase 0, só detectar o conflito e enviar para revisão humana.**

---

## 3. Matriz de correções P0

| ID | Problema | Arquivos | Causa | Atual | Esperado | Correção proposta | Risco | Testes | Aceite |
|---|---|---|---|---|---|---|---|---|---|
| **P0-S1** | Restauração e escrita via CSRF / DNS rebinding | `app.py` (middleware) | Sem validação de `Host`, `Origin` e `Sec-Fetch-Site` | Um site externo envia `POST /api/system/restore` e substitui o banco | Só a UI local altera estado | Middleware de §2.4; `restore` também valida o manifesto **antes** de criar o backup de segurança (hoje valida duas vezes; manter) | Bloquear acesso legítimo por outro host (ex.: Docker acessado por IP da LAN, que hoje nem é publicado) | API: `Host: evil.com` → 400; `Origin: https://evil.com` em restore/upload/confirm → 403; `Sec-Fetch-Site: cross-site` → 403; mesma origem → 200; sem cabeçalhos (CLI) → 200 | Os 6 vetores da tabela §2.4 bloqueados; UI sem alteração e funcionando |
| **P0-9** | Malha diferente entre rotas | `app.py` (`build_analysis_context`, `confirm_analysis`) | `normalize_malha_data` aplicado só em parte das rotas | Cálculo/relatório podem ignorar Tipo 17 visível na tela | Todas as rotas analisam a mesma malha normalizada | Normalizar dentro de `build_analysis_context` e em `confirm_analysis` (idempotente) **sem gravar** | Muito baixo: função idempotente, já usada | Unitário: `normalize(normalize(m)) == normalize(m)`; API: malha legada (só `raw_rows` com Tipo 17) → `calculate-tax` vê a competência | Mesma lista de competências em `/process`, `/tax-setup`, `/calculate-tax` e `/client-report` |
| **P0-1** | Leitor ignora as páginas 2+ | `readers/malha_reader.py` | `find_notice_table(pages[0])` | Avisos das páginas seguintes perdidos | Todas as páginas lidas; falha explícita se nada for encontrado ou se houver tabela suspeita não lida | Reimplementar: percorrer as páginas; aceitar tabela com cabeçalho; **sinalizar** (erro 422) página com tabela de 5 colunas com data `dd/mm/aaaa` na 2ª coluna e sem cabeçalho (continuação não reconhecida); manter o erro se nenhuma tabela for encontrada; `page` = índice real; versão do leitor → `1.1.0` | Médio: muda o plano das **novas** importações (desejado); continuação sem cabeçalho pode passar a gerar erro em PDFs que antes "funcionavam" pela metade | Fixtures: 1 página; 2 páginas com cabeçalho repetido; 2 páginas sem cabeçalho; tipo que continua na página 2 sem célula de tipo; PDF sem tabela → erro | `raw_row_count` igual ao total de linhas visíveis nas fixtures; zero perda silenciosa |
| **P0-2** | Cálculo "completo" sem cobertura do Tipo 17 | `app.py` `calculate_tax` | Travas removidas em `fe0679b` | Total 0 gravado com Tipo 17 em `AWAITING_PGDAS` | 409 explicando o que falta | (a) restaurar a trava do Tipo 17 aguardando; (b) trava adaptada §2.2; (c) 409 se `pgdas_plan.validation.status != "VALID"` | Médio: pode bloquear processos que hoje "calculam" (esse é o objetivo); (b) bloqueia empresas com menos de 12 meses de histórico até a regra proporcional existir | 409 em: Tipo 17 aguardando; correção em `missing_months`; plano `ERROR`. 200 com incremento pequeno e diferença 0 | Nenhum `tax_calculation` gravado sem cobertura das competências com incremento |
| **P0-3** | Relatório omite competências | `services/client_report.py` | Filtro `relevant_rows`; a linha "Tipo 17 pendente" foi removida | Linhas de Tipo 17 sem PGDAS (sem Tipo 01) não aparecem | Toda competência da malha aparece; pendências explícitas | Restaurar o bloco da 1.45 (`normalize_malha_data` + inclusão + ordenação + `malha_competence_count`) e a ação "Tipo 17 pendente" | Baixo: só apresentação; texto para o cliente precisa de aprovação (C13) | Malha com N competências → N linhas; Tipo 17 sem PGDAS → texto de pendência; competências ordenadas por ano/mês | `len(competence_rows) == malha_competence_count` |
| **P0-5** | Relatório com cálculo desatualizado | `app.py` (`calculate_tax`, `calculate_legal_charges`, `client_report`) | O cálculo não registra as entradas | PGDAS novo após o cálculo → relatório mistura dados | Relatório bloqueado até recalcular | Gravar `input_fingerprint` **dentro** de `calculation_json` (sem mudar o esquema): SHA-256 de {sha256 dos PGDAS aceitos, linhas da malha normalizada, decisões, anexo, cenário}. Os encargos guardam o `input_fingerprint` do cálculo base. O relatório compara e responde 409 se divergir ou se faltar (cálculo legado) | Médio: processos com cálculo antigo exigirão recálculo para emitir relatório | Calcular → enviar PGDAS → relatório 409; recalcular → 200; cálculo legado → 409 com mensagem "recalcule" | Nenhum relatório emitido com fingerprint divergente |
| **P0-4** | Merge apaga histórico | `app.py:564`, `services/backup_service.py` | `invalidate_process_analysis` faz DELETE | Perda irreversível de cálculos e relatórios | Recuperável enquanto a ADR-003 não chega | Antes de `invalidate_process_analysis`: snapshot **só do banco** (`sqlite3.backup`) em `backups/pre-merge/`, registrado no evento; o merge aborta se o snapshot falhar | Baixo: espaço em disco | O merge cria o snapshot; falha no snapshot impede o merge; o snapshot restaura os cálculos apagados | Todo merge com dados derivados tem snapshot referenciado no evento |
| **P0-8** | PGDAS duplicado | `app.py` `upload_pgdas` | Sem verificação de período/sha antes do insert | Dois registros aceitos | Reenvio idêntico ignorado | Na rota manual, antes de `save_pgdas_document`: se já houver aceito com o mesmo `sha256` no processo → status `ALREADY_RECEIVED` (como no lote) | Baixo | Mesmo PDF 2× → 1 registro; PDF diferente do mesmo PA → segue para a regra P0-7 | Contagem de aceitos não cresce com reenvio idêntico |
| **P0-7** | Original × retificadora sem regra | `services/analysis_engine.py` (detecção) | Precedência implícita pela ordem de upload | Valor escolhido em silêncio | Conflito → revisão humana | Detecção: se dois documentos aceitos trazem **valores diferentes** para a mesma competência (PA corrente ou histórico), adicionar warning → `REVIEW_REQUIRED`. **Sem** mudar a precedência | Médio: processos com retificadora passam a pedir revisão | Original + retificadora com valores iguais → sem revisão; com valores diferentes → `REVIEW_REQUIRED` com as duas fontes | Nenhuma escolha silenciosa entre valores divergentes |
| **P0-6** | Versão ambígua | `app.py`, `static/index.html` (rótulos), `.bat`, `iniciar_*.sh`, `desktop_launcher.py`, `README.md` | Rótulos em 6 lugares | 1.41 / "1.45" | Uma versão em todos os canais | `VERSION` (arquivo) lido por `app.py`; rótulo da UI vindo de `/api/health` **ou** editado (é texto, não lógica); proposta **1.46.0** (maior que 1.45, para quem rodou a 1.45). Portas mantidas por canal | Baixo | Um teste compara `VERSION` com API, `.bat`, scripts e o rótulo HTML | Nenhuma string "1.41"/"1.45" de versão operacional fora do histórico |

P0-2(b), P0-3 e P0-7 alteram o que o operador vê ou o que fica bloqueado, **não** fórmulas. Mesmo assim, entram só após os casos contábeis da §7.

---

## 4. Tarefas, ordem e rollback

**Premissas de rollback:**
- Fase 0 **sem migração de esquema**. Toda tarefa pode ser revertida por `git revert` do seu próprio commit (quando commits forem autorizados).
- Dados novos são retrocompatíveis: o campo extra em `calculation_json` é ignorado pelo código antigo; arquivos de snapshot são inertes.
- As travas de cálculo e a checagem de origem ganham chave de desligamento por variável de ambiente (`CHECKFISCAL_CALC_GUARDS=0`, `CHECKFISCAL_ORIGIN_CHECK=0`), **documentadas só para suporte**, para destravar o escritório sem um novo build.

| Ordem | Tarefa | Depende de | Arquivos | Tam. | Rollback |
|---|---|---|---|---|---|
| **Sequência A — Segurança da execução e dos dados** ||||||
| T01 | Isolamento total dos testes (§5) + `httpx` em `requirements-dev.txt` | — | `tests/conftest.py` (novo), `requirements-dev.txt` | P | Apagar o conftest |
| T02 | Middleware Host/Origin/Sec-Fetch-Site (P0-S1) | T01 | `app.py` (+ `services/request_guard.py` novo) | P | Revert / `CHECKFISCAL_ORIGIN_CHECK=0` |
| T03 | Restauração: bloquear restore concorrente (lock de processo) e devolver `restart_required` com instrução clara | T02 | `services/backup_service.py`, `app.py` | P | Revert |
| **Sequência B — Mesma malha em todo lugar** ||||||
| T04 | Normalização em todas as rotas de análise (P0-9) | T01 | `app.py` | P | Revert |
| **Sequência C — Travas de cálculo e relatório** ||||||
| T05 | Travas de cálculo (P0-2 a, c) | T04 | `app.py` | P | Revert / flag |
| T06 | Trava adaptada "toda correção calculada" (P0-2 b) | T05, **casos C8/C9 aprovados** | `app.py` | P | Revert / flag |
| T07 | Relatório com todas as competências (P0-3) | T04, **C13 aprovado** | `services/client_report.py` | P | Revert |
| T08 | Fingerprint de entradas e bloqueio de relatório desatualizado (P0-5) | T04, T11 | `app.py`, `services/process_fingerprint.py` (novo) | M | Revert (os campos gravados ficam inertes) |
| **Sequência D — Preservação e documentos** ||||||
| T09 | Snapshot do banco antes do merge (P0-4) | T01 | `app.py`, `services/backup_service.py` | P | Revert |
| T11 | Deduplicação no upload manual (P0-8) | T01 | `app.py` | P | Revert |
| T12 | Detecção de conflito entre versões do PGDAS (P0-7) | T11, **C7 aprovado** | `services/analysis_engine.py` | M | Revert |
| **Sequência E — Leitor** ||||||
| T05R | Leitor multipágina reimplementado (P0-1) | T01, **fixtures de PDF (bloqueador)** | `readers/malha_reader.py`, `tests/fixtures/pdf/` | M | Revert (malhas lidas pelo 1.1.0 continuam válidas para o código antigo: mesmo formato) |
| T10 | Diagnóstico **somente leitura**: relê os PDFs de malha armazenados com o leitor novo e compara com o `malha_json` gravado (linhas, competências, tipos); mede também P0-9 e o uso das tabelas 1.44/1.45. Gera relatório; **não grava** | T05R, T04 | `tools/diagnose_malhas.py` (novo) | M | Apagar o script |
| T10b | Reprocessamento opcional por processo (opt-in do operador), passando por T09 | T10, T09, aprovação | `app.py` | M | Revert + snapshot pré-merge |
| **Sequência F — Versão e suíte** ||||||
| T13 | Versão única 1.46.0 (P0-6) | todas acima | `VERSION`, `app.py`, lançadores, `README.md`, rótulo HTML | P | Revert |
| T14 | Testes por comportamento no lugar de trechos de CSS (21 testes) e de hash de arquivo | T01 | `tests/*` | M | Revert |

**Dependências que evitam restauração parcial inconsistente:**
- Copiar o `app.py` da 1.45 inteiro quebra no import (as funções 1.44/1.45 não existem no banco). **Só aplicar os blocos das travas.**
- Copiar o `index.html` da 1.45 chamaria rotas inexistentes. **Fora da Fase 0.**
- Copiar o leitor da 1.45 introduz o erro "malha vazia sem erro" (§2.1).
- T05/T06/T07 sem T04 protegem só metade das rotas.
- T10b sem T09 apaga os cálculos ao reprocessar.
- T08 antes de T11 gera fingerprints diferentes para o mesmo conjunto de documentos (por causa das duplicatas).
- Restaurar os testes da 1.45 sem reescrever reintroduz asserções de versão e porta.
- O banco de quem rodou a 1.45 tem `pgdas_missing_status`/`pgdas_last_transmitted`: **nenhuma tarefa pode apagá-las**; T10 informa se contêm linhas (marcações que a 1.41 hoje ignora).

---

## 5. Estratégia de testes com banco temporário isolado

Problema atual: `services/runtime_paths.py` resolve `DATA_DIR`/`DB_PATH` **no import**, e `database`, `backup_service` e `support_bundle` copiam essas constantes. O `monkeypatch` em `database.DB_PATH` (padrão atual) não alcança `backup_service.DB_PATH`. Um teste de restauração sem isolamento **sobrescreveria o banco real**.

Desenho de `tests/conftest.py`:

1. `pytest_configure` (roda antes de importar qualquer módulo de teste): cria `tempfile.mkdtemp(prefix="checkfiscal-test-")` e define `CHECKFISCAL_DATA_DIR` e `CHECKFISCAL_DB_PATH` dentro dele.
2. **Canário obrigatório** (fixture `autouse`, escopo de sessão): importa `services.runtime_paths`, `database`, `backup_service`, `support_bundle` e **aborta a sessão** (`pytest.exit`) se qualquer `DB_PATH`, `DATA_DIR` ou `DOCUMENTS_DIR` não estiver dentro do diretório temporário, ou se apontar para `%LOCALAPPDATA%\CheckFiscal` ou para `<repo>/checkfiscal_data`.
3. Fixture `fresh_data` (`autouse`, escopo de função): apaga o conteúdo do diretório temporário (banco, `-wal`, `-shm`, `documents/`, `backups/`) e chama `database.init_db()`. Como todos os módulos apontam para o mesmo caminho, os testes ficam isolados sem `monkeypatch` de constantes.
4. **Rede bloqueada** (`autouse`): `urllib.request.urlopen` e `socket.create_connection` substituídos por funções que falham. Os testes de encargos passam `monthly_selic` explícito (a assinatura já permite: `legal_charges.py:276`).
5. Ao final da sessão: verificar que o `mtime` do banco real (se existir) não mudou, e remover o diretório temporário.
6. Os testes atuais que fazem `monkeypatch` de `DB_PATH` continuam funcionando, porque apontam para outro arquivo dentro de `tmp_path`.
7. PDFs: `tests/fixtures/pdf/` com **amostras anonimizadas com consentimento do escritório** (preferencial) e PDFs sintéticos para casos-limite (sem tabela, continuação sem cabeçalho). Proibido referenciar `/mnt/data` ou qualquer caminho absoluto; um teste de varredura garante isso.

Execução padrão: `python -m pytest -p no:cacheprovider`. Nenhuma variável manual é necessária.

---

## 6. Testes por tarefa

| Tarefa | Testes novos |
|---|---|
| T01 | Canário; teste que tenta abrir o banco real e falha; rede bloqueada |
| T02 | 6 vetores bloqueados (§2.4); mesma origem permitida; CLI sem cabeçalhos permitida; `TestClient` com `Host` configurado |
| T03 | Restauração concorrente → 409; backup inválido não cria backup de segurança desnecessário |
| T04 | Malha legada (só `raw_rows`) → mesmas competências em 5 rotas |
| T05/T06 | Matriz de 409 e 200 de P0-2 |
| T07 | N competências → N linhas; texto de pendência |
| T08 | Desatualização detectada; cálculo legado → 409 |
| T09 | Snapshot criado e referenciado; falha impede merge |
| T11 | Reenvio idêntico ignorado |
| T12 | Conflito com valores diferentes → revisão |
| T05R | 5 fixtures de leitor; contagem exata de linhas; página real |
| T10 | O script não altera o `mtime` nem o hash do banco de teste |
| T13 | Versão consistente nos 6 lugares |

Regressão geral ao fim de cada tarefa: suíte completa verde **exceto** os testes marcados `xfail(strict=True)` com o motivo, até a T14.

---

## 7. Casos fiscais que exigem aprovação de um contador

Cada caso deve virar `tests/regression/cases/<id>/` com entrada, saída esperada e o nome do aprovador. **Até a aprovação, o resultado do sistema não deve ser considerado correto.**

| Caso | Situação | O que aprovar | Afeta |
|---|---|---|---|
| C1 | Tipo 17, declarado < considerado, Anexo I, sem mudança de faixa | Incremento = considerado − declarado; DAS da diferença | Base |
| C2 | Tipo 17 com mudança de faixa nos 12 meses seguintes | Reflexos da RBT12 mês a mês | Base |
| C3 | Tipo 17 com declarado ≥ considerado | Sem exposição (`NO_ACTION_REQUIRED`) | Base |
| C4 | Só Tipo 01 | Nenhum imposto; PGDAS só para conferência; texto ao cliente | P0-3 |
| C5 | Tipo 01 e 17 na mesma competência com "considerado" diferente | Revisão humana obrigatória | Base |
| C6 | Malha com aviso que continua na página 2 sem repetir o tipo | Herdar o tipo da linha anterior está correto? | P0-1 |
| C7 | Original e retificadora do mesmo PA ou com histórico divergente | Qual prevalece; quando exigir revisão | P0-7 |
| C8 | Empresa com menos de 12 meses (histórico insuficiente) | Bloquear (proposta) × RBT12 proporcional (LC 123, art. 18, §2º) | P0-2(b) |
| C9 | Incremento pequeno cuja diferença de DAS arredonda para 0 | Aceitar o resultado zero como calculado | P0-2(b) |
| C10 | Vencimento em fim de semana ou feriado; pagamento no mês do vencimento; Selic do mês anterior ainda não publicada | Datas, juros de 0% e 1%, erro explícito | Encargos |
| C11 | Correção em 2026 com reflexos em 2027 | Resultado parcial e mensagem | Cálculo |
| C12 | RBT12 corrigida acima de R$ 3,6 milhões | Aviso de sublimite (o DAS estimado inclui ICMS indevidamente) | Cálculo |
| C13 | Texto do relatório para competências pendentes e sem exposição | Redação ao cliente ("sem presumir pagamento devido") | P0-3 |
| C14 | Malha com identidade só por nome (sem CFDF) | Limiar de 0,78 aceitável ou exigir confirmação | Identidade |
| C15 | Multa de mora × multa de ofício no cenário "exposição" | Texto de premissa no relatório | Relatório |

---

## 8. Coerência dos documentos da auditoria

| # | Documento | Afirmação | Problema | Correção proposta |
|---|---|---|---|---|
| 1 | `risk-assessment.md` P0-1; `implementation-backlog.md` F0-07; `migration-plan.md` D1 | "Restaurar a leitura multipágina de `64c9578`" | Contradiz §2.1: a versão 1.45 tem defeitos | "Reimplementar com base na 1.45, mantendo o erro explícito" |
| 2 | `implementation-backlog.md` F0-08 | "Contar linhas de todas as tabelas de aviso" | Circular: tabela não detectada não é contada | Detectar tabelas suspeitas (5 colunas + data) sem cabeçalho |
| 3 | `risk-assessment.md` P0-2 | Cenário principal "plano com `validation.status = ERROR`" | O planejador cobre todas as competências por construção; o gatilho realista é a **premissa de 24 meses de histórico** (D-5) ou P0-1 | Reescrever o cenário |
| 4 | `risk-assessment.md` P0-2; F0-09 | "Restaurar as duas travas" | A trava 2 da 1.45 tem falso positivo e falso negativo (§2.2) | "Restaurar a 1 e adaptar a 2" |
| 5 | `current-state.md` §4; `risk-assessment.md` P0-3 | "Oculta as linhas sem impacto" | Impreciso: oculta só as competências **Tipo 17 sem PGDAS e sem Tipo 01**; com P0-2 corrigido, isso ocorre principalmente em processos legados (P0-9) | Precisar a descrição e a severidade |
| 6 | `current-state.md` §5 | "6 testes dependem de `/mnt/data`"; "cerca de 17 testes de UI" | Contagem real: 5 falhas por PDF ausente + 1 falso verde (`test_v143`), e 5 arquivos referenciam `/mnt/data`; **21** falhas de UI por trecho de string | Corrigir números (também em F0-13) |
| 7 | `risk-assessment.md` S-1 | Mitigação "cabeçalho obrigatório `X-CheckFiscal`" | Exige mudar o frontend (vedado na Fase 0) e omite os vetores por query string e GET com escrita | Usar §2.4 (só servidor) e listar todos os vetores |
| 8 | Todos | Lista de P0 sem P0-9 | Achado novo (§2.3) | Incluir P0-9 |
| 9 | `current-state.md` §1 | "três correções fiscais" removidas | São quatro, se o leitor multipágina for contado como correção fiscal (é tratado em separado no fato 2) | Unificar a contagem |
| 10 | `risk-assessment.md` P0-7 | "Data de transmissão já extraída (confirmar)" | Confirmado: `transmitted_at` (declaração), `assessed_at` + `assessment_type` (extrato); são datas de natureza diferente | Registrar e manter a decisão na Fase 3 |
| 11 | `implementation-backlog.md` F0-11 | "Backup automático antes do merge" (backup completo com PDFs) | Pesado; o necessário é o banco | Snapshot só do banco (T09) |
| 12 | `migration-plan.md` F0 | "Versão única" sem número | — | Propor 1.46.0 (§3, P0-6) |

Nenhuma contradição foi encontrada em `api-catalog.md`, `company-registry.md`, `fiscal-services.md` nem nas ADRs (fora do escopo da Fase 0).

---

## 9. Primeira tarefa recomendada: T01 (isolamento dos testes)

**Por que antes da vulnerabilidade de restauração:** o teste da correção de P0-S1 precisa chamar `POST /api/system/restore`. Sem o isolamento, `backup_service.DB_PATH` aponta para o banco real (`%LOCALAPPDATA%\CheckFiscal\checkfiscal.db`, presente nesta máquina) e o teste **sobrescreveria os dados dos clientes**. T01 e T02 formam a primeira sequência e devem ser revisadas juntas.

- **Arquivos:** `tests/conftest.py` (novo) e `requirements-dev.txt` (+`httpx`). Nenhum arquivo de produção é alterado.
- **Validação:**
  1. Teste canário: a sessão aborta se algum caminho de dados estiver fora do diretório temporário.
  2. Teste de rede bloqueada: `fetch_bcb_monthly_selic` sem `monthly_selic` falha com `LegalChargesError`, sem chamada externa.
  3. `test_commercial_hardening.py`, `test_company_delete_api.py` e `test_v144_missing_pgdas.py` passam a ser **coletados** (antes: erro de `httpx`).
  4. Hash e `mtime` de `%LOCALAPPDATA%\CheckFiscal\checkfiscal.db` iguais antes e depois de rodar a suíte.
- **Aceite:** zero erros de coleta por `httpx`; a suíte roda sem nenhuma variável de ambiente manual; o banco real fica intocado (item 4).

Em seguida, a **T02**, com os 6 vetores de §2.4 como testes de aceitação.

## 10. T08: concluída

- **O que foi feito:** fingerprints de análise, imposto e encargos (`services/fingerprints.py`), estados `ATUALIZADO` / `DESATUALIZADO` / `PENDENTE_DE_DADOS` / `NAO_CALCULADO`, bloqueio do relatório (409 `CALCULATION_OUTDATED`) e dos encargos (409 `TAX_OUTDATED`). Detalhes em `t08-fingerprints.md`.
- **Testes:** 34 novos (`test_t08_fingerprints.py`, `test_t08_api.py`, `test_t08_flow.py`), todos passando. Suíte geral: 323 passam e 33 falham, as mesmas 33 da baseline (ver `t08-test-report.md`).
- **Divergências do plano:** o módulo ficou em `services/fingerprints.py` (o plano citava `services/process_fingerprint.py`). Não há `rule_versions` gravado; a versão das regras vai em `input_fingerprint.version` e nas constantes `RULES`.
- **Limites:** a Selic publicada depois do cálculo não é detectada offline (depende do cache de F3-04). O estado depende da data de hoje, e os testes de API fixam a data.
- **Próximo:** T09 e T11 (dependências em `t08-t09-t11-dependencias.md`). Upload e confirmação não invalidam nada: só mudam o estado.
