# Avaliação de riscos

> Auditoria de 22/10/2026. Classificação:
> **P0**: pode gerar número fiscal errado entregue ao cliente, ou perda de dado sem recuperação.
> **P1**: risco de segurança, de consistência ou de operação com impacto real, mas com contorno.
> **P2**: manutenção, desempenho ou qualidade.

## P0 — Fiscal e integridade

| ID | Risco | Evidência | Cenário concreto | Mitigação proposta |
|---|---|---|---|---|
| P0-1 | **Leitor de malha ignora as páginas 2 em diante** | `readers/malha_reader.py:89` (`find_notice_table(pages[0])`), `:150` (`"page": 1`); revertido em `fe0679b` | Malha com 23 linhas, 4 delas na página 2 (inclusive Tipo 17 de 12/2025 e 06/2026, conforme `test_v143`): essas competências não entram no plano, na análise nem no relatório, e nenhum erro é exibido | Restaurar a leitura multipágina de `64c9578` e criar uma trava: contar as linhas de aviso em todas as páginas e falhar se a contagem divergir das linhas lidas |
| P0-2 | **Cálculo pode ser gravado como completo, com valor zero, sem cobertura do Tipo 17** | Travas removidas de `/api/calculate-tax` em `fe0679b`. Hoje só se verifica `analysis_requests_complete`, que considera apenas os pedidos **planejados** (`app.py:195–235`) | Se o plano estiver com `validation.status = "ERROR"` (competência sem cobertura) ou se P0-1 tiver perdido um mês, `missing_initial` fica vazio e o cálculo segue com o total `0` | Restaurar as duas travas e bloquear o cálculo quando `pgdas_plan.validation.status != "VALID"` |
| P0-3 | **Relatório do cliente omite competências da malha** | `services/client_report.py:191–199` filtra as linhas sem impacto; a correção 1.43 foi revertida | O cliente recebe um relatório sem as competências pendentes ou sem cálculo e conclui que foram analisadas | Restaurar "todas as competências da malha aparecem" e marcar as pendentes de forma explícita |
| P0-4 | **Nova malha apaga cálculos, decisões do contador e relatórios emitidos** | `database.invalidate_process_analysis` (`database.py:448`), chamada em `app.py:564` | O processo 125 teve um relatório entregue ao cliente. Uma nova malha chega, e o relatório e as revisões humanas que o explicavam são apagados de forma irreversível (só sobra o que estiver em backup) | Revisões de processo e preservação imutável (ADR-003). Até lá: backup automático antes do merge |
| P0-5 | **Cálculo sem vínculo com as entradas (desatualização silenciosa)** | `upload_pgdas` não invalida nem marca o cálculo; `GET /api/client-report` combina o último `tax_calculation` com a análise **recalculada agora** (`app.py:2064–2111`) | O imposto é calculado, depois um PGDAS retificador é enviado, e o relatório mostra linhas novas com totais antigos | Gravar no cálculo uma impressão digital das entradas (hashes dos PGDAS aceitos, plano, decisões) e bloquear o relatório se ela divergir |
| P0-6 | **Versão operacional ambígua** | `.bat`/launcher 1.41:8141; `compose.yaml`/`iniciar_docker.sh` "1.45":8145; release notes 1.42–1.45 descrevem regras ausentes | O escritório usa o Docker acreditando ter as travas da 1.43 | Decisão de baseline na Fase 0 e versão única exibida pela API |
| P0-7 | **Precedência inconsistente entre retificadora e original** | `tax_engine.build_revenue_timeline` (`:142–167`) e `analysis_engine.build_revenue_index` (`:25–49`): no histórico **o primeiro documento enviado vence**; no PA corrente, **o último vence**. `pgdas_documents` não guarda a versão da declaração | O PGDAS original de 03/2025 é enviado primeiro e a retificadora depois. O histórico de 02/2025 continua sendo o do original, e a RBT12 sai errada | Ordenar por data de transmissão da declaração (já extraída do PDF; confirmar o campo) e registrar original × retificadora |
| P0-8 | **Mesmo PGDAS aceito em duplicidade** | `/api/upload-pgdas` sempre insere (`database.save_pgdas_document`), sem `UNIQUE` | Duplicatas não mudam o índice hoje, mas inflam as contagens e combinam com P0-7 | `UNIQUE(process_id, sha256)` em uma migração aditiva, com tratamento das duplicatas existentes |

