# Arquitetura atual — estado comprovado pelo código

> Auditoria de 22/10/2026 sobre o branch `fix/arquitetura`, commit `bf35530`.
> Toda afirmação abaixo aponta para arquivo e linha. O que não foi verificado está marcado como **NÃO VERIFICADO**.

## 1. Resumo executivo

O CheckFiscal / Matriz Fiscal é um **monólito FastAPI local** com cerca de 12,3 mil linhas de Python de produção, 3,35 mil linhas de HTML/JS (`static/index.html`) e 6,76 mil linhas de CSS (`static/app.css`). Ele lê PDFs de **malha fiscal da SEEC-DF (Agenci@Net)** e extratos e declarações **PGDAS-D**, cruza os dois por competência e estima a exposição tributária de anexo único, com multa e juros Selic.

Três fatos mudam a leitura que o projeto fazia de si mesmo:

1. **O código em execução é 1.41.0, e não por falta de implementação: a 1.42–1.45 foi implementada e depois revertida.** O primeiro commit (`64c9578`) tinha `APP_VERSION = "1.45.0"`. O commit seguinte, `fe0679b` ("dados reais"), voltou para `1.41.0` e removeu `adapt_plan_to_last_transmitted`, `set/get_last_transmitted_pgdas`, `list/set_pgdas_missing_status`, três endpoints e **três correções fiscais** (seção 6). Os testes foram editados no mesmo commit para aceitar a reversão.
2. **O leitor de malha voltou a ler somente a página 1.** Avisos que continuam na página 2, inclusive Tipo 17, são descartados sem erro (`readers/malha_reader.py:89` e `:150`).
3. **O produto é específico do Distrito Federal.** O leitor se chama `checkfiscal-malha-gdf-reader` (`readers/malha_reader.py:216`), procura o texto "Agenci@Net - Secretaria de Estado de Economia - SEEC DF" (`:101`) e identifica o contribuinte por **CFDF**, não por CNPJ (`:42`). A malha não traz CNPJ; a identidade é feita por CFDF ou por similaridade de razão social de pelo menos 0,78 (`services/security.py:70`).

## 2. Componentes reais

```
desktop_launcher.py ─┐
INICIAR_*.bat ───────┼─► uvicorn app:app ──► app.py (2.140 linhas, 22 rotas)
compose.yaml ────────┘                         │
                                               ├─► readers/malha_reader.py  (pdfplumber)
                                               ├─► readers/pgdas_reader.py  (pdfplumber, 1.598 linhas)
                                               ├─► services/* (regras fiscais, sem dependência de FastAPI)
                                               ├─► database.py (SQLite, 1.330 linhas, init_db() no import)
                                               └─► services/legal_charges.py ──HTTP──► api.bcb.gov.br (SGS 4390)
static/index.html + app.css  ◄── GET / e GET /static/app.css
```

| Camada de fato | Arquivos | Observação |
|---|---|---|
| Apresentação + orquestração | `app.py` | Rotas, validação, orquestração dos casos de uso e transições de status ficam no mesmo arquivo |
| Regras fiscais | `services/*.py` | Funções puras sobre `dict`, sem importar FastAPI nem SQLite (bom ponto de partida) |
| Leitura documental | `readers/*.py` | Dependem só de `pdfplumber` |
| Persistência | `database.py` | Uma função por operação, uma conexão por chamada, JSON em colunas `*_json` |
| Infra de runtime | `services/runtime_paths.py`, `app_logging.py`, `file_storage.py`, `backup_service.py`, `support_bundle.py` | Criam diretórios **no import** |
| UI | `static/index.html` | JS inline, sem build e sem framework |

### Rotas (app.py)

