# Plano de migração Flask → PHP (Recibo Express)

Marca cada item quando estiver feito no código PHP (`recibo-php/`).

## Já implementado

- [x] Arranque: `public/index.php`, `bootstrap.php`, autoload Composer
- [x] Sessão + mensagens flash
- [x] Config empresa: ler/gravar `storage/config_empresa.json`
- [x] Páginas: **Início**, **Configurações** (formulário + salvar)
- [x] Upload **logo** e **watermark** → `public/static/uploads/`
- [x] Pastas `storage/`, `public/static/uploads`, `public/static/recibos`
- [x] `.htaccess` em `storage` (bloquear acesso web ao JSON)

## A migrar (espelho das rotas do `app.py`)

### PDF / comissões (núcleo)

- [ ] `GET previa` — pré-visualização tabela
- [ ] `POST upload` — upload PDF
- [ ] `POST gerar_recibos`
- [ ] `GET download_pdf`
- [ ] `GET imprimir_todos`
- [ ] `GET limpar`
- [ ] `GET teste_csv` (se ainda for necessário)

### Recibo avulso

- [ ] `GET recibo_avulso`
- [ ] `POST previa_recibo_avulso`
- [ ] `GET editar_recibo_avulso`
- [ ] `POST atualizar_recibo_avulso`
- [ ] `POST gerar_recibo_avulso_final`
- [ ] `GET download_recibo_avulso`

### Vale transporte / CSV

- [ ] `GET vale_transporte_ajuda_custo`
- [ ] `POST upload_csv_vale_transporte`
- [ ] `GET previa_csv_vale_transporte`
- [ ] `POST gerar_recibos_csv`
- [ ] `GET download_pdf_csv`
- [ ] `GET imprimir_csv`

### API / util

- [ ] `GET api/status`
- [ ] (Opcional) rotas só usadas pelo Vite no projecto antigo — não aplicável ao PHP puro

### Bibliotecas PHP sugeridas

| Necessidade | Pacote / abordagem |
|-------------|---------------------|
| PDF gerado | **TCPDF** ou **Dompdf** ou **mPDF** |
| Ler texto de PDF | **smalot/pdfparser** (ou extrair só tabelas conforme lógica actual) |
| CSV | `fgetcsv` / **league/csv** |
| Imagens | GD ou Imagick (se o servidor tiver) |

### Notas

- Toda a lógica grande que está em `app.py` (milhares de linhas) deve ir para classes em `src/Services/` por domínio (ex.: `ComissaoPdfService`, `ValeTransporteService`).
- Testar cada módulo na Hostinger com ficheiros reais antes de fechar o item.
