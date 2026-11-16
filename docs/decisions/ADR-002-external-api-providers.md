# ADR-002 — Provedores externos por adaptadores, com o modo offline como padrão

- **Status:** Proposta (aguarda aprovação)
- **Data:** 22/10/2026
- **Evidência:** `docs/integrations/api-catalog.md`, `company-registry.md`, `fiscal-services.md`

## Contexto

Hoje a única chamada externa é a do BCB (`services/legal_charges.py:106`): `urllib` direto, sem cache, sem retry e sem registro dos valores usados. Queremos integrar consulta de CNPJ (BrasilAPI e opcionalmente cnpj.ai), CEP (ViaCEP) e, no futuro, o Integra Contador.

Fatos verificados que moldam a decisão:

- BrasilAPI, Minha Receita e cnpj.ai **têm a mesma origem** (dados abertos da RFB, defasagem mensal). Fallback entre eles melhora a disponibilidade, não a atualidade.
- A BrasilAPI pede uso "de pessoa real"; a cnpj.ai limita a 60 requisições/min e desaconselha chave em app distribuído.
- O Integra Contador exige contrato, e-CNPJ e procuração por cliente.

## Decisão

1. **Cada módulo declara um port** (`Protocol`) para o dado de que precisa: `CompanyRegistryProvider`, `AddressProvider`, `SelicSource`, `PgdasSource`. Adaptadores em `integrations/`.
2. **Cliente HTTP único** (`integrations/http.py`) com timeout por provedor, retry com backoff exponencial e jitter só para 5xx/429/erro de rede, respeito a `Retry-After`, rate limit local (token bucket), User-Agent com a versão real e **sem registrar payloads**.
3. **Cache e histórico em SQLite** para toda consulta externa (`*_lookups`), com status, provedor, data e hash da resposta. Resultados usados em cálculo (Selic) são **copiados para o snapshot do cálculo** (ADR-003).
4. **O modo offline é o padrão funcional**: nenhuma consulta externa bloqueia cadastro, importação ou análise. Só os juros exigem a Selic; com cache, funcionam offline para meses já obtidos.
5. **Fallback configurável** em `settings` (ordem dos provedores); um provedor sem credencial é ignorado.
6. **Credenciais por instalação**, fornecidas pelo escritório e guardadas via `keyring` (Windows Credential Manager/DPAPI) ou em arquivo 600 no Docker. **Nenhum segredo no executável, no repositório, no banco em claro ou no pacote de suporte.**
7. **Testes nunca dependem de rede**: contratos via respostas gravadas e sanitizadas.
8. **Proibido** scraping de portais autenticados ou com CAPTCHA como solução padrão.

## Alternativas

| Alternativa | Rejeição |
|---|---|
| Chamar provedores direto da rota | Repete o problema atual (`legal_charges`), sem teste nem cache |
| Biblioteca de terceiros para CNPJ | Acopla o formato e a política de terceiros; pouco ganho |
| Backend próprio intermediando APIs | Muda a natureza local e sem nuvem do produto; reavaliar só no perfil software-house |
| Serpro Consulta CNPJ como primário | Pago, e o dado público atende o cadastro |

## Consequências

- (+) Troca de provedor sem tocar no domínio; testes determinísticos.
- (+) Cálculos reprodutíveis (Selic gravada).
- (−) Mais uma tabela por integração; política de retenção do cache necessária (LGPD).