| Método | Rota | Linha | Efeito colateral relevante |
|---|---|---|---|
| GET | `/`, `/static/app.css`, `/api/health` | 355–378 | — |
| GET/POST/PATCH/DELETE | `/api/companies[/{id}]` | 382–444 | `GET /api/companies/{id}` **grava** o plano PGDAS (`ensure_current_pgdas_plan`) |
| GET | `/api/events` | 387 | — |
| POST | `/api/analyze-malha` | 447 | Cria ou mescla processo; **apaga cálculos, decisões e relatórios** ao mesclar (`invalidate_process_analysis`) |
| POST | `/api/upload-pgdas` | 639 | Sempre insere um novo `pgdas_documents`, sem deduplicar |
| POST | `/api/upload-pgdas-auto` | 957 | Lote; deduplica por período já aceito |
| GET | `/api/process/{id}/documents`, `/api/documents/{id}/download` | 1199, 1224 | Caminho protegido contra traversal (`file_storage.resolve_document_path`) |
| GET | `/api/system/status`, `/backup`, `/support-bundle` | 1245–1301 | Backup grava ZIP em disco |
| POST | `/api/system/restore` | 1266 | Substitui banco e documentos |
| GET | `/api/process/{id}` | 1304 | **Grava** o plano PGDAS |
| POST | `/api/confirm-analysis` | 1381 | Decisão humana |
| GET | `/api/accounting-study` | 1640 | Desativado (410) |
| GET | `/api/tax-setup` | 1651 | — |
| POST | `/api/calculate-tax` | 1738 | Grava cálculo |
| POST | `/api/calculate-legal-charges` | 1925 | Consulta o BCB e grava |
| GET | `/api/client-report` | 2019 | **GET que grava** relatório, status e evento a cada abertura |

## 3. Fluxo fiscal implementado

1. **Malha**: `read_malha_pdf` → `normalize_malha_data` → `calculate_required_pgdas` (planejador **2.4.0**, `services/pgdas_planner.py:568`) → `processes.malha_json` e `pgdas_plan_json`.
2. **Mesma empresa, nova malha**: `merge_malhas` une as linhas brutas, recalcula o plano e **apaga** diagnósticos, confirmações, conclusões, perfis, cálculos e relatórios (`database.py:448–468`). Arquivo idêntico é reconhecido pelo SHA-256 (`services/malha_merge.py:74`).
3. **PGDAS**: `read_pgdas_pdf` → `validate_pgdas_identity` (raiz do CNPJ, 8 dígitos) → aceito se raiz e competência conferem.
4. **Análise**: `analyze_process` (`services/analysis_engine.py:563`). O Tipo 17 compara a receita declarada com o valor considerado e simula `max(declarado, considerado)`. O Tipo 01 registra a diferença mínima de SPED/LFE e **não usa o PGDAS** (`:354–374`), embora o planejador peça PGDAS para ele.
5. **Revisão humana**: só quando há conflito de fontes ou avisos duplicados com valores diferentes (`:511`).
6. **Cálculo**: `calculate_hidden_reflections` (`services/tax_engine.py:222`), com anexo único I–V, tabelas da LC 155/2016 (conferidas faixa a faixa nesta auditoria), reflexo de 12 meses na RBT12 e bloqueio de 2027 em diante.
7. **Encargos**: multa de 0,33% ao dia, limitada a 20%, e juros pela soma da Selic mensal (série 4390) do mês seguinte ao vencimento até o mês anterior ao pagamento, mais 1% (`services/legal_charges.py:159–217`). É a forma do art. 61 da Lei 9.430/1996.
8. **Relatório**: `build_report_model` + `render_client_report`, com HTML escapado (`html.escape`).

## 4. Regras fiscais: implementadas, documentadas e divergentes

