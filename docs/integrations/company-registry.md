# Cadastro inteligente de empresas

> Estratégia proposta. **Não implementada.** Depende da aprovação da ADR-002.

## 1. Situação atual

O cadastro é manual (`CompanyCreateRequest`, `app.py:300`): CNPJ (com dígitos verificadores validados em `services/security.py:13`), razão social, nome fantasia, inscrição estadual, cidade, UF, anexo padrão e observações. Não há origem por campo nem data de consulta.

**Particularidade do DF:** a malha identifica o contribuinte por **CFDF**, e o confronto com a empresa usa o campo `state_registration` (`security.validate_malha_identity`). **Nenhuma API pública pesquisada fornece o CFDF/IE de forma comprovada.** Ele continua sendo informado manualmente, e é o campo que mais vale a pena exigir, porque elimina a comparação por similaridade de nome.

## 2. Fluxo

```
Operador digita CNPJ
  → validar dígitos (local, já existe)
  → existe cadastro local? ─sim→ abrir; oferecer "atualizar dados públicos"
  → cache válido (≤ 30 dias)? ─sim→ usar cache
  → provedor primário (BrasilAPI) ──falha/timeout──► fallback configurado (cnpj.ai, se houver chave)
  → normalizar para CompanyRegistrySnapshot
  → detectar inconsistências (situação ≠ ATIVA, UF ≠ DF, CEP × ViaCEP, Simples = false)
  → pré-preencher o formulário com indicação "fonte: BrasilAPI · dados RFB de AAAA-MM"
  → operador revisa e corrige
  → salvar: valores confirmados + origem por campo + snapshot bruto
```

Offline: o passo do provedor falha rápido (timeout curto), o formulário fica manual e um aviso "consulta pública indisponível" é exibido. **Nada bloqueia o cadastro.**

## 3. Modelo de dados proposto (migração aditiva)

```sql
CREATE TABLE company_registry_lookups (      -- histórico e cache
  id INTEGER PRIMARY KEY,
  cnpj TEXT NOT NULL,
  provider TEXT NOT NULL,                  -- BRASILAPI | CNPJAI | MANUAL
  requested_at TEXT NOT NULL,
  status TEXT NOT NULL,                    -- OK | NOT_FOUND | ERROR | TIMEOUT | RATE_LIMITED
  http_status INTEGER,
  source_reference TEXT,                   -- ex.: competência dos dados abertos, se informada
  normalized_json TEXT,                    -- snapshot normalizado
  raw_sha256 TEXT,                         -- hash da resposta bruta (o bruto não guarda QSA)
  error_message TEXT
);
CREATE INDEX idx_registry_lookups_cnpj ON company_registry_lookups(cnpj, requested_at);

CREATE TABLE company_field_provenance (      -- origem de cada campo confirmado
  company_id INTEGER NOT NULL REFERENCES companies(id),
  field TEXT NOT NULL,                     -- legal_name, city, cnae_principal...
  value TEXT,
  source TEXT NOT NULL,                    -- PROVIDER | MANUAL | MALHA
  lookup_id INTEGER REFERENCES company_registry_lookups(id),
  confirmed_at TEXT NOT NULL,
  manual_override INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (company_id, field)
);
```

Novos campos opcionais em `companies` (aditivos e anuláveis): `cnae_principal`, `cnaes_secundarios_json`, `natureza_juridica`, `porte`, `data_abertura`, `situacao_cadastral`, `data_situacao_cadastral`, `logradouro`, `numero`, `complemento`, `bairro`, `cep`, `codigo_municipio_ibge`, `matriz_filial`, `simples_publico` (`TRUE`/`FALSE`/`NULL`), `simei_publico`, `registry_checked_at`.

## 4. Regras

1. **Correção manual prevalece.** Um campo com `manual_override = 1` nunca é sobrescrito por uma nova consulta. A UI mostra "o provedor diz X; você confirmou Y" e pede uma ação explícita.
2. **Atualizar não é sobrescrever.** "Atualizar dados públicos" gera um diff campo a campo; o operador aceita item a item.
3. **Simples e SIMEI** vindos de dados abertos são apenas informação. O enquadramento no processo continua sendo uma decisão do contador. As datas de opção e exclusão não são exibidas sem o booleano coerente (ver o alerta em `api-catalog.md` §1).
4. **QSA não é persistido por padrão** (dado pessoal, sem finalidade no fluxo). Se for necessário, guardar com aviso de LGPD.
5. **Cache:** TTL de 30 dias, porque a origem é mensal. O botão "forçar consulta" respeita o rate limit.
6. **Timeout:** 6 s por provedor (a BrasilAPI corta o upstream em 5 s). **Retry:** no máximo 2, com backoff exponencial e jitter (0,5 s → 1,5 s), **só** para 5xx, 429 (respeitando `Retry-After`) e erro de conexão. Nunca para 4xx.
7. **Rate limit local:** token bucket por provedor (BrasilAPI: 1 requisição/s, conservador; cnpj.ai: 60/min, como publicado).
8. **Fallback configurável:** lista ordenada em `settings` (`["BRASILAPI", "CNPJAI"]`); um provedor sem credencial é pulado.
9. **Credencial da cnpj.ai:** fornecida **pelo operador**, por instalação, guardada no Windows Credential Manager (`keyring`) ou, no Docker, em arquivo fora do volume de dados com permissão 600. Nunca no banco em texto puro, nunca no executável e nunca no pacote de suporte.

## 5. Contrato do adaptador

```python
class CompanyRegistryProvider(Protocol):
    name: str
    def lookup(self, cnpj: str) -> RegistryLookupResult: ...

@dataclass(frozen=True)
class RegistryLookupResult:
    status: Literal["OK", "NOT_FOUND", "ERROR", "TIMEOUT", "RATE_LIMITED"]
    snapshot: CompanyRegistrySnapshot | None
    provider: str
    fetched_at: datetime
    source_reference: str | None
    raw_sha256: str | None
```

O domínio (`company_registry/domain`) só conhece `CompanyRegistrySnapshot`. O formato da BrasilAPI fica no adaptador.

## 6. Testes

- **Contrato:** fixtures gravadas (respostas reais **sanitizadas**: CNPJ público de órgão, sem QSA de pessoa física) para BrasilAPI (200, 404, 503) e cnpj.ai (200, 401, 429 com `Retry-After`).
- **Normalização:** o alerta de datas do Simples sem opção vira `simples_publico = False` e as datas são descartadas.
- **Falhas:** timeout, conexão recusada, JSON inválido, campo ausente → o formulário segue manual.
- **Regra de override:** uma nova consulta não altera campo confirmado manualmente.
- **Nenhum teste chama a rede** (adaptador injetado).
