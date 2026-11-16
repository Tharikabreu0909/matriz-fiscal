# Catálogo de APIs candidatas

> Pesquisa de 22/10/2026. Cada item informa **como** foi verificado:
> **[CHAMADA REAL]**: endpoint chamado nesta auditoria e resposta inspecionada.
> **[DOC OFICIAL]**: documentação do fornecedor lida.
> **[CÓDIGO-FONTE]**: repositório público do fornecedor lido.
> **NÃO VERIFICADO**: não foi possível confirmar; não usar como premissa.

## Resumo de classificação

| API | Classificação | Custo | Recomendação |
|---|---|---|---|
| BrasilAPI CNPJ v1 | Disponível por API pública | Gratuita | **Adotar como provedor primário** do cadastro |
| cnpj.ai v2 | API autenticada (chave por conta) | Gratuita, segundo a página; planos pagos NÃO VERIFICADO | Fallback opcional, com chave **por instalação** |
| Minha Receita | API pública (upstream da BrasilAPI) | Gratuita | Não usar como fallback independente (mesma origem) |
| Serpro Consulta CNPJ v2 | Serviço comercial | Pago; valores NÃO VERIFICADO | Só se houver necessidade de dado on-line da RFB |
| ViaCEP | API pública | Gratuita | Adotar para endereço |
| BrasilAPI CEP v2 | API pública | Gratuita | Fallback do ViaCEP |
| BCB SGS 4390 | API pública | Gratuita | **Já em uso**; acrescentar cache e registro |
| Integra Contador (Serpro) | Serviço comercial + autorização do contribuinte | Pago por faixa de consumo; valores NÃO VERIFICADO | Prova de conceito **após aprovação** (Fase 4) |
| Consulta Faturamento (Serpro / Compartilha Receita) | Comercial + consentimento do titular | NÃO VERIFICADO | Inviável no escopo atual |
| Portal do Simples Nacional (consulta optante) | Página web com CAPTCHA | — | **Não usar** (seria scraping) |
| Malha SEEC-DF (Agenci@Net) | Portal autenticado estadual | — | Não comprovada como API; manter upload de PDF |
| NFS-e Nacional / SEFAZ | Autenticado, por certificado | — | Inviável no escopo atual |
| Tabelas CNAE (IBGE) | API pública | Gratuita | NÃO VERIFICADO nesta auditoria; candidata para validar a descrição do CNAE |

---

## 1. BrasilAPI — CNPJ v1

- **Fornecedor:** projeto comunitário BrasilAPI. Docs: <https://brasilapi.com.br/docs> (a página é uma SPA e não renderizou para leitura automática).
- **Endpoint:** `GET https://brasilapi.com.br/api/cnpj/v1/{cnpj}` **[CHAMADA REAL]**. HTTP 200, `Content-Type: application/json`, CORS `*`, servido por Cloudflare/Vercel com cache de CDN (`Age: 75619` s na chamada de teste: a resposta pode ter cerca de 1 dia).
- **Upstream:** `services/cnpj.js` faz `GET https://minhareceita.org/{cnpj}` com **timeout de 5 s**, e devolve 503 em falha do upstream **[CÓDIGO-FONTE]**. A Minha Receita publica os **dados abertos do CNPJ da RFB** (atualização periódica, tipicamente mensal).
- **Autenticação:** nenhuma.
- **Limites / política:** sem limite numérico publicado. O README pede uso "com natureza de uma pessoa real requisitando um determinado dado" e proíbe crawling **[CÓDIGO-FONTE]**. Termos de uso formais: "ainda elaborando".
- **Campos retornados** (chamada real com o CNPJ público 00.000.000/0001-91):

