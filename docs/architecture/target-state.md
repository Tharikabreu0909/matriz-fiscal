# Arquitetura-alvo

> Proposta para aprovação. Decisão registrada em `docs/decisions/ADR-001-modular-monolith.md`.

## 1. Avaliação crítica da proposta inicial

A proposta "Monólito Modular + Clean Architecture + organização por domínio" é **adequada na direção, mas precisa ser dosada** para o tamanho real do projeto:

| Fato | Implicação |
|---|---|
| ~12 mil linhas de Python, um operador, um processo, SQLite local | Microsserviços, fila, mensageria ou event sourcing **não se justificam** |
| As regras fiscais já são funções puras sobre `dict` (`services/`) | O "domínio" já existe. O trabalho é **tipar** e **desduplicar**, não reescrever |
| O problema real está em `app.py` (orquestração + regra + status) e em `database.py` (JSON livre, sem transação) | A camada **Application (casos de uso)** é a que mais rende |
| A UI depende do JSON integral das respostas | Manter contratos HTTP estáveis durante a migração (strangler) |

Ajustes em relação à proposta:

1. **Clean Architecture "leve":** quatro camadas por módulo, mas **sem** interfaces para tudo. Ports (`Protocol`) apenas onde há troca real de implementação: provedores externos, leitores de PDF por UF, repositórios (para testes). Nada de mapeadores ORM, CQRS ou entidades anêmicas com getters.
2. **`fiscal_integrations` não é um módulo de domínio.** Integração é infraestrutura. Cada módulo declara o port de que precisa (`company_registry` → `CompanyRegistryProvider`; `pgdas` → `PgdasSource`; `taxation` → `EconomicIndexSource`) e os adaptadores ficam em `integrations/`.
3. **`processes` é o agregado central** (caso fiscal com revisões). `analysis` depende dele, não o contrário.
4. **Novo `shared_kernel`** para objetos de valor fiscais hoje copiados em 6 arquivos: `Competencia`, `Centavos`, `Cnpj`, `Aliquota`.
5. **`taxation` absorve `legal_charges`** (multa e juros) e a série Selic (via port).
6. **`malha` ganha um port de leitor por fonte** (`MalhaReader` com `SeecDfAgencianetReader`). É o ponto de extensão para outras UFs.

## 2. Módulos e responsabilidades

| Módulo | Domínio (puro) | Casos de uso | Origem no código atual |
|---|---|---|---|
| `shared_kernel` | `Competencia`, `Centavos`, `Cnpj`, `Aliquota`, `calendario_fiscal` (vencimento padrão) | — | `month_index` (×6), `parse_money_to_cents` (×2), `security.is_valid_cnpj`, `legal_charges.standard_due_date` |
| `company_registry` | `Company`, `CompanyRegistrySnapshot`, regras de override manual | Cadastrar, consultar CNPJ, atualizar dados públicos, excluir | `database.*company*`, `security.validate_cnpj` |
| `malha` | `Malha`, `AvisoMalha` (Tipo 01/17), merge, identidade | Importar malha, detectar duplicidade | `readers/malha_reader`, `malha_merge`, `security.validate_malha_identity`, `pgdas_planner.normalize_malha_data` |
| `pgdas` | `DeclaracaoPgdas`, `LinhaDoTempoReceitas` (**implementação única** da precedência), plano de cobertura, situação documental (1.44) | Planejar PGDAS, importar (manual/lote), marcar ausência | `readers/pgdas_reader`, `pgdas_planner`, `reflection_coverage`, `cross_engine.validate_pgdas_identity` |
| `analysis` | Análise por competência, segregação 01/17, exceções | Analisar processo, registrar decisão humana | `analysis_engine`, `accounting_study`, `process_summary`, parte de `confirm_analysis` |
| `taxation` | Tabelas LC 123 versionadas, `calculate_hidden_reflections`, multa e juros | Calcular imposto, calcular encargos | `tax_engine`, `legal_charges`; `tax_segregation`/`tax_revenue_lines` como **experimental** |
| `reports` | Modelo do relatório | Emitir relatório (imutável), listar emitidos | `client_report` |
| `processes` | `FiscalProcess`, `ProcessRevision`, máquina de estados, trilha de eventos | Abrir/obter processo, nova revisão | Status espalhado em `app.py`, `database.*process*` |
| `system` | — | Backup, restauração, diagnóstico | `backup_service`, `support_bundle`, `runtime_paths`, `app_logging` |
| `integrations` (infra) | — | — | Novo: BrasilAPI, cnpj.ai, ViaCEP, BCB, (futuro) Integra Contador |

