# Estudo de Migração — Python (Flask) → PHP
## Recibo Express v2.0

**Data:** 2026-05-25
**Pergunta central:** migrar para **PHP puro** ou **Laravel**, sem perder funcionalidade nem a agilidade na geração de recibos?

---

## 1. Por que considerar a migração

A motivação **não é técnica do código** — o app Flask funciona bem. É de **hospedagem**:

- A Hostinger/Hostgator (planos shared) executam **PHP nativamente**, sem configuração.
- Python exige ativar "Python App" via Passenger, que dá 404/403 e muitas vezes **só funciona em VPS** (custo maior). Isso está documentado nos próprios arquivos do projeto (`GUIA_SIMPLES_HOSTINGER.md`, `ERRO_404_PASSENGER.md`).

> **Em uma frase:** migrar para PHP troca um problema crônico de deploy por uma instalação trivial de "subir arquivos por FTP".

---

## 2. Mapeamento de dependências (o que tem equivalente)

| Função no Flask | Biblioteca Python | Equivalente PHP | Dificuldade |
|-----------------|-------------------|-----------------|-------------|
| Rotas / framework | Flask | PHP puro (router simples) **ou** Laravel | Baixa |
| Templates | Jinja2 | PHP nativo / Twig / Blade | Baixa |
| Sessão | Flask session | `$_SESSION` / `session()` | Baixa |
| **Gerar PDF do recibo** | reportlab (canvas) | **mPDF** ou **Dompdf** (HTML→PDF) | **Baixa** ✅ |
| Processar CSV | csv (stdlib) | `fgetcsv` / **League\Csv** | Baixa |
| Config JSON | json | `json_encode/decode` | Baixa |
| Valor por extenso | função própria | função própria (portar) / pacote | Baixa |
| **Extrair dados do PDF** | **pdfplumber** | **smalot/pdfparser** (só texto) | **ALTA** ⚠️ |
| Upload / saneamento | werkzeug | nativo PHP | Baixa |

### 2.1 O ponto fácil: gerar PDF (reportlab → mPDF)
Hoje os recibos são desenhados por **coordenadas absolutas** (`c.drawString(50, y_pos, ...)`) — verboso e duplicado em 5 funções. Em PHP, com **mPDF/Dompdf**, o mesmo recibo vira **um template HTML+CSS**. Isso é **mais simples, mais fácil de ajustar e elimina a duplicação**. Aqui a migração até **melhora** o projeto.

### 2.2 O ponto crítico: extrair dados do PDF de comissões
`pdfplumber.extract_tables()` reconstrói **tabelas** lendo a posição (x/y) de cada palavra na página. **Nenhuma biblioteca PHP faz isso bem.** `smalot/pdfparser` extrai **texto**, não a grade de colunas. O código atual depende de índices de coluna fixos (`row[3]`=nome, `row[10]`=comissão, `row[11]`=origem) — **isso não se reproduz fielmente em PHP**.

Existe um fallback por texto+regex no código atual, mas é o caminho menos confiável. **Este é o único risco real da migração.**

---

## 3. As três saídas para o problema do PDF (decisão-chave)

| Opção | Descrição | Recomendação |
|-------|-----------|--------------|
| **3A. Trocar a entrada para CSV/Excel** | Pedir ao sistema MASTEROP a exportação do relatório em CSV/XLSX em vez de PDF. O fluxo de vale-transporte **já funciona assim**. | ⭐ **Melhor.** Elimina toda a fragilidade do `pdfplumber`, torna a migração trivial e deixa o sistema mais robusto **independente da linguagem**. |
| **3B. Microserviço Python só p/ parsing** | PHP faz tudo; um pequeno serviço Python (em VPS/Render/PythonAnywhere) só lê o PDF e devolve JSON. | Boa se o PDF for inegociável. Mantém o melhor de cada mundo, mas exige hospedar 2 coisas. |
| **3C. Parsing 100% em PHP** | Reescrever a extração com `smalot/pdfparser` + regex. | Só se o PDF tiver layout textual estável. Exige **prova de conceito obrigatória** antes de decidir. |

> **Recomendação:** validar **3A** primeiro (uma conversa com quem gera o relatório). Se viável, é a opção que mais protege a "agilidade" pedida.

---

## 4. PHP puro vs. Laravel

| Critério | PHP puro + libs (Composer) | Laravel |
|----------|----------------------------|---------|
| Tamanho do app (5 fluxos, sem BD) | ✅ Sob medida | ⚠️ Sobredimensionado |
| Deploy em shared hosting | ✅ Sobe por FTP, funciona | ⚠️ Precisa Composer no servidor, apontar docroot p/ `/public`, etc. |
| Curva / manutenção | ✅ Simples, direto | ⚠️ Mais conceitos (Eloquent, Artisan...) que aqui não se usam |
| Recursos prontos (auth, BD, fila) | ➖ Instala só o que precisa | ✅ Tudo incluso (mas o projeto não usa) |
| Performance em hospedagem básica | ✅ Leve | ➖ Mais pesado |