| Campo desejado | Campo BrasilAPI | Observação |
|---|---|---|
| CNPJ | `cnpj` | só dígitos |
| Razão social | `razao_social` | |
| Nome fantasia | `nome_fantasia` | |
| Data de abertura | `data_inicio_atividade` | ISO `AAAA-MM-DD` |
| Situação cadastral | `situacao_cadastral` (código), `descricao_situacao_cadastral` | |
| Data da situação | `data_situacao_cadastral` | |
| Motivo | `motivo_situacao_cadastral`, `descricao_motivo_situacao_cadastral` | |
| Natureza jurídica | `codigo_natureza_juridica`, `natureza_juridica` | |
| Porte | `codigo_porte`, `porte` | |
| Capital social | `capital_social` | número; **conferir a unidade** (reais, não centavos) |
| CNAE principal | `cnae_fiscal`, `cnae_fiscal_descricao` | |
| CNAEs secundários | `cnaes_secundarios[] {codigo, descricao}` | |
| Logradouro | `descricao_tipo_de_logradouro` + `logradouro` | |
| Número / complemento / bairro | `numero`, `complemento`, `bairro` | |
| Município / UF / CEP | `municipio`, `codigo_municipio`, `codigo_municipio_ibge`, `uf`, `cep` | |
| Telefone | `ddd_telefone_1`, `ddd_telefone_2`, `ddd_fax` | |
| E-mail | `email` | pode vir `null` |
| Matriz/filial | `identificador_matriz_filial`, `descricao_identificador_matriz_filial` | |
| Opção pelo Simples | `opcao_pelo_simples`, `data_opcao_pelo_simples`, `data_exclusao_do_simples` | ver o alerta abaixo |
| SIMEI | `opcao_pelo_mei`, `data_opcao_pelo_mei`, `data_exclusao_do_mei` | ver o alerta abaixo |
| Sócios | `qsa[]` | dado pessoal (LGPD): **não armazenar por padrão** |
| Regime tributário histórico | `regime_tributario[] {ano, forma_de_tributacao, ...}` | campo extra útil |

> **Alerta de qualidade:** na chamada de teste, `opcao_pelo_simples = false` veio com `data_opcao_pelo_simples = 2007-07-01` e `data_exclusao_do_simples = 2007-07-01`, o mesmo para o MEI. **As datas podem vir preenchidas sem opção efetiva.** Usar só o booleano, rotulado como "informação pública dos dados abertos, defasagem possível", e nunca como prova de enquadramento.

- **Riscos:** projeto comunitário sem SLA; dados mensais; dependência de um único upstream.
- **Utilidade:** alta para preencher o cadastro.
- **Recomendação:** **adotar** atrás de um adaptador com cache.

## 2. cnpj.ai — API v2

- **Docs:** <https://cnpj.ai/api/docs> **[DOC OFICIAL]**; OpenAPI em `https://api.cnpj.ai/v2/openapi.json` (não lido nesta auditoria).
- **Endpoints:** `GET /v2/empresas/{cnpj_basico_8}` e `GET /v2/estabelecimentos/{cnpj_14}`, com os modos `/basic`, `/full` e `/fontes/{fonte}`. Coleções paginadas por cursor (`limite` de 1 a 100).
- **Autenticação:** `Authorization: Bearer <chave>`. A chave aparece uma vez. A página **desaconselha colocar a chave em app distribuído** e informa que não há CORS.
- **Limites:** 60 chamadas por minuto por conta, até 5 chaves; cabeçalhos `X-RateLimit-*`; respeitar `Retry-After` no 429. Chamadas que retornam erro também contam.
- **Custo:** "Gratuita, com consumo na sua conta… sem cartão e sem cota mensal inicial". Planos pagos: NÃO VERIFICADO.
- **Fontes:** dados abertos da RFB, mais PGFN, CEIS/CNEP/CEPIM, MTE, IBAMA, ANTT, PNCP, BNDES; `meta` informa a competência e o snapshot (`2026-10`) e se a cobertura é completa ou parcial.
- **Simples/MEI:** objeto `simples` com valores `true`/`false`/`null`. Nomes exatos dos campos de CNAE, endereço e contato: NÃO VERIFICADO (estão no OpenAPI).
- **Utilidade:** fallback e enriquecimento (PGFN/dívida ativa pública e sanções).
- **Recomendação:** fallback **opcional**, ativado só quando o operador cadastrar a **própria** chave. Mesma origem RFB da BrasilAPI: melhora a disponibilidade, não a atualidade.

## 3. Serpro — Consulta CNPJ v2

- **Docs:** <https://apicenter.estaleiro.serpro.gov.br/documentacao/consulta-cnpj/pt/> **[DOC OFICIAL]**.
- **Produtos:** variantes Básica, QSA e Empresa (`consulta-cnpj-df-v2`). Paths e campos exatos: NÃO VERIFICADO.
- **Autenticação:** OAuth2 `client_credentials`: `POST https://gateway.apiserpro.serpro.gov.br/token` com Basic `ConsumerKey:ConsumerSecret`; Bearer com validade de 1 hora **[DOC OFICIAL]**.
- **Contratação:** Loja Serpro, contrato com pessoa jurídica. Preço: NÃO VERIFICADO (há notícias de 2017 com valores antigos, que não devem ser usadas).
- **Campos de Simples/SIMEI:** NÃO VERIFICADO.
- **Recomendação:** **não adotar agora.** O dado público dos dados abertos atende o cadastro. Reavaliar se o escritório precisar de situação cadastral on-line.