| Regra | Estado no HEAD | Evidência |
|---|---|---|
| Tipo 01 e Tipo 17 não se somam | Implementada | `analysis_engine.build_segregation` (`tax_source: TYPE_17_ONLY`) |
| PGDAS para toda competência da malha, inclusive só Tipo 01 | Implementada no planejador | `pgdas_planner.py:218` |
| Conferência do PGDAS contra o Tipo 01 | **Não implementada** (o PGDAS é exigido, mas não é comparado) | `analysis_engine.py:354–374` |
| Plano antecipado de reflexos | Implementada | `pgdas_planner.py:300` |
| Leitura de malha em várias páginas (1.43) | **Revertida** | `malha_reader.py:89`; diff de `fe0679b` |
| Trava: Tipo 17 aguardando PGDAS impede cálculo "completo" (1.43) | **Revertida** | diff de `fe0679b` em `app.py` |
| Trava: incremento esperado sem impacto calculado (1.43) | **Revertida** | idem |
| Relatório lista todas as competências da malha (1.43) | **Revertida**: hoje oculta as linhas sem impacto | `client_report.py:191–199` |
| Situação do PGDAS: não declarado / não localizado (1.44) | **Revertida** | `database.py` em `64c9578` |
| Corte no último PGDAS transmitido (1.45) | **Revertida** | `pgdas_planner.py` em `64c9578` |
| Fator R, segregação, monofásico e ST | Escrita, **fora do cálculo da API** | `tax_segregation.py`, `tax_revenue_lines.py`, `annex_columns_profile.py` |
| RBT12 proporcional (início de atividade) | Não implementada; meses faltantes viram `missing_months` | `tax_engine.py:307–321` |
| Sublimite de R$ 3,6 milhões (ICMS/ISS fora do DAS) | Não implementada | `tax_engine.py:76` (só o teto de R$ 4,8 milhões) |
| Vencimento com feriados | Não implementado; dia 20, com avanço de fim de semana e aviso | `legal_charges.py:48` |

## 5. Testes: cobertura real

Execução isolada (`CHECKFISCAL_DATA_DIR` apontando para um diretório temporário):

| Estado | Aprovados | Falhas | Erros de coleta |
|---|---|---|---|
| HEAD `bf35530` (1.41) | **121** | **29** | 4 |
| `64c9578` (1.45), em worktree isolado | **143** | 8 | 3 |

Por que falham no HEAD:

- **4 erros de coleta**: `httpx` não consta em `requirements-dev.txt` (exigido pelo `TestClient`), e `test_v145` importa uma função removida.
- **6 testes dependem de PDFs em `/mnt/data/...`**, que não estão no repositório.
- **`test_v143_real_multiplage_malha.py` passa sem testar nada**: faz `return` quando o PDF não existe (falso verde).
- **cerca de 17 testes de UI procuram trechos literais** de HTML/CSS minificado (`"flex:1 1 0" in HTML`). Quebraram quando o CSS foi extraído para `app.css` (commit `bf35530`).
- **3 testes de versão** esperam 1.45 e Python 3.13 no `.bat`.
- `test_simplified_analysis_ui.py::test_tax_calculator_files_were_not_changed` compara SHA-256 de arquivos-fonte e quebra com conversão CRLF/LF.
- **Não há `conftest.py`.** `import database` executa `init_db()` no banco real (`%LOCALAPPDATA%\CheckFiscal`) quando a variável de ambiente não é definida. Testes que não fazem `monkeypatch` tocam o banco do operador.

Cobertura de linhas: **NÃO MEDIDA** (`coverage` não está instalado).

## 6. O commit de reversão `fe0679b`

| Área | O que saiu | Consequência |
|---|---|---|
| `readers/malha_reader.py` | Leitura de tabelas de avisos em todas as páginas | Avisos da página 2 em diante são perdidos |
| `app.py` `calculate_tax` | Duas travas 409 (Tipo 17 aguardando PGDAS; incremento sem impacto) | Cálculo pode ser gravado como completo com valor zero |
| `services/client_report.py` | Linhas de todas as competências da malha | Relatório ao cliente omite competências |
| `database.py` | Tabelas e funções `pgdas_missing_status` e `pgdas_last_transmitted` | Funcionalidades 1.44/1.45 removidas |
| `app.py` | `/last-transmitted-pgdas`, `/pgdas-situation`, `/partial-report` | idem |
| `requirements.txt` | `uvicorn` → `uvicorn[standard]` | Reintroduz dependências compiladas (motivo da nota 1.42) |
| Lançadores | Porta 8145 → 8141 | Docker continua em 8145 |
| Testes | Asserções trocadas de 1.45 para 1.41 | Os testes deixaram de proteger as correções |