**Conclusão:** para **este** projeto (pequeno, sem banco, alvo shared hosting), **PHP puro com 3 bibliotecas via Composer** é o ponto ideal:
- `mpdf/mpdf` — gerar os recibos (HTML→PDF)
- `league/csv` — ler os CSVs
- `smalot/pdfparser` — **só se** escolher a opção 3C

Laravel só se valeria a pena se o roadmap incluir **login multiusuário, histórico em banco, multiempresa** — aí a estrutura do Laravel compensa.

---

## 5. Arquitetura proposta (PHP puro)

```
public_html/
├─ index.php             # front controller + router simples
├─ src/
│  ├─ Recibo.php         # geração de PDF (mPDF) — 1 classe, sem duplicação
│  ├─ ExtratorCsv.php    # League\Csv
│  ├─ ExtratorPdf.php    # (opção 3C) ou cliente do microserviço (3B)
│  ├─ Extenso.php        # valor por extenso (porte direto da função atual)
│  └─ Config.php         # lê/grava config_empresa.json
├─ views/                # templates HTML dos recibos e das telas
├─ static/recibos/       # PDFs gerados (igual ao atual)
├─ uploads/              # temporários
└─ vendor/               # Composer
```
O mapeamento de rotas é praticamente 1:1 com o Flask atual — nenhuma URL precisa mudar.

---

## 6. A "agilidade na geração de recibos" é preservada?

**Sim**, e pode até melhorar:

| Aspecto da agilidade | Situação após migração |
|----------------------|------------------------|
| Fluxo upload → prévia → gerar | Idêntico (mesmas telas, mesmas URLs). |
| Geração em lote (1 PDF, N páginas) | mPDF faz nativamente; mesma velocidade. |
| Ajustar layout do recibo | **Mais ágil** — editar HTML/CSS em vez de coordenadas. |
| Recibo avulso e VT/AC (CSV) | Portam direto, sem risco. |
| Valor por extenso, moeda, datas | Portam direto (lógica simples). |
| Extração do PDF de comissões | **Único ponto que pode perder agilidade** — mitigado pela opção 3A/3B. |

---

## 7. Plano de migração faseado (sugestão)

1. **Fase 0 — Decisão sobre o PDF (1–2 dias):** verificar se o relatório de comissões pode sair em CSV/Excel (opção 3A). Esta decisão define todo o resto.
2. **Fase 1 — Esqueleto PHP (2–3 dias):** router, sessão, telas, config JSON, upload. Sem PDF ainda.
3. **Fase 2 — Geração de PDF (3–4 dias):** classe `Recibo` com mPDF para os 3 tipos (comissão, avulso, VT/AC). Validar visualmente contra os PDFs atuais em `static/recibos/`.
4. **Fase 3 — Entrada de dados (2–5 dias):** CSV de VT/AC (fácil) + comissões (CSV se 3A; senão PoC do parser PDF).
5. **Fase 4 — Paridade e testes (2–3 dias):** comparar recibo a recibo com a versão Flask; ajustar regras hardcoded para configuração.
6. **Fase 5 — Deploy:** subir em `public_html`, rodar `composer install` (ou subir `vendor/` pronto), testar.

**Esforço total estimado:** ~2 a 3 semanas para 1 desenvolvedor, sendo a Fase 0/3 a de maior incerteza.

---

## 8. Melhorias recomendadas (independente da linguagem)

Estas valem **mesmo se ficar em Python**, e devem ser feitas durante a migração:
1. **Padronizar entrada em CSV/Excel** (mata o risco do PDF). — *maior alavanca*
2. **Externalizar regras hardcoded** ("MASTEROP", "ANA CAROLINA", padrões de total) para `config`.
3. **Unificar os 5 geradores de PDF** em um só template parametrizado.
4. **Remover `debug=True`, `secret_key` fixa e `print()`** de produção.
5. **Adicionar autenticação simples** se o app for ficar exposto na internet.

---

## 9. Recomendação final

1. **Vale a pena migrar?** Sim — **se o objetivo é hospedar barato em shared hosting**, PHP resolve a dor de raiz. Se um VPS for aceitável, **manter o Flask** (zero retrabalho) também é válido.
2. **PHP puro ou Laravel?** **PHP puro** com mPDF + League\Csv. Laravel é overkill aqui.
3. **Faça a Fase 0 antes de tudo:** confirme se o relatório de comissões pode vir em CSV/Excel. Essa única decisão determina se a migração é "tranquila" (3A) ou "tem 1 risco a gerenciar" (3B/3C).
4. **A agilidade é mantida** em todos os fluxos; o desenho do recibo até fica mais fácil de manter em HTML/CSS.
