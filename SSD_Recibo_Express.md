# SSD — Documento de Especificação de Software
## Recibo Express v2.0

**Cliente / Domínio:** MASTEROP — Operadora Turística (Maceió-AL)
**Data:** 2026-05-25
**Autor da especificação:** Engenharia (análise reversa do código existente)
**Status:** Sistema em produção (Flask/Python), em estudo de migração

---

## 1. Visão Geral

O **Recibo Express** é uma aplicação web para **geração automatizada de recibos em PDF**. Ele recebe dados de pagamento (via PDF, CSV ou formulário manual), processa, permite revisão prévia e emite recibos no padrão tradicional brasileiro ("Recebi de... a quantia de... referente...").

### 1.1 Objetivo de negócio
Eliminar a criação manual de recibos de comissão, premiação, vale-transporte e ajuda de custo, garantindo padronização, valor por extenso correto e emissão em lote a partir de relatórios já existentes.

### 1.2 Atores
| Ator | Descrição |
|------|-----------|
| Operador administrativo | Único perfil. Faz upload, revisa, gera, baixa e imprime recibos. Não há autenticação. |
| Sistema MASTEROP (externo) | Origem do relatório PDF de comissões consumido pelo app. |

### 1.3 Arquitetura atual (as-is)
```
Navegador (HTML/CSS/JS + Jinja2)
        │  HTTP
        ▼
Flask 3.0  ──── sessão server-side (cookie)
   │  ├─ pdfplumber  → extrai dados do PDF de comissões
   │  ├─ reportlab   → desenha os recibos em PDF (canvas absoluto)
   │  ├─ csv (stdlib)→ processa vale-transporte/ajuda de custo
   │  └─ json        → config_empresa.json
        ▼
Sistema de arquivos
   ├─ uploads/            (temporário, removido após uso)
   ├─ static/recibos/     (PDFs gerados)
   └─ static/uploads/     (logo_empresa.png, watermark_empresa.png)
```
- **Porta:** 5002. **Deploy alvo:** shared hosting via `passenger_wsgi.py`.
- **Persistência:** não há banco de dados. Estado entre etapas vive na **sessão**; resultados vivem no **disco**.

---

## 2. Requisitos Funcionais

### Módulo A — Recibos de Comissão (a partir de PDF)
| ID | Requisito | Origem no código |
|----|-----------|------------------|
| RF-A1 | Upload de relatório PDF (drag-and-drop ou seleção), validação de extensão e tamanho. | `/upload`, `allowed_file` |
| RF-A2 | Extração automática dos dados: nome, classificação→setor, valor de **Comissão** e **Premiação** por funcionário. | `extrair_dados_pdf` |
| RF-A3 | Estratégia dupla de extração: primeiro por **tabela** (`extract_tables`), com fallback por **texto** (regex). | `extrair_dados_pdf` |
| RF-A4 | Unificação de funcionários duplicados e soma de comissão+premiação = total. | `funcionarios_unificados` |
| RF-A5 | Agrupamento e ordenação por setor (Emissores, Executivos, Supervisores, Diretor, Gerente, Serviços Gerais). | `ordem_setores` |
| RF-A6 | Filtros de limpeza: ignora registros `ZZZ_`, linhas de total, valores acima de limites, prefixos de nome (`T.RIZ `, `A `, etc.), cabeçalhos. | múltiplos filtros |
| RF-A7 | Regra de negócio fixa: "ANA CAROLINA ... FEITOSA" é forçada ao setor Diretor. | hardcoded |
| RF-A8 | Prévia dos dados extraídos antes de gerar. | `/previa` |
| RF-A9 | Geração de **PDF único** com 1 recibo por página, com discriminação de Comissão/Gratificação. | `gerar_pdf_unico` |
| RF-A10 | Download e visualização para impressão do PDF gerado. | `/download_pdf`, `/imprimir_todos` |

