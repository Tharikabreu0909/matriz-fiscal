# CheckFiscal 1.37 — Blindagem Comercial

## Entregue

- CNPJ com validação de dígitos verificadores.
- Conferência de identidade da malha por CFDF/IE e razão social.
- Bloqueio de malha incompatível e confirmação manual auditada.
- Guarda dos PDFs originais enviados a partir desta versão.
- Download dos documentos dentro do processo.
- Backup completo e restauração com cópia de segurança automática.
- Pacote de diagnóstico sem documentos fiscais e sem valores extraídos.
- Logs rotativos de operação e erros.
- Migrações de banco explícitas e versionadas.
- Dados persistentes em `%LOCALAPPDATA%\CheckFiscal` no Windows.
- Inicialização mais rápida após a primeira instalação das dependências.
- Estudo contábil desativado na API comercial.
- Scripts para compilar um pacote Windows em ambiente próprio.

## Preservado

- design da versão 1.36;
- leitor da malha;
- leitor PGDAS;
- planejador de documentos;
- análise Tipo 01 e Tipo 17;
- motor tributário e reflexos;
- multa e juros;
- relatório do cliente.

## Ainda necessário para SaaS público

- autenticação;
- escritórios e usuários;
- permissões;
- banco PostgreSQL;
- armazenamento em nuvem;
- cobrança e assinatura;
- executável Windows compilado, assinado e testado;
- ampliação da matriz de casos tributários reais;
- adaptação ao PGDAS-A e às regras de 2027.