## Status de mitigação (Fase 0, 16/11/2026)

| ID | Status | Residual |
|---|---|---|
| **P0-S1** (CSRF / DNS rebinding na restauração e escrita) | **Mitigado** na T02 (`services/request_guard.py`, `phase0/integration`). Vetores de §2.4 do plano cobertos por testes | Trava só por processo; `Host` duplicado valida o primeiro; WebSocket não checado (app não tem rota); `https` bloqueado como `Origin` (ajustar se houver proxy TLS); navegador sem `Sec-Fetch-*` e GET sem `Origin` passam só pela regra de `Host`. Ver [t02-implementation.md](t02-implementation.md) |
| **DEF-001** (conexões SQLite não fechadas; restauração insegura) | **Corrigido** na T03 (`048aef5`) | Trava por processo (não multi-processo); documentos trocados por `rename` com pastas `.new`/`.old`. Ver [t03-sqlite-connections.md](t03-sqlite-connections.md) |
| P0-1 a P0-8 (fiscais e de integridade) | **Não tratados** (T04 em diante) | — |

## P1 — Segurança

| ID | Risco | Evidência | Mitigação |
|---|---|---|---|
| S-1 | **CSRF contra o servidor local** | Sem autenticação, sem verificação de `Origin`/`Host`. `POST /api/system/restore` e os uploads são multipart, ou seja, *simple requests* que o navegador envia **sem preflight** | Uma página maliciosa aberta pelo operador pode enviar um backup forjado e **substituir o banco**. Mitigar com: cabeçalho obrigatório (`X-CheckFiscal: 1`) nas rotas que alteram estado, validação de `Origin` e `TrustedHostMiddleware` (`127.0.0.1`, `localhost`) |
| S-2 | **DNS rebinding** | Sem validação de `Host` | Um site externo pode ler `/api/companies` (dados fiscais). Mesma mitigação de S-1 |
| S-3 | Backups e PDFs sem criptografia em repouso | `backup_service.create_backup`, `documents/` | Aceitável para a beta local; documentar que o disco precisa de BitLocker. Não guardar backup em pasta sincronizada sem criptografia |
| S-4 | Sem política de retenção de backup | `BACKUPS_DIR` só cresce; cada restauração cria um backup de segurança | Retenção configurável e aviso de LGPD (exclusão de empresa não atinge os backups) |
| S-5 | Restauração com o servidor em uso | `restore_backup` troca o arquivo do banco; `restart_required: True`, mas o processo continua atendendo | Colocar o app em modo manutenção e encerrar ou reabrir as conexões |
| S-6 | Exclusão de empresa apaga os arquivos antes do banco | `app.py:439–440` | Se `delete_company` falhar, o banco fica apontando para PDFs inexistentes. Inverter a ordem ou usar exclusão lógica |
| S-7 | Docker como root e com código montado | `compose.yaml` | Imagem de distribuição separada da de desenvolvimento, com `USER` não-root |
| S-8 | Credenciais futuras (Serpro) | Ainda não existem | **Nunca** embutir no executável. Ver `docs/integrations/fiscal-services.md` §6 |
| S-9 | Logs | Registram apenas o caminho da requisição (`app.py:332`). Mensagens de erro de leitura voltam ao cliente com `str(error)` | Risco baixo. Manter a regra de nunca registrar query string nem valores |

