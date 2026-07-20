# Deploy no Vercel — Recibo Express

## Pré-requisitos

- Conta no [Vercel](https://vercel.com)
- Repositório Git (GitHub, GitLab ou Bitbucket)
- [Vercel CLI](https://vercel.com/docs/cli) (opcional, para deploy local)

## Estrutura criada para o Vercel

```
recibo-express/
├── api/index.py       ← entrada serverless (Flask)
├── vercel.json        ← rotas e timeout (60s)
├── app.py             ← aplicação adaptada para serverless
├── templates/
├── static/
├── config_empresa.json
└── requirements.txt
```

## Deploy via GitHub (recomendado)

1. Envie o projeto para um repositório Git
2. Acesse [vercel.com/new](https://vercel.com/new)
3. Importe o repositório
4. O Vercel detecta Python automaticamente — **não altere** o diretório raiz
5. Configure as variáveis de ambiente (aba **Settings → Environment Variables**):

| Variável | Obrigatória | Descrição |
|---|---|---|
| `SECRET_KEY` | Sim | Chave secreta para sessões Flask (string longa aleatória) |
| `EMPRESA_NOME` | Não | Sobrescreve nome da empresa |
| `EMPRESA_ENDERECO` | Não | Sobrescreve endereço |
| `EMPRESA_TELEFONE` | Não | Sobrescreve telefone |

6. Clique em **Deploy**

## Deploy via CLI

```bash
npm i -g vercel
cd "D:\Recibo express"
vercel login
vercel
```

Na primeira vez, confirme as opções padrão. Para produção:

```bash
vercel --prod
```

## Configuração da empresa

No Vercel **não é possível salvar** configurações pela tela (sem disco persistente).

Opções:

1. **Editar `config_empresa.json`** no repositório e fazer redeploy
2. **Usar variáveis de ambiente** (`EMPRESA_NOME`, etc.)
3. **Logo / marca d'água:** colocar `logo_empresa.png` e `watermark_empresa.png` em `static/uploads/` no repositório

## Limites importantes

| Item | Plano Free | Plano Pro |
|---|---|---|
| Tempo máximo por requisição | 10 segundos | 60 segundos (configurado no `vercel.json`) |
| Tamanho do upload | 4,5 MB (body) | 4,5 MB |
| Disco | Efêmero (`/tmp`) | Efêmero (`/tmp`) |

PDFs grandes com muitos funcionários podem ultrapassar 10s no plano Free. Se isso ocorrer, faça upgrade para Pro ou divida o relatório.

## Diferenças em relação ao PythonAnywhere

| Recurso | PythonAnywhere | Vercel |
|---|---|---|
| Servidor sempre ligado | Sim | Não (serverless) |
| Salvar configurações pela tela | Sim | Não |
| Upload de logo persistente | Sim | Não (via Git) |
| Download de PDF | Via sessão + disco | Download direto na geração |
| Prévia → Gerar | Funciona igual | Funciona igual |

## Testar localmente (modo serverless)

```powershell
$env:SERVERLESS = "1"
$env:SECRET_KEY = "teste-local"
python app.py
```

## Solução de problemas

**Erro 500 ao enviar PDF**
- Verifique os logs em Vercel → Project → Deployments → Functions → Logs
- Confirme que `pdfplumber` instalou corretamente (primeiro deploy pode demorar)

**Timeout**
- PDF com muitas páginas/funcionários: upgrade para Pro (60s) ou reduza o relatório

**Configurações não salvam**
- Comportamento esperado no Vercel — use `config_empresa.json` ou env vars