O motivo da reversão **não está registrado**. Decidir o que restaurar é a primeira decisão da Fase 0 (`migration-plan.md`).

## 7. Persistência e compatibilidade dos bancos

- 13 tabelas, `PRAGMA user_version = 2`, `schema_migrations` com uma única linha "1". As migrações são aditivas (`_ensure_column`).
- Instalações que rodaram a 1.45 têm duas tabelas a mais (`pgdas_missing_status`, `pgdas_last_transmitted`). A 1.41 **as ignora sem erro**, mas os dados nelas ficam invisíveis. As duas versões gravam `user_version = 2`, então não há como distinguir os bancos.
- Chaves estrangeiras declaradas e `PRAGMA foreign_keys = ON`, mas **sem `ON DELETE CASCADE`**. A exclusão é manual (`database.py:353`).
- `pgdas_documents` não tem restrição de unicidade. O mesmo PDF enviado duas vezes por `/api/upload-pgdas` gera dois registros aceitos.
- `with sqlite3.connect(...) as conn` confirma a transação, mas **não fecha a conexão**. O fechamento depende do coletor de lixo.
- Não há transação entre etapas de um caso de uso. No upload de PGDAS, `save_pgdas_document`, `store_document`, `register_stored_document`, o evento e o status usam conexões separadas.

## 8. Execução: Windows × Docker × executável

| Aspecto | Windows `.bat` | `desktop_launcher.py` / PyInstaller | Docker `compose.yaml` | `Dockerfile` CMD |
|---|---|---|---|---|
| Porta | 8141 | 8141 | 8145 | 8145 |
| Versão anunciada | 1.41 | — | "1.45" (`iniciar_docker.sh`) | — |
| Python | qualquer `py`/`python` do PATH | o da máquina de build | 3.13-slim | 3.13-slim |
| Dados | `%LOCALAPPDATA%\CheckFiscal` | idem | `./checkfiscal_data` (bind mount) | `/data` |
| Código | pasta extraída | empacotado | **bind mount `.:/app` com `--reload`** (configuração de desenvolvimento) | copiado na imagem |
| Usuário | operador | operador | **root** | root |
| Dependências | instaladas da internet no primeiro uso, transitivas sem pin | congeladas | imagem | imagem |

**Risco no executável (NÃO VERIFICADO por build):** `checkfiscal.spec` analisa só `desktop_launcher.py`, que passa `"app:app"` como **texto** ao uvicorn. O PyInstaller não segue esse import, e `hiddenimports` cobre apenas `uvicorn` e `pdfplumber`. É provável que `app.py`, `database.py`, `readers/` e `services/` fiquem fora do pacote e o executável falhe com "Could not import module 'app'".

## 9. Dependências externas

| Dependência | Uso | Falha |
|---|---|---|
| `api.bcb.gov.br` SGS 4390 | Juros | Erro 422 explícito; o resto do fluxo funciona offline |
| PyPI | Primeira execução do `.bat` | Sem internet, não instala |

Não há outras chamadas de rede. A BrasilAPI, o Serpro e o ViaCEP **não são usados** hoje.

## 10. Divergências com `jarvis_docs/`

A pasta `jarvis_docs/` está correta sobre o estado 1.41, mas parte de uma premissa que o histórico do git desmente: trata a 1.42–1.45 como "meta não implementada", quando ela **foi implementada em `64c9578` e revertida em `fe0679b`**. Também não registra a regressão do leitor multipágina nem a remoção das travas de cálculo e do relatório completo.

**Proposta:** acrescentar uma seção "Histórico de reversão" em `jarvis_docs/activeContext.md` e `progress.md` apontando para este documento, sem apagar o conteúdo atual.