## 3. Estrutura de pastas

```
checkfiscal/
  shared_kernel/              competencia.py, money.py, cnpj.py, fiscal_calendar.py
  company_registry/
    domain/                   company.py, registry_snapshot.py, override_policy.py
    application/              register_company.py, lookup_cnpj.py, ports.py
    infrastructure/           sqlite_company_repository.py
    api/                      routes.py, schemas.py
  malha/
    domain/                   malha.py, notice.py, merge.py, identity.py
    application/              import_malha.py, ports.py (MalhaReader)
    infrastructure/           seec_df_agencianet_reader.py, sqlite_malha_repository.py
    api/
  pgdas/
    domain/                   declaration.py, revenue_timeline.py, coverage_plan.py, document_status.py
    application/              plan_pgdas.py, import_pgdas.py, mark_pgdas_status.py, ports.py
    infrastructure/           pdf_pgdas_reader.py, sqlite_pgdas_repository.py
    api/
  analysis/   domain/ application/ infrastructure/ api/
  taxation/
    domain/                   annex_tables_2018.py, effective_rate.py, reflections.py, legal_charges.py
    experimental/             segregation.py, revenue_lines.py, annex_columns.py   # sem rota
    application/              calculate_tax.py, calculate_charges.py, ports.py (SelicSource)
    infrastructure/           sqlite_selic_cache.py
  reports/    domain/ application/ infrastructure/ api/
  processes/  domain/ (state_machine.py, revision.py) application/ infrastructure/ api/
  system/     backup.py, support_bundle.py, runtime_paths.py, logging.py, settings.py
  integrations/
    brasilapi.py, cnpjai.py, viacep.py, bcb_sgs.py, http.py (timeout/retry/rate-limit)
    integra_contador/         # somente após a Fase 4
  infrastructure/
    db.py                     # conexão, unidade de trabalho, migrações versionadas
    migrations/0003_*.sql …
  main.py                     # FastAPI: monta os routers + middlewares (Host/Origin)
static/                       # sem mudança de tecnologia
app.py                        # shim: `from checkfiscal.main import app` (mantém "app:app")
```

### Regra de dependência

```
api ──► application ──► domain ◄── infrastructure
                 │                    ▲
                 └── ports (Protocol) ┘
shared_kernel ◄── todos
```

- `domain/` **não importa** `fastapi`, `sqlite3`, `pdfplumber`, `urllib`/`httpx`.
- Um módulo só importa `application` de outro módulo, nunca `infrastructure`.
- Teste arquitetural (`tests/architecture/test_imports.py`) com análise de AST para garantir isso.

## 4. Persistência-alvo

- **Unidade de trabalho:** uma conexão e uma transação por caso de uso (`with uow:`). Fecha a conexão sempre.
- **Migrações numeradas** (`infrastructure/migrations/NNNN_*.sql`) registradas em `schema_migrations`, com `user_version` igual ao maior número. A primeira migração **reconhece** os bancos 1.41 e 1.45 existentes e cria as tabelas 1.44/1.45 se faltarem.
- O JSON continua permitido para **snapshots imutáveis** (documento lido, cálculo emitido), com campo `schema_version`. Os dados consultados por regra (status, competência, sha256) ganham colunas próprias.
- `ON DELETE` explícito; exclusão de empresa vira **arquivamento** (exclusão física só por ação de LGPD, com registro).

## 5. Matriz de automação

