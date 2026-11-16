# Integrações fiscais oficiais — viabilidade

> Fonte principal: catálogo oficial do Integra Contador
> (<https://apicenter.estaleiro.serpro.gov.br/documentacao/api-integra-contador/pt/catalogo_de_servicos/>, atualizado em 15/10/2026)
> e as páginas de serviço PGDAS-D e de Serviços × Procurações, lidas em 22/10/2026.
> Nada aqui foi testado contra a API real (exige contrato).

## 1. Conclusão em uma frase

**É possível recuperar automaticamente as declarações PGDAS-D já transmitidas, mas em PDF (base64), não como receitas estruturadas.** O CheckFiscal continuaria lendo esses PDFs com o `pgdas_reader` atual; a integração elimina o download manual, não o leitor. Isso exige um contrato pago com o Serpro, um e-CNPJ do escritório e a procuração e-CAC **00146** de cada cliente.

## 2. Serviços relevantes do Integra-SN (PGDAS-D)

| idServico | Tipo | O que faz | Retorno | Útil ao CheckFiscal |
|---|---|---|---|---|
| `CONSDECLARACAO13` | Consultar | Lista as operações por ano-calendário ou PA: original, retificadora, geração de DAS, DAS avulso/cobrança | **JSON**: `numeroDeclaracao`, `dataHoraTransmissao`, **`malha`** (Retida em Malha / Liberada / Intimada / Rejeitada), `numeroDas`, `dataHoraEmissaoDas`, **`dasPago`** | **Alta.** Mostra qual é a última declaração (resolve P0-7), se o PA foi transmitido (substitui a marcação manual da 1.44/1.45) e se o DAS foi pago |
| `CONSULTIMADECREC14` | Consultar | Última declaração e recibo de um PA (`periodoApuracao` AAAAMM) | **PDF base64** (declaração, recibo e, se houver, MAED) | **Alta.** Substitui o upload manual da declaração |
| `CONSDECREC15` | Consultar | Declaração e recibo por `numeroDeclaracao` | PDF base64 | Média (versões anteriores ou retificadas) |
| `CONSEXTRATO16` | Consultar | Extrato do DAS por `numeroDas` | PDF base64 | Alta. O extrato traz o quadro do DAS (vencimento), que a declaração não traz |
| `TRANSDECLARACAO11` | Declarar | Entrega a declaração mensal | — | **Fora do escopo. Não automatizar.** |
| `GERARDAS12`, `GERARDAS*17-19` | Emitir | Geram DAS | PDF | Fora do escopo atual |

Outros serviços com valor de **contexto**, não de cálculo:

| Serviço | Procuração | Uso possível |
|---|---|---|
| `SITFIS` `SOLICITARPROTOCOLO91` + `RELATORIOSITFIS92` | **00002** (Situação Fiscal) | Relatório de situação fiscal (assíncrono, PDF) anexado ao processo |
| `PAGTOWEB` `PAGAMENTOS71` | NÃO VERIFICADO | Confirmar pagamentos de DAS |
| `CAIXAPOSTAL` `MSGCONTRIBUINTE61` | NÃO VERIFICADO | Detectar intimações e comunicados de malha |
| `REGIMEAPURACAO` `CONSULTAROPCAOREGIME103` | NÃO VERIFICADO | Regime de caixa × competência (afeta a leitura das receitas) |
| `PROCURACOES` `OBTERPROCURACAO41` | n/a | Verificar se a procuração do cliente está vigente antes de consultar |
| `SICALC` `CONSOLIDAR54` (15/10/2026) | n/a | Consolida débito com acréscimos **sem emitir DARF**. Candidato a **conferência oficial** de multa e juros (verificar se cobre o DAS do Simples: NÃO VERIFICADO) |

## 3. Respostas às questões do escopo

| # | Questão | Resposta | Base |
|---|---|---|---|
| 1 | Serviços do Simples Nacional? | Sim: PGDAS-D, DEFIS, REGIMEAPURACAO, PARCSN/PERTSN/RELPSN | Catálogo |
| 2 | Consulta de declarações PGDAS-D? | **Sim**: `CONSDECLARACAO13`, `CONSULTIMADECREC14`, `CONSDECREC15` | Catálogo + página do serviço |
| 3 | Recuperar dados declarados? | **Sim, em PDF.** Receitas e RBT12 estruturados em JSON: **não** (os serviços de consulta devolvem PDF base64) | Página do serviço |
| 4 | Recibos, extratos, demonstrativos? | Sim: recibo, declaração, MAED e extrato do DAS em PDF | idem |
| 5 | Débitos? | Indiretamente: `dasPago`; PGMEI `DIVIDAATIVA24` (só MEI); parcelamentos; SITFIS | Catálogo |
| 6 | Situação fiscal? | Sim: SITFIS (procuração 00002) | Catálogo |
| 7 | Faturamento declarado? | Sim, no PDF da declaração (que o leitor atual já interpreta) | — |
| 8 | Dados para os cálculos do CheckFiscal? | Receita do PA, histórico e RBT12 (pela declaração), vencimento (pelo extrato) e sequência original/retificadora (pelo índice) | — |
| 9 | Certificado digital? | **Sim**: e-CNPJ do contratante | "Como contratar" |
| 10 | Procuração? | **Sim**: procuração eletrônica no e-CAC, **código 00146** para PGDAS-D. Software-house: Termo de Autorização assinado (`AUTENTICAPROCURADOR`/`ENVIOXMLASSINADO81`) | "Serviços × Procurações" |
| 11 | Contratação comercial? | Sim, Loja Serpro, empresas de qualquer porte | "Como contratar" |
| 12 | Autenticação? | Consumer Key/Secret do contrato → Bearer; mais `jwt_token` em produção e certificado. Detalhes de mTLS: página "Como autenticar" retornou 403, **NÃO VERIFICADO** | Modelos de autenticação |
| 13 | Limites e custos? | Preço por faixa de consumo mensal (consulta / emissão / declaração). **Valores NÃO VERIFICADO** | Notícias e "Como contratar" |
| 14 | O que vem estruturado? | Índice de declarações (JSON). Conteúdo da declaração: PDF | Página do serviço |
| 15 | Permitido ao perfil do CheckFiscal? | **Sim, se quem contrata for o escritório** (procurador dos clientes). Se o CheckFiscal virar um produto que intermedeia vários escritórios, o perfil é **software-house** e exige Termo de Autorização de cada escritório | Integra Contador, perfis |

### Distinções obrigatórias

| Operação | Disponível? | Observação |
|---|---|---|
| Consulta de dados declarados | Sim (PDF) | `CONSULTIMADECREC14` / `CONSDECREC15` |
| Consulta de situação fiscal | Sim | SITFIS, procuração 00002 |
| Consulta de débitos | Parcial | `dasPago`, parcelamentos, SITFIS |
| Recuperação de extratos | Sim (PDF) | `CONSEXTRATO16` |
| Recuperação de PDF | Sim | Todos os de consulta acima |
| Transmissão / retificação | Existe (`TRANSDECLARACAO11`) | **Proibida no CheckFiscal.** A decisão de retificar é do contador, fora do sistema |

## 4. Riscos

- **O layout do PDF devolvido pela API pode diferir** do PDF baixado do portal. É preciso validar o `pgdas_reader` com amostras reais antes de qualquer automação (NÃO VERIFICADO).
- **Custo variável por consulta.** Um processo com 3 a 6 PGDAS e um índice anual são cerca de 5 a 10 chamadas. Estimar com a tabela vigente da Loja Serpro antes da prova de conceito.
- **Credenciais do escritório** (e-CNPJ e Consumer Secret) passam a residir na máquina local. Ver §6.
- **Procurações vencidas:** checar com `OBTERPROCURACAO41` antes e exibir pendência, nunca falhar em silêncio.
- **Dependência de terceiro:** o upload manual continua sendo o caminho padrão e o fallback permanente.

## 5. Consulta Faturamento

É **inviável no escopo atual** (ver `api-catalog.md` §8). Exige credenciamento como destinatário no Compartilha Receita e consentimento ativo do titular por compartilhamento. O dado é de faturamento, não da receita declarada no PGDAS-D. Pode, no futuro, servir como **indício** para comparar com a malha, nunca como substituto do PGDAS.

## 6. Arquitetura de credenciais (quando aprovado)

Opções, da recomendada para a menos recomendada:

1. **Credencial por instalação, do próprio escritório.** O escritório contrata o Integra Contador, importa o e-CNPJ (`.pfx`) para o repositório de certificados do Windows e cadastra Consumer Key/Secret no CheckFiscal. Os segredos ficam no **Windows Credential Manager / DPAPI** (`keyring`). O CheckFiscal **nunca** distribui segredo próprio.
2. **Intermediação por serviço do fornecedor do CheckFiscal** (perfil software-house). Exige backend em nuvem, Termo de Autorização de cada escritório, LGPD de operador e SLA. Muda a natureza do produto, que hoje é local e sem nuvem. **Não recomendado agora.**
3. Segredo comercial embutido no executável: **proibido.** Pode ser extraído trivialmente do binário PyInstaller.

## 7. Recomendação

1. **Não iniciar** a integração antes de concluir as Fases 0 a 3 (`migration-plan.md`).
2. Fase 4: prova de conceito **somente leitura** com `CONSDECLARACAO13` + `CONSULTIMADECREC14` em 1 ou 2 clientes reais, comparando os PDFs da API com o `pgdas_reader`.
3. Critério para avançar: 100% dos PDFs de teste lidos pelo leitor existente; custo mensal estimado aprovado pelo escritório; procurações 00146 vigentes.
