# Política local de dados — beta 1.37

## Armazenamento

No Windows, banco, PDFs, backups e logs ficam por padrão em `%LOCALAPPDATA%\CheckFiscal`.

## Backup

O backup completo contém banco e documentos originais. Deve ser armazenado em local seguro e com acesso restrito.

## Diagnóstico

O pacote de diagnóstico contém versão, ambiente, integridade, contagem de registros e logs. Não inclui PDFs nem valores fiscais extraídos.

## Exclusão

Ao excluir uma empresa, o sistema remove os registros e a pasta de documentos vinculada. Backups antigos continuam contendo os dados até serem eliminados pelo responsável.
