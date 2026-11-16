# Política de segurança de requisições (T02)

Status: aprovada pelo Maestro e pelo Security Engineer. Implementação na T02.
Fonte técnica: `phase-0-plan.md` §2.4 e §3 (P0-S1); `t02-preparation.md` §6.
Testes de aceitação: `tests/test_t02_request_guard.py`.

## 1. Regras

1. **Host** (toda requisição, inclusive `GET /`): `Host` deve ser `127.0.0.1` ou `localhost`, nas portas **8141** (Windows), **8145** (Docker) e **8146** (desenvolvimento isolado). Fora da lista → **400** `{"code": "HOST_NOT_ALLOWED"}`. Bloqueia DNS rebinding (`evil.com`, `127.0.0.1.evil.com`, porta não listada).
2. **Origin** (quando presente): precisa ser `http(s)://host:porta` autorizado, com esquema, host e porta iguais aos da lista. `Origin: null` é inválido. Fora disso → **403** `{"code": "CROSS_ORIGIN_BLOCKED"}`.
3. **Sec-Fetch-Site** (quando presente): aceita só `same-origin` ou `none`. `cross-site` e `same-site` → 403, inclusive `same-site` com outra porta de `localhost`.
4. **Contradição**: `Origin` e `Sec-Fetch-Site` que apontam para lados diferentes → 403.
5. **Sem `Origin` e sem `Sec-Fetch-Site`** (CLI, cliente local, `TestClient`): só vale a regra de Host. **Decisão a confirmar pelo Security Engineer.**
6. **Escopo do bloqueio**:
   - `POST`, `PUT`, `PATCH` e `DELETE` em qualquer caminho, inclusive rota inexistente (PUT → 403, não 405).
   - `GET` sob `/api/`, exceto `/api/health`. Inclui GETs que gravam (`/api/system/backup`, `/api/system/support-bundle`, `/api/client-report`, `/api/process/{id}`, `/api/companies/{id}`).
   - `GET /`, `GET /static/app.css` e `GET /api/health` aceitam qualquer `Sec-Fetch-Site` (somente leitura, sem dados).
7. **Ordem**: o guard roda **antes** do roteador e antes de ler o corpo. Rota com barra final cross-origin → 403, não 307. Upload e restore não são lidos quando bloqueados.
8. **OPTIONS** não ganha CORS: não há `CORSMiddleware`, logo nenhuma resposta traz `Access-Control-*`.
9. **Proteção em camadas**: a regra não depende só de `Content-Type` nem só de CORS. JSON enviado sem `Content-Type` (corpo `Blob`) passa pela mesma regra de Origin/Sec-Fetch-Site.
10. **Bloqueio registrado** em log no nível WARNING, com método e rota. Sem query string e sem corpo.
11. **Configuração**: lista de hosts e portas em `CHECKFISCAL_ALLOWED_HOSTS`. Na suíte de testes ela inclui `testserver` (aditivo, definido no `conftest.py`); em produção não é definida.
12. **Menor privilégio**: nenhuma rota nova; nenhuma alteração na UI (`static/*`); a UI continua com caminhos relativos `/api/...`.

## 2. Decisões fora do escopo

- **Sem token** de API e **sem interruptor de desativação**. Não existe `CHECKFISCAL_ORIGIN_CHECK=0` nem equivalente. O item H1 do plano anterior (`t02-preparation.md` §6), que previa essa chave para suporte, foi **descartado**. A política não admite interruptor genérico que desligue a segurança.
- Acesso por IP da LAN não é permitido (Docker não publica porta na LAN).

## 3. Inventário de rotas

Levantado de `app.py` (25 decoradores de rota; `GET /` incluído). "Guardada" indica se a regra 6 se aplica. Efeito colateral é o observado no handler.

