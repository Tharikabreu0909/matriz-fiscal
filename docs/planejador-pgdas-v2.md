# Planejador de PGDAS v2

## Entrada

Competências tipo 17 encontradas na malha e a data atual.

## Saída inicial

1. PGDAS necessários para analisar as competências da malha;
2. PGDAS posterior mais recente disponível para calcular os reflexos da
   competência tipo 17 mais recente.

## Exemplo

Em 22/07/2026, para uma malha em 11/2025:

- solicitar PGDAS 11/2025;
- solicitar PGDAS 06/2026;
- calcular receitas posteriores reais até 06/2026;
- deixar 07/2026 a 11/2026 como períodos futuros pendentes.

## Regra de segurança

Um PGDAS posterior não substitui o PGDAS da própria competência. O histórico
pode confirmar a receita, mas não preserva todos os dados específicos da
apuração daquele PA com o mesmo nível de segurança.
