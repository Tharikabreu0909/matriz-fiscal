# Blindagem comercial — versão 1.37

## Escopo da beta

- aplicação local;
- um operador por instalação;
- estimativa fiscal conservadora;
- períodos até 12/2026;
- onboarding e suporte assistidos.

## Controles implantados

1. CNPJ validado pelos dígitos verificadores.
2. Malha confrontada com CFDF/IE e razão social da empresa.
3. Divergências de identidade exigem confirmação explícita e ficam no histórico.
4. PDFs enviados a partir da 1.37 são armazenados localmente.
5. Backup inclui banco e documentos.
6. Restauração verifica estrutura e integridade do banco.
7. Pacote de suporte exclui documentos e valores fiscais.
8. Migrações do banco são registradas em `schema_migrations`.

## Limitações conhecidas

- sem autenticação;
- sem múltiplos escritórios;
- sem nuvem;
- sem atualização automática;
- executável Windows precisa ser compilado e assinado em ambiente próprio;
- leitores continuam limitados aos padrões de PDF já validados;
- não cobre PGDAS-A/CBS/IBS a partir de 2027.
