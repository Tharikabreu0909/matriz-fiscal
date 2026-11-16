# Plano de migração incremental

> Pré-requisito de todas as fases: **backup completo** (`/api/system/backup`) de cada instalação antes de atualizar.
> Nenhuma fase altera fórmula fiscal sem um caso de regressão aprovado por contador.

## Decisões que precisam do responsável antes da Fase 0 terminar

| # | Decisão | Opções | Recomendação |
|---|---|---|---|
| D1 | O que fazer com a reversão `fe0679b` | (a) manter a 1.41; (b) restaurar tudo de `64c9578`; (c) restaurar **seletivamente** | **(c)**: restaurar já as **correções de segurança fiscal** (leitor multipágina, duas travas de cálculo, relatório completo) e tratar as **funcionalidades** 1.44/1.45 (situação do PGDAS, corte do último transmitido) como itens da Fase 3, com caso de regressão aprovado |
| D2 | Motivo da reversão | Perguntar ao autor do commit `fe0679b` | Registrar a resposta em `jarvis_docs/activeContext.md` |
| D3 | Escopo geográfico | Só DF × multi-UF | Só DF agora; leitor como adaptador para permitir outras UFs depois |
| D4 | Canal de distribuição oficial | `.bat` + venv, executável, Docker | Executável **ou** `.bat` como canal do operador; Docker só para desenvolvimento e suporte |

---

## Fase 0 — Estabilização (baseline segura)

- **Objetivo:** uma versão única, conhecida, testável e sem as regressões P0-1 a P0-3.
- **Dependências:** D1, D2.
- **Arquivos afetados:** `requirements-dev.txt` (+`httpx`, +`pytest-cov`), novo `tests/conftest.py`, `tests/fixtures/pdf/` (PDFs sanitizados), `readers/malha_reader.py`, `app.py` (travas em `calculate_tax`), `services/client_report.py`, `app.py`/`.bat`/`desktop_launcher.py`/`compose.yaml`/`iniciar_docker.sh` (versão e porta únicas), `checkfiscal.spec`.
- **Tarefas:** ver backlog `F0-*`.
- **Riscos:** a reintrodução da leitura multipágina muda o plano de processos existentes (`ensure_current_pgdas_plan` recalcula ao abrir). Isso é **desejado**, mas precisa ser comunicado: competências novas aparecerão.
- **Complexidade:** baixa a média. **Prioridade:** máxima.
- **Rollback:** tag `baseline-1.41-bf35530` antes de começar; o banco não muda de esquema nesta fase (as tabelas 1.44/1.45 só são criadas se D1 = b).
- **Testes necessários:** a suíte inteira rodando no CI local sem acesso a `/mnt/data`; testes do leitor multipágina com fixture versionada; testes das travas 409; teste "relatório contém todas as competências".
- **Critérios de aceite:**
  - `pytest` sem erros de coleta; nenhum teste depende de caminho absoluto externo; nenhum `return` silencioso.
  - `GET /api/health` → a mesma versão do `.bat`, do launcher, do compose e da UI.
  - Malha de várias páginas: a contagem de linhas lidas é igual à contagem de linhas da tabela em todas as páginas.
  - Cálculo com competência Tipo 17 `AWAITING_PGDAS` ou plano `ERROR` → HTTP 409.
  - O executável gerado abre e responde em `/api/health` em uma máquina Windows limpa.

## Fase 1 — Fundação arquitetural

- **Objetivo:** criar a estrutura modular e mover a orquestração para casos de uso **sem mudar comportamento**.
- **Dependências:** Fase 0 verde.
- **Arquivos afetados:** novo pacote `checkfiscal/`; `app.py` vira shim; `database.py` vira `infrastructure/db.py` + repositórios; `services/*` são movidos para `*/domain` com re-exports temporários nos caminhos antigos (para os testes atuais seguirem passando).
- **Ordem:** `shared_kernel` (Competencia, Centavos) → `processes` (máquina de estados única, eliminando as 3 cópias) → `pgdas` (LinhaDoTempoReceitas **única**) → `analysis` → `taxation` → `reports` → `company_registry` → `system`.
- **Riscos:** quebrar o contrato JSON da UI. Mitigação: **testes de caracterização** (snapshot das respostas JSON dos endpoints para os casos de regressão) **antes** de mover cada rota.
- **Complexidade:** média a alta. **Prioridade:** alta.
- **Rollback:** cada módulo migrado é um PR separado; o shim permite voltar a rota para a implementação antiga.
- **Testes:** caracterização de endpoint; teste arquitetural de imports; unidade de trabalho com rollback.
- **Critérios de aceite:** respostas JSON idênticas às do snapshot; `app.py` com menos de 100 linhas; nenhum GET grava (exceto o recálculo de plano, que passa a ser explícito); uma transação por caso de uso.

## Fase 2 — Cadastro inteligente

