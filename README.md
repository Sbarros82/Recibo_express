# 🧾 Recibo Express v2.0

**Gerador Automático de Recibos de Comissão**

Sistema web moderno para geração automática de recibos de comissão a partir de relatórios PDF, com interface intuitiva e design responsivo.

## ✨ Funcionalidades

- 📄 **Upload de PDF**: Interface drag-and-drop para upload de relatórios
- 🤖 **Processamento Automático**: Extração automática de dados do PDF
- 📁 **Organização por Setor**: Recibos organizados automaticamente por departamento
- 📦 **Download em ZIP**: Todos os recibos em um arquivo compactado
- 🎨 **Interface Moderna**: Design responsivo e intuitivo
- 🔒 **Segurança**: Processamento local, arquivos temporários removidos automaticamente

## 🚀 Início Rápido

### Windows
1. **Duplo clique** no arquivo `iniciar_servidor.bat`
2. Aguarde a instalação automática das dependências
3. O navegador abrirá automaticamente em `http://localhost:5000`

### Linux/Mac
```bash
python3 start_server.py
```

### Manual
```bash
# Instalar dependências
pip install -r requirements.txt

# Iniciar servidor
python app.py
```

## 📋 Requisitos

- **Python 3.7+**
- **Navegador web moderno**
- **Conexão com internet** (apenas para fontes e ícones)

## 🛠 Tecnologias

- **Backend**: Flask 3.0.0
- **Frontend**: HTML5, CSS3, JavaScript
- **PDF**: pdfplumber, reportlab
- **Dados**: pandas
- **Números**: num2words

## 📖 Como Usar

1. **Acesse** o sistema em `http://localhost:5000`
2. **Faça upload** do relatório PDF (formato do sistema)
3. **Aguarde** o processamento automático
4. **Baixe** os recibos organizados por setor

## 📁 Estrutura de Saída

```
static/recibos/
├─ Emissores/
├─ Executivos de Contas/
├─ Diretor Comercial/
├─ Gerente Operacional/
└─ Supervisores/
```

## ⚙️ Configurações

### Porta do Servidor
Por padrão, o servidor roda na porta 5000. Para alterar:

```python
# No arquivo app.py, linha final:
app.run(debug=True, host='0.0.0.0', port=5000)  # Altere a porta aqui
```

### Formatos Suportados
- **Entrada**: PDF (.pdf)
- **Saída**: PDF (.pdf), ZIP (.zip)

## 🔧 Solução de Problemas

### Python não encontrado
- **Windows**: Instale Python de [python.org](https://www.python.org/downloads/)
- **Linux**: `sudo apt install python3 python3-pip`
- **Mac**: `brew install python3`

### Dependências não instaladas
```bash
pip install -r requirements.txt
```

### Porta em uso
O sistema tentará automaticamente uma porta alternativa, ou altere manualmente no código.

### Erro de permissão
- **Windows**: Execute como administrador
- **Linux/Mac**: Use `sudo` se necessário

## 📞 Suporte

Para problemas ou sugestões:
1. Verifique se todas as dependências estão instaladas
2. Confirme que o Python 3.7+ está instalado
3. Teste com um arquivo PDF simples primeiro

## 🎯 Versão

**v2.0** - Interface moderna, drag-and-drop, design responsivo

---

*Desenvolvido com ❤️ para facilitar a geração de recibos de comissão*