Pontos positivos verificados: bind em `127.0.0.1` nos lançadores e `127.0.0.1:8145` no compose; proteção contra path traversal no download (`file_storage.resolve_document_path`); proteção contra zip-slip na restauração (`backup_service._safe_extract`); limites de tamanho e de membros do backup; `integrity_check` antes de restaurar; HTML escapado no relatório e na UI (`escapeHtml`); pacote de suporte sem PDFs nem valores.

## P1 — Consistência e operação

| ID | Risco | Evidência |
|---|---|---|
| C-1 | Sem transação por caso de uso; falha no meio deixa o estado parcial | `app.upload_pgdas` faz 5 escritas em conexões separadas |
| C-2 | Transições de status duplicadas e divergentes | `dependency-map.md` §2 |
| C-3 | GET com escrita (`/api/client-report`, `/api/process/{id}`, `/api/companies/{id}`) | Prefetch do navegador ou recarregamento gera eventos e relatórios duplicados |
| C-4 | Suíte de testes quebrada e testes adaptados à regressão | `current-state.md` §5 |
| C-5 | Testes podem tocar o banco real do operador | `database.py:1330` executa `init_db()` no import; não há `conftest.py` |
| C-6 | Executável provavelmente não empacota `app.py` | `checkfiscal.spec` (NÃO VERIFICADO por build) |
| C-7 | O `.bat` instala dependências transitivas sem pin e aceita qualquer Python | `INICIAR_CHECKFISCAL_WINDOWS.bat` |
| C-8 | Selic sem cache e sem registro dos valores mensais usados | `legal_charges.py:106`; o resultado guarda a taxa agregada, mas não a série nem a data da consulta. Não é reprodutível de forma auditável |
| C-9 | Selic: consultas com janela de mais de 10 anos falham na API do BCB (limite desde 26/03/2025) | `fetch_bcb_monthly_selic` faz uma única chamada. É improvável dentro de 5 anos de decadência, mas não é tratado |
| C-10 | Tipo 01: o PGDAS é exigido, mas não é comparado | `analysis_engine.py:354–374`. O operador acredita que houve conferência |

## P1 — Domínio (validação por contador necessária)

| ID | Ponto | Observação |
|---|---|---|
| D-1 | Multa de mora × multa de ofício | O cenário "exposição" usa multa de mora (0,33% ao dia, até 20%). Em autuação, aplica-se multa de ofício (75%, art. 44 da Lei 9.430/1996). O relatório deve deixar claro que a estimativa pressupõe autorregularização |
| D-2 | RBT12 proporcional no início de atividade (LC 123, art. 18, §2º) | Não tratada |
| D-3 | Sublimite de R$ 3,6 milhões | Não tratado; o DAS estimado incluiria ICMS indevidamente |
| D-4 | Correção que ultrapassa R$ 4,8 milhões | Gera erro genérico, sem tratar o efeito de exclusão |
| D-5 | Janela de 24 meses de histórico no PGDAS (`HISTORY_MONTHS = 24`) | A premissa do planejador sobre quantos meses um PGDAS traz deve ser confirmada com documentos reais (`docs/leitor-pgdas-padroes-v2.md`) |
| D-6 | Malha do DF | Leitor e identidade específicos da SEEC-DF. Outras UFs exigem um novo leitor (adaptador) |

## P2 — Manutenção e desempenho

- `float` na conversão de valores monetários (`malha_reader.py:25`, `pgdas_reader.py:54`). O `round()` evita erro na prática, mas `Decimal` elimina a classe de bug.
- N+1 em `list_companies` (`database.py:546`): por empresa, 1 + 6 consultas.
- `upload_pgdas_auto` recalcula a análise a cada iteração do laço (`app.py:1047`).
- Conexões SQLite sem `close()` explícito.
- Cerca de 2.000 linhas de motor fiscal sem uso em produção.
- `index.html` com 3.350 linhas de JS inline, sem módulos.
- Testes de UI por trecho de string.
- User-Agent `CheckFiscal/1.11` desatualizado.
- `schema_migrations` sem uso real (`user_version` fixo em 2).