| # | Método | Rota | Corpo / parâmetros | Efeito colateral | Guardada |
|---|---|---|---|---|---|
| 1 | GET | `/` | — | Lê `static/index.html` | Não (leitura) |
| 2 | GET | `/static/app.css` | — | Lê CSS | Não (leitura) |
| 3 | GET | `/api/health` | — | Nenhum | Não (leitura) |
| 4 | GET | `/api/companies` | — | Lê lista | Sim |
| 5 | GET | `/api/events` | query `limit` | Lê eventos | Sim |
| 6 | POST | `/api/companies` | JSON `CompanyCreateRequest` | Insere empresa | Sim |
| 7 | GET | `/api/companies/{id}` | path | **Grava**: `ensure_current_pgdas_plan` atualiza o plano PGDAS | Sim |
| 8 | PATCH | `/api/companies/{id}` | JSON `CompanyUpdateRequest` | Atualiza empresa | Sim |
| 9 | DELETE | `/api/companies/{id}` | path | Apaga documentos em disco e a empresa | Sim |
| 10 | POST | `/api/analyze-malha` | multipart `file` + query `company_id`, `company_cnpj`, `confirm_identity_mismatch` | Cria processo, documento, malha; em merge, apaga análise derivada (P0-4) | Sim |
| 11 | POST | `/api/upload-pgdas` | multipart `file` + query `process_id`, `competence` | Grava PGDAS e diagnóstico | Sim |
| 12 | POST | `/api/upload-pgdas-auto` | multipart `files[]` + query `process_id` | Grava lote de PGDAS | Sim |
| 13 | GET | `/api/process/{id}/documents` | path | Lê lista | Sim |
| 14 | GET | `/api/documents/{id}/download` | path | Lê arquivo | Sim |
| 15 | GET | `/api/system/status` | — | Lê estado | Sim |
| 16 | GET | `/api/system/backup` | — | **Cria** ZIP em `backups/` | Sim |
| 17 | POST | `/api/system/restore` | multipart `file` (ZIP) | **Substitui o banco** (cria backup de segurança antes) | Sim |
| 18 | GET | `/api/system/support-bundle` | — | **Cria** ZIP em `support/` | Sim |
| 19 | GET | `/api/process/{id}` | path | **Grava**: `ensure_current_pgdas_plan` | Sim |
| 20 | POST | `/api/confirm-analysis` | query `process_id`, `competence`, `decision`, `corrected_pgdas_revenue_cents` | Grava confirmação | Sim |
| 21 | GET | `/api/accounting-study` | — | Rota desativada; handler sem escrita | Sim |
| 22 | GET | `/api/tax-setup` | query `process_id`, `scenario` | Lê configuração | Sim |
| 23 | POST | `/api/calculate-tax` | JSON `TaxCalculationRequest` | Grava perfil e cálculo; atualiza status | Sim |
| 24 | POST | `/api/calculate-legal-charges` | query `process_id`, `update_date`, `scenario` | Grava cálculo de encargos; atualiza status | Sim |
| 25 | GET | `/api/client-report` | query `process_id`, `scenario` | **Grava** relatório e evento; atualiza status | Sim |

Observações:
- Os GETs 7 e 19 gravam, por isso entram na regra 6 mesmo sendo `GET`. A §2.4 do plano listava só três GETs; o inventário mostra cinco.
- Rota 24: não verifiquei se o handler faz chamada de rede. Se fizer, a regra não muda, mas o teste de rejeição deve provar que nenhuma chamada saiu.
- A lista é do código atual (`app.py`). Se uma rota for adicionada, a regra 6 a cobre sem ajuste.

## 4. Decisões pendentes (Security Engineer)

1. Requisição sem `Origin` e sem `Sec-Fetch-Site` passa só com Host válido (regra 5). Confirmar.
2. Hosts e portas exatos (`8141`, `8145`, `8146`) e se `localhost` e `127.0.0.1` valem nas três portas.
3. Formato do log de bloqueio (regra 10).

## 5. Testes

`tests/test_t02_request_guard.py`: 72 casos. 50 rejeições com `xfail(strict=True, reason="T02: ...")` e 22 permissões verdes. Cada rejeição prova ausência de efeito (linhas de todas as tabelas, arquivos de backup, suporte e documentos iguais antes e depois) e que o handler não foi alcançado.