### Módulo B — Recibo Avulso (manual)
| ID | Requisito | Origem |
|----|-----------|--------|
| RF-B1 | Formulário: nome, valor, data, observações, referência. | `/recibo_avulso` |
| RF-B2 | Validação e conversão de valor em formato brasileiro (`1.234,56`). | `previa_recibo_avulso` |
| RF-B3 | Tela de prévia/edição com valor por extenso e valor formatado. | `/editar_recibo_avulso`, `/atualizar_recibo_avulso` |
| RF-B4 | Geração do recibo individual em PDF, download. | `gerar_recibo_individual`, `/download_recibo_avulso` |

### Módulo C — Vale-Transporte & Ajuda de Custo (a partir de CSV)
| ID | Requisito | Origem |
|----|-----------|--------|
| RF-C1 | Upload de CSV com colunas `Funcionário`, `descrição`, `Valor`. | `/upload_csv_vale_transporte` |
| RF-C2 | Detecção automática de encoding (utf-8-sig, utf-8, latin-1, cp1252, iso-8859-1) e delimitador. | `processar_csv_vale_transporte` |
| RF-C3 | Classificação do tipo pelo texto da descrição ("ajuda de custo" / "vale transporte"). | idem |
| RF-C4 | Prévia, geração de PDF único, download e impressão. | `/previa_csv_vale_transporte`, `/gerar_recibos_csv`, `/download_pdf_csv`, `/imprimir_csv` |
| RF-C5 | Mês de referência = mês subsequente ao atual. | `gerar_recibo_vale_transporte` |

### Módulo D — Configurações
| ID | Requisito | Origem |
|----|-----------|--------|
| RF-D1 | Editar dados da empresa (nome, endereço, telefone, email, site) salvos em `config_empresa.json`. | `/configuracoes`, `/salvar_configuracoes` |
| RF-D2 | Upload de logo (`logo_empresa.png`) exibida no cabeçalho do recibo. | `/upload_logo` |
| RF-D3 | Upload de imagem de fundo / papel timbrado (`watermark_empresa.png`). | `/upload_watermark` |

### Módulo E — Utilitários
| ID | Requisito | Origem |
|----|-----------|--------|
| RF-E1 | Conversão de número para extenso em português (reais e centavos). | `numero_para_palavras` |
| RF-E2 | Limpar todos os recibos gerados. | `/limpar` |
| RF-E3 | Endpoint de status do servidor (JSON). | `/api/status` |
| RF-E4 | Página informativa do frontend Vite (placeholder). | `/app` |

---

## 3. Requisitos Não-Funcionais

| ID | Categoria | Requisito |
|----|-----------|-----------|
| RNF-1 | Usabilidade | Interface responsiva (sidebar + cards), drag-and-drop, mensagens de feedback (flash), barra de progresso. |
| RNF-2 | Localização | Tudo em pt-BR: moeda `R$ 1.234,56`, datas `dd/mm/aaaa`, valor por extenso, nomes de meses. |
| RNF-3 | Robustez de entrada | Múltiplos encodings e delimitadores no CSV; saneamento de nomes de arquivo. |
| RNF-4 | Segurança | `secure_filename`, `safe_join`, remoção de uploads temporários, processamento local. **Limitação:** sem autenticação, `secret_key` fixa no código, `debug=True`. |
| RNF-5 | Desempenho | Geração em lote em um único passe; PDFs servidos do disco. |
| RNF-6 | Portabilidade / Deploy | **Ponto crítico:** requer Python+Passenger no servidor — incompatível com a maioria dos planos shared hosting (Hostinger/Hostgator). Ver estudo de migração. |
| RNF-7 | Manutenibilidade | Monólito de ~2.800 linhas; muita duplicação entre as funções `gerar_*` (layout repetido 5×); logs de debug em produção. |

---

## 4. Modelo de Dados (estruturas em memória/sessão)