| Operação | Classe | Justificativa |
|---|---|---|
| Validar dígitos do CNPJ | Total | Determinístico |
| Buscar dados públicos do CNPJ | Total, com revisão | Dados abertos podem estar defasados; o operador confirma |
| CFDF / inscrição estadual | Manual | Nenhuma API verificada fornece |
| Ler a malha (todas as páginas) | Total | Determinístico; falha explícita se a contagem de linhas divergir |
| Identificar a empresa da malha | Total por CFDF; **humana** por similaridade de nome | Hoje aceita nome com similaridade ≥ 0,78 |
| Detectar malha duplicada | Total | SHA-256 |
| Planejar PGDAS | Total | Determinístico; o plano inválido bloqueia |
| Associar PGDAS ao processo | Total | Raiz do CNPJ + PA |
| Original × retificadora | Total, **após** registrar a data de transmissão (ou via `CONSDECLARACAO13`) | Hoje é implícito e inconsistente (P0-7) |
| Marcar PGDAS "não declarado" | **Humana** (1.44), ou total via `CONSDECLARACAO13` na Fase 4 | Hoje é declaração do operador |
| Análise Tipo 17 sem conflito | Total | Regra conservadora documentada |
| Conflito de fontes | **Humana** | Decisão contábil |
| Conferência Tipo 01 × PGDAS | Parcial (exibir comparação) | Hoje não existe; não gera imposto |
| Escolha do anexo / Fator R | **Humana** | Motor de segregação ainda não validado |
| Cálculo de imposto e reflexos | Total, com pré-condições bloqueantes | Só com cobertura completa |
| Selic e encargos | Total | Série oficial, com cache e valores gravados |
| Vencimento com feriados | Parcial | Extrato do DAS quando houver; senão estimativa com aviso |
| Emitir relatório | Total, **após** aprovação do contador | Relatório imutável, com premissas e fontes |
| Retificar PGDAS / SPED | **Fora do sistema** | Decisão e ato do contador |

## 6. Estratégia de testes

| Nível | Escopo | Ferramentas e regras |
|---|---|---|
| Unitário (domínio) | `Competencia`, alíquota efetiva por faixa (todas as faixas dos 5 anexos), RBT12, reflexos, multa (limite de 20%), juros (meses, mês corrente, sem dados), precedência de receitas | pytest puro, sem I/O; property-based (`hypothesis`) para as invariantes de competência e arredondamento |
| Leitores | Malha (1 e várias páginas; continuação de tipo entre páginas), PGDAS (extrato e declaração) | **PDFs sanitizados versionados** em `tests/fixtures/pdf/` (substituir `/mnt/data`). Proibir `return` silencioso: usar `pytest.skip` com motivo ou falhar |
| Integração (SQLite) | Repositórios, unidade de trabalho, rollback em falha no meio do caso de uso | Banco temporário por teste via `conftest.py` (fixture `autouse` que define `CHECKFISCAL_DATA_DIR`) |
| Contrato (provedores) | BrasilAPI, cnpj.ai, ViaCEP, BCB | Respostas gravadas e sanitizadas; um job manual opcional de "verificação ao vivo", nunca no CI |
| Falhas externas | Timeout, 429 com `Retry-After`, 5xx, JSON inválido, campo ausente, offline | Transporte HTTP injetado |
| Regressão fiscal | Casos **aprovados por contador**: entrada (malha + PGDAS) → saída esperada (plano, análise, imposto, encargos com Selic fixada) | `tests/regression/cases/<id>/` com `expected.json` e a assinatura do aprovador; mudança no resultado exige revisão |
| Ponta a ponta | Malha → PGDAS → decisão → cálculo → relatório via `TestClient` | `httpx` em `requirements-dev.txt` |
| Migração | Banco 1.41 e banco 1.45 → schema novo: contagens preservadas, `integrity_check`, `foreign_key_check` | Fixtures de banco geradas pelos commits `bf35530` e `64c9578` |
| Arquitetura | Regra de imports entre camadas | Teste de AST |
| UI | Substituir os testes por trecho de string por testes de **comportamento** (Playwright) em poucos fluxos críticos; manter os de string só para identificadores estáveis (`id=`) | Fase 1 em diante |