## 4. ViaCEP

- **Endpoint:** `GET https://viacep.com.br/ws/{cep}/json/` **[CHAMADA REAL]**.
- **Campos:** `cep`, `logradouro`, `complemento`, `unidade`, `bairro`, `localidade`, `uf`, `estado`, `regiao`, `ibge`, `gia`, `ddd`, `siafi`. CEP inexistente retorna `{"erro": "true"}` (comportamento documentado no site; não testado aqui).
- **Autenticação:** nenhuma. Limites: NÃO VERIFICADO (o site pede uso moderado).
- **Recomendação:** adotar para **validar e completar** o endereço vindo do CNPJ, nunca para sobrescrevê-lo sem revisão.

## 5. BrasilAPI — CEP v2

- `GET https://brasilapi.com.br/api/cep/v2/{cep}` **[CHAMADA REAL]**: `cep`, `state`, `city`, `neighborhood`, `street`, `service` (indica a origem, ex.: `open-cep`), `ibge.city`, `location.coordinates`.
- **Recomendação:** fallback do ViaCEP.

## 6. Banco Central — SGS série 4390 (Selic acumulada no mês)

- **Endpoint em uso:** `GET https://api.bcb.gov.br/dados/serie/bcdata.sgs.4390/dados?formato=json&dataInicial=dd/MM/aaaa&dataFinal=dd/MM/aaaa` **[CHAMADA REAL]** (`/ultimos/3` → `[{"data":"01/10/2026","valor":"0.71"}, ...]`, valores em % ao mês, decimal com ponto).
- **Série correta?** Sim. Os juros de mora federais (Lei 9.430/1996, art. 61, §3º; LC 123/2006, art. 35) usam a Selic **acumulada mensal**, que é a 4390.
- **Limites:** desde 26/03/2025 o BCB exige filtros, limita o volume e não aceita intervalo maior que 10 anos por consulta; `/ultimos/N` limitado a 20 (fonte: páginas de dados abertos do BCB).
- **Atualização:** mensal. O mês corrente pode ainda não estar publicado nos primeiros dias; o código já falha de forma explícita nesse caso (`legal_charges.py:209`).
- **Recomendação:** manter, com cache SQLite e registro dos valores usados (ver `migration-plan.md`, Fase 3).

## 7. Integra Contador (Serpro / RFB)

Detalhado em [`fiscal-services.md`](fiscal-services.md). Resumo verificado na documentação oficial:

- PGDAS-D: `TRANSDECLARACAO11`, `GERARDAS12`, `CONSDECLARACAO13`, `CONSULTIMADECREC14`, `CONSDECREC15`, `CONSEXTRATO16`, `GERARDASCOBRANCA17`, `GERARDASPROCESSO18`, `GERARDASAVULSO19`.
- **Procuração e-CAC código 00146** ("PGDAS-D - a partir de 01/2018") para todos os serviços PGDAS-D; **00002** para a Situação Fiscal (SITFIS).
- Contratação com **e-CNPJ**; Consumer Key/Secret; cobrança por faixa de consumo mensal.

## 8. Consulta Faturamento (Serpro, dentro do Compartilha Receita)

- **Natureza:** o titular PJ autoriza no portal da RFB **quais** dados vão, **para quem** e **por quanto tempo**. Só instituições previamente cadastradas podem ser destinatárias. Avaliado pela ANPD (Nota Técnica 38/2022) com base no consentimento.
- **Uso histórico:** instituições financeiras (por exemplo, Pronampe).
- **Endpoints, formato e preço:** NÃO VERIFICADO.
- **Viabilidade para o CheckFiscal:** **inviável no escopo atual**. Exige credenciamento como destinatário, o dado é de faturamento (não de receita declarada no PGDAS-D) e depende de ação ativa do cliente por consulta. **Não substitui o PGDAS.**

## 9. Integrações descartadas como padrão arquitetural

- **Scraping** do Portal do Simples Nacional (CAPTCHA), do e-CAC ou do Agenci@Net: **proibido** como solução padrão (viola os termos e é frágil).
- **NFS-e Nacional / SEFAZ (NF-e):** exigem certificado do contribuinte e têm escopo de documento fiscal, não de apuração. Fora do escopo atual.
- **Dívida ativa (PGFN):** o dado público aparece via cnpj.ai (`registros_publicos`). Útil como alerta, não como dado fiscal oficial do processo.
