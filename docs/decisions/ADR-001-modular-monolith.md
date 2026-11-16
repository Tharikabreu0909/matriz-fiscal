# ADR-001 — Monólito modular com camadas leves

- **Status:** Proposta (aguarda aprovação)
- **Data:** 22/10/2026
- **Contexto de evidência:** `docs/architecture/current-state.md`, `dependency-map.md`

## Contexto

O CheckFiscal é uma aplicação local de um operador, com SQLite e cerca de 12 mil linhas de Python. As regras fiscais já estão em funções puras (`services/`). Os problemas reais são:

- `app.py` mistura HTTP, orquestração, mutação de análise e transições de status (3 cópias divergentes);
- `database.py` não oferece transação por caso de uso e guarda o domínio em JSON sem versão;
- a mesma regra fiscal (precedência de receitas) está implementada três vezes;
- o leitor de malha é específico do DF, sem ponto de extensão.

## Decisão

Adotar um **monólito modular** organizado por domínio (`shared_kernel`, `company_registry`, `malha`, `pgdas`, `analysis`, `taxation`, `reports`, `processes`, `system`) com quatro camadas leves (`domain`, `application`, `infrastructure`, `api`) e dependências apontando para o domínio. As integrações externas ficam em `integrations/`, atrás de ports declarados por cada módulo. A migração segue o padrão **strangler**: `app.py` vira um shim e as rotas migram uma a uma, mantendo o contrato JSON.

## Alternativas consideradas

| Alternativa | Motivo da rejeição |
|---|---|
| Manter como está, só corrigir bugs | Não resolve a duplicação de regra fiscal nem a ausência de transação; cada correção fiscal continua exigindo mexer em `app.py` |
| Microsserviços / fila | Um operador, sem nuvem, sem escala. Custo operacional e de distribuição sem benefício |
| Clean Architecture "completa" (interfaces e DTOs por camada, ORM) | Cerimônia desproporcional ao tamanho; o domínio já é funcional e puro |
| Reescrever com outro framework ou SPA | Risco alto sem ganho fiscal; a UI atual funciona |

## Consequências

- (+) Uma única implementação por regra fiscal, testável isoladamente.
- (+) Pontos de extensão claros: novos leitores de malha (UF), novos provedores.
- (+) Transações por caso de uso eliminam estados parciais.
- (−) Período de convivência entre código antigo e novo; exige testes de caracterização antes de mover.
- (−) Imports mudam; o `checkfiscal.spec` precisa listar o pacote (o que, de quebra, corrige C-6).

## Critérios de revisão

Rever esta decisão se o produto passar a ser multiescritório ou hospedado (aí a autenticação e o backend intermediário viram requisito).