```
Funcionário (comissão)        Registro CSV (VT/AC)         Recibo Avulso
├─ nome                       ├─ nome                      ├─ nome
├─ setor                      ├─ tipo (vt|ajuda_custo)     ├─ valor / valor_formatado
├─ comissao                   ├─ descricao                 ├─ data / data_br
├─ premiacao                  ├─ valor                     ├─ observacoes
├─ valor (total)             └─ data                      ├─ referencia
└─ data                                                    └─ valor_por_extenso
```
`config_empresa.json`: `{ nome_empresa, endereco, telefone, email, site }`

Não há entidades persistidas em banco. **Implicação para migração:** não há esquema relacional a recriar — apenas estruturas transitórias e arquivos.

---

## 5. Interfaces (rotas HTTP)

| Método | Rota | Função |
|--------|------|--------|
| GET | `/` | Dashboard |
| POST | `/upload` | Upload PDF comissões |
| GET | `/previa` | Prévia comissões |
| POST | `/gerar_recibos` | Gera PDF comissões |
| GET | `/download_pdf` · `/imprimir_todos` | Baixar / imprimir |
| GET | `/recibo_avulso` | Formulário avulso |
| POST | `/previa_recibo_avulso` · `/atualizar_recibo_avulso` · `/gerar_recibo_avulso_final` | Fluxo avulso |
| GET | `/editar_recibo_avulso` · `/download_recibo_avulso` | Editar / baixar avulso |
| GET | `/vale_transporte_ajuda_custo` | Página VT/AC |
| POST | `/upload_csv_vale_transporte` · `/gerar_recibos_csv` | Fluxo CSV |
| GET | `/previa_csv_vale_transporte` · `/download_pdf_csv` · `/imprimir_csv` | Prévia / baixar / imprimir |
| GET/POST | `/configuracoes` · `/salvar_configuracoes` · `/upload_logo` · `/upload_watermark` | Configurações |
| GET | `/limpar` · `/api/status` · `/teste_csv` · `/app` | Utilitários |

---

## 6. Regras de Negócio (extraídas)

1. **Valor por extenso** obrigatório em todo recibo (até milhares + centavos).
2. **Comissão**: mês de referência = mês **anterior**. **VT/Ajuda de custo**: mês **subsequente**.
3. **Discriminação**: comissão e premiação ("Gratificação") aparecem separadas quando > 0.
4. **Limpeza de nomes**: remoção de prefixos de classificação e sufixo " COMISSAO".
5. **Exclusões**: `ZZZ_*`, totais/subtotais, valores acima de R$ 100 mil na extração de tabela.
6. Local fixo de emissão: **"MACEIÓ-AL"**. Remetente fixo: **"Recebi de MASTEROP"**.

> ⚠️ Diversas regras estão **hardcoded** (nome da empresa "MASTEROP", padrões de totais específicos, correção da "ANA CAROLINA"). Devem virar configuração no destino da migração.

---

## 7. Riscos e Dívidas Técnicas

| Risco | Severidade | Nota |
|-------|-----------|------|
| Deploy Python em shared hosting | **Alta** | Motivador principal da migração. |
| Extração de tabela de PDF frágil (regras hardcoded a 1 layout) | **Alta** | Quebra se o relatório MASTEROP mudar de formato. |
| Duplicação de layout em 5 funções `gerar_*` | Média | Dificulta manutenção. |
| `debug=True`, `secret_key` fixa, sem auth | Média | Inadequado para produção pública. |
| `print()` de debug em produção | Baixa | Ruído/lentidão. |
| Sessão guardando listas grandes de dados | Baixa | Pode estourar cookie em relatórios muito grandes. |

---

## 8. Conclusão da especificação
O sistema é um **monólito pequeno e bem delimitado** (3 fluxos de geração + config), **sem banco de dados**, cuja complexidade real está concentrada em **dois pontos**: (a) extração de dados do PDF de comissões e (b) desenho dos recibos em PDF. Esses dois pontos definem todo o esforço e risco de uma eventual migração — detalhados no documento **ESTUDO_MIGRACAO_PHP.md**.