- **Objetivo:** cadastro por CNPJ com BrasilAPI, ViaCEP, cache, revisão e proveniência.
- **Dependências:** Fase 1 (`company_registry`, `integrations/http.py`). ADR-002 aprovada.
- **Arquivos afetados:** `company_registry/*`, `integrations/brasilapi.py`, `viacep.py`, `cnpjai.py` (opcional), migração `000N_company_registry.sql`, `static/index.html` (formulário).
- **Riscos:** indisponibilidade do provedor (mitigada pelo modo offline); dado defasado (rótulo de origem e data); LGPD do QSA (não persistir).
- **Complexidade:** média. **Prioridade:** alta (maior redução de trabalho manual por esforço).
- **Rollback:** feature flag `registry.lookup_enabled = false` volta ao formulário manual; a migração é aditiva.
- **Testes:** contrato com fixtures gravadas; falhas (timeout, 429, 503, JSON inválido); regra de override manual.
- **Critérios de aceite:** com a internet desligada, o cadastro funciona manualmente; com internet, o formulário é preenchido em menos de 3 s no p95 com indicação de fonte; uma correção manual nunca é sobrescrita; cada campo salvo tem origem e data.

## Fase 3 — Regras e automações fiscais

- **Objetivo:** consolidar os motores fiscais, a auditabilidade e as funcionalidades 1.44/1.45 aprovadas.
- **Dependências:** Fase 1; casos de regressão aprovados por contador; ADR-003 aprovada.
- **Tarefas principais:** revisões de processo e snapshots (ADR-003); precedência por data de transmissão (P0-7); `UNIQUE` de documentos (P0-8); Selic com cache e valores gravados (C-8) e paginação de 10 anos (C-9); conferência Tipo 01 × PGDAS **exibida**, sem imposto (C-10); situação do PGDAS (1.44) e corte do último transmitido (1.45), se aprovados; tabelas do Simples versionadas por vigência.
- **Riscos:** mudança de número em processos existentes. Toda diferença em caso de regressão exige aprovação explícita.
- **Complexidade:** alta. **Prioridade:** alta.
- **Rollback:** migrações aditivas; os processos antigos viram "revisão 1" sem alteração de dados; a flag por funcionalidade (1.44/1.45) pode ser desligada.
- **Testes:** regressão fiscal; migração de banco 1.41 e 1.45; Selic offline com cache; reprodução de cálculo a partir do snapshot.
- **Critérios de aceite:** recalcular a partir do snapshot gera o mesmo valor ao centavo; uma nova malha não apaga nada; o relatório é bloqueado com cálculo desatualizado; nenhuma diferença não aprovada nos casos de regressão.

## Fase 4 — Integrações oficiais (estudo e prova de conceito)

- **Objetivo:** decidir com dados se o Integra Contador compensa.
- **Dependências:** Fases 0 a 3; aprovação de custo; contrato Serpro; e-CNPJ; procurações 00146.
- **Escopo da prova de conceito:** **somente leitura**: `CONSDECLARACAO13` (índice, situação de malha, DAS pago) e `CONSULTIMADECREC14` (PDF). Sem `TRANSDECLARACAO11` e sem emissão de DAS.
- **Riscos:** layout do PDF da API diferente do PDF do portal; custo por consulta; credenciais na máquina local.
- **Complexidade:** média. **Prioridade:** média.
- **Rollback:** a integração é opcional, atrás de uma flag; o upload manual continua sendo o caminho padrão.
- **Critérios de aceite:** 100% dos PDFs obtidos pela API lidos pelo `pgdas_reader` com o mesmo resultado do PDF do portal, em pelo menos 10 declarações reais; custo mensal estimado e aprovado; nenhum segredo fora do Credential Manager.

## Fase 5 — Auditoria e relatórios

- **Objetivo:** relatório emitido imutável com fontes, premissas, limitações, competências analisadas e pendências.
- **Dependências:** Fase 3 (snapshots).
- **Arquivos:** `reports/*`, `static/index.html` (lista de relatórios emitidos).
- **Critérios de aceite:** o relatório mostra todas as competências da malha; lista as fontes (sha e nome) e as premissas (anexo único, vencimento estimado, multa de mora × ofício); reemitir gera uma nova versão sem alterar a anterior; o hash do HTML é guardado.
- **Rollback:** a rota antiga de relatório fica disponível como "pré-visualização".

## Fase 6 — Distribuição e operação

- **Objetivo:** instalação limpa e atualização confiáveis nos canais escolhidos (D4).
- **Tarefas:** `.spec` com o pacote `checkfiscal` e verificação de build no CI (Windows); seletor de Python 3.11–3.13 no `.bat` (recuperar da 1.42); `requirements.lock` com hashes; imagem Docker de distribuição separada da de desenvolvimento, com usuário não-root; `TrustedHostMiddleware` e verificação de Origin (S-1, S-2); retenção de backups; modo manutenção na restauração; runbook de diagnóstico e recuperação.
- **Critérios de aceite:** instalação limpa em Windows 10/11 sem Python pré-instalado (executável); atualização sobre um banco 1.41 e um banco 1.45 sem perda (contagens iguais, `integrity_check` = ok); POST de outra origem → 403.
- **Rollback:** o instalador mantém o backup automático pré-atualização e a versão anterior lado a lado.
