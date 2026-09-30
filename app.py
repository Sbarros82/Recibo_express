from flask import Flask, render_template, request, redirect, url_for, flash, send_file, send_from_directory, jsonify, session, abort
import os
import sys
import json
import base64
import zlib


def _configurar_saida_console():
    """Evita UnicodeEncodeError no Windows (cp1252) ao imprimir emojis no log."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, 'reconfigure', None)
        if reconfigure:
            try:
                reconfigure(encoding='utf-8', errors='replace')
            except Exception:
                pass


_configurar_saida_console()
import zipfile
import tempfile
from datetime import datetime
import re
import csv
from werkzeug.utils import secure_filename, safe_join

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IS_VERCEL = os.environ.get('VERCEL') == '1'
IS_SERVERLESS = IS_VERCEL or os.environ.get('SERVERLESS') == '1'

app = Flask(
    __name__,
    template_folder=os.path.join(_BASE_DIR, 'templates'),
    static_folder=os.path.join(_BASE_DIR, 'static'),
)
app.secret_key = os.environ.get('SECRET_KEY', 'recibo_express_2024')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

if IS_SERVERLESS:
    _WORK_DIR = tempfile.gettempdir()
    UPLOAD_FOLDER = os.path.join(_WORK_DIR, 'recibo_uploads')
    OUTPUT_FOLDER = os.path.join(_WORK_DIR, 'recibo_output')
else:
    UPLOAD_FOLDER = os.path.join(_BASE_DIR, 'uploads')
    OUTPUT_FOLDER = os.path.join(_BASE_DIR, 'static', 'recibos')

ALLOWED_EXTENSIONS = {'pdf', 'csv', 'xlsx', 'xls'}

for _pasta in (UPLOAD_FOLDER, OUTPUT_FOLDER):
    try:
        os.makedirs(_pasta, exist_ok=True)
    except OSError:
        pass

try:
    os.makedirs(os.path.join(_BASE_DIR, 'static', 'uploads'), exist_ok=True)
except OSError:
    pass


def _asset_path(*parts):
    return os.path.join(_BASE_DIR, *parts)


def _ler_dados_json_form(chave='dados_json'):
    raw = request.form.get(chave, '').strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _salvar_dados_sessao(chave, dados):
    """Salva lista de dados na sessão de forma compacta (cabe no cookie)."""
    raw = json.dumps(dados, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    session[chave] = base64.urlsafe_b64encode(zlib.compress(raw, 9)).decode('ascii')
    session[f'{chave}__z'] = 1


def _carregar_dados_sessao(chave):
    """Lê lista de dados da sessão (compactada ou lista legada)."""
    valor = session.get(chave)
    if not valor:
        return []
    if isinstance(valor, list):
        return valor
    if not isinstance(valor, str):
        return []
    try:
        if session.get(f'{chave}__z'):
            return json.loads(zlib.decompress(base64.urlsafe_b64decode(valor.encode('ascii'))))
        return json.loads(valor)
    except Exception:
        return []


def _obter_dados_form_ou_sessao(chave_sessao):
    dados = _ler_dados_json_form()
    if dados is not None:
        return dados
    return _carregar_dados_sessao(chave_sessao)


def _arquivo_temporario(prefixo):
    fd, path = tempfile.mkstemp(suffix='.pdf', prefix=prefixo)
    os.close(fd)
    return path


def _parsear_valor_brl(valor_str):
    valor_clean = re.sub(r'[^\d,.]', '', valor_str or '')
    if not valor_clean:
        raise ValueError('Valor vazio')
    if ',' in valor_clean:
        partes = valor_clean.split(',')
        if len(partes) == 2:
            parte_inteira = partes[0].replace('.', '')
            parte_decimal = partes[1]
            return float(f"{parte_inteira}.{parte_decimal}")
        return float(valor_clean.replace('.', '').replace(',', ''))
    return float(valor_clean.replace('.', ''))


def _montar_dados_recibo_avulso_form():
    nome = request.form.get('nome', '').strip()
    valor_str = request.form.get('valor', '').strip()
    data = request.form.get('data', '').strip()
    observacoes = request.form.get('observacoes', '').strip()
    referencia = request.form.get('referencia', '').strip()

    if not nome:
        raise ValueError('Nome do funcionário é obrigatório')
    if not valor_str:
        raise ValueError('Valor é obrigatório')

    valor_float = _parsear_valor_brl(valor_str)
    if valor_float <= 0:
        raise ValueError('Valor deve ser maior que zero')

    if not data:
        data = datetime.now().strftime('%Y-%m-%d')

    try:
        data_br = datetime.strptime(data, '%Y-%m-%d').strftime('%d/%m/%Y')
    except ValueError:
        data_br = datetime.now().strftime('%d/%m/%Y')

    try:
        valor_por_extenso = numero_para_palavras(valor_float)
    except Exception:
        valor_por_extenso = f"R$ {valor_float:,.2f}"

    return {
        'nome': nome,
        'valor': valor_float,
        'valor_formatado': f"R$ {valor_float:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'),
        'data': data,
        'data_br': data_br,
        'observacoes': observacoes or '',
        'referencia': referencia or '',
        'valor_por_extenso': valor_por_extenso,
    }

def allowed_file(filename):
    if not filename:
        return False
    
    if '.' not in filename:
        return False
    
    extension = filename.rsplit('.', 1)[1].lower()
    return extension in ALLOWED_EXTENSIONS

def _normalizar_nome_coluna_csv(nome_coluna):
    """Normaliza nome de coluna do CSV (BOM, espaços, maiúsculas)."""
    return (nome_coluna or '').strip().lstrip('\ufeff').lower()


def _coluna_csv_corresponde(nome_coluna, coluna_esperada):
    """Verifica se uma coluna do arquivo corresponde à coluna esperada."""
    col = _normalizar_nome_coluna_csv(nome_coluna)
    aliases = {
        'funcionário': ('funcionário', 'funcionario', 'nome'),
        'descrição': ('descrição', 'descricao', 'veículo', 'veiculo'),
        'valor': ('valor',),
    }
    return col in aliases.get(coluna_esperada.lower(), (coluna_esperada.lower(),))


def _converter_valor_recibo(valor):
    """Converte valor numérico ou texto (R$ 150,00) para float."""
    if valor is None:
        raise ValueError('Valor vazio')
    if isinstance(valor, (int, float)):
        return float(valor)
    valor_str = str(valor).strip()
    if not valor_str:
        raise ValueError('Valor vazio')
    return _parsear_valor_brl(valor_str)


def _identificar_tipo_recibo(descricao_ou_veiculo):
    """
    Identifica o tipo de recibo a partir da coluna Veículo.

    Regra:
    - contém "carro" → Ajuda de Custo
    - qualquer outra informação (ou vazio) → Vale transporte
    """
    texto = ''
    if descricao_ou_veiculo is not None:
        texto = str(descricao_ou_veiculo).strip()

    if texto and 'carro' in texto.lower():
        return 'ajuda_custo', 'Ajuda de Custo'

    return 'vale_transporte', 'Vale transporte'


def processar_xlsx_vale_transporte(caminho_xlsx):
    """Processa planilha Excel no modelo padrão: Nome | Veículo | Valor."""
    print(f"🔍 INICIANDO PROCESSAMENTO DO EXCEL: {caminho_xlsx}")

    if not os.path.exists(caminho_xlsx):
        print(f"❌ Arquivo não encontrado: {caminho_xlsx}")
        return []

    if os.path.getsize(caminho_xlsx) == 0:
        print("❌ Arquivo está vazio")
        return []

    try:
        from openpyxl import load_workbook
    except ImportError:
        print("❌ openpyxl não instalado")
        raise RuntimeError(
            'Suporte a Excel requer o pacote openpyxl. Execute: pip install openpyxl'
        )

    dados_finais = []

    try:
        wb = load_workbook(caminho_xlsx, data_only=True)
        ws = wb.active
        print(f"📋 Planilha ativa: {ws.title}")

        linhas = list(ws.iter_rows(values_only=True))
        if not linhas:
            print("❌ Planilha vazia")
            return []

        cabecalho = [(_normalizar_nome_coluna_csv(str(c)) if c is not None else '') for c in linhas[0]]
        print(f"📋 Cabeçalho: {cabecalho}")

        idx_nome = next(
            (i for i, c in enumerate(cabecalho) if c in ('nome', 'funcionário', 'funcionario')),
            None,
        )
        idx_veiculo = next(
            (
                i
                for i, c in enumerate(cabecalho)
                if c in ('veículo', 'veiculo', 'descrição', 'descricao')
            ),
            None,
        )
        idx_valor = next((i for i, c in enumerate(cabecalho) if c == 'valor'), None)

        if idx_nome is None or idx_valor is None:
            print(f"❌ Cabeçalho inválido. Esperado: Nome, Veículo, Valor. Encontrado: {cabecalho}")
            return []

        # Se não houver coluna Veículo, assume índice 1 (modelo padrão)
        if idx_veiculo is None:
            idx_veiculo = 1 if idx_nome == 0 else None

        print(f"📋 Índices: nome={idx_nome}, veiculo={idx_veiculo}, valor={idx_valor}")

        for i, row in enumerate(linhas[1:], start=2):
            if not row:
                continue

            nome_raw = row[idx_nome] if idx_nome < len(row) else None
            veiculo_raw = (
                row[idx_veiculo]
                if idx_veiculo is not None and idx_veiculo < len(row)
                else None
            )
            valor_raw = row[idx_valor] if idx_valor < len(row) else None

            nome = str(nome_raw).strip() if nome_raw is not None else ''
            if not nome:
                print(f"❌ Pulando linha {i}: sem nome")
                continue

            try:
                valor_float = _converter_valor_recibo(valor_raw)
            except (ValueError, TypeError) as e:
                print(f"❌ Pulando linha {i}: valor inválido '{valor_raw}': {e}")
                continue

            if valor_float <= 0:
                print(f"❌ Pulando linha {i}: valor inválido ({valor_float})")
                continue

            tipo_recibo, descricao = _identificar_tipo_recibo(veiculo_raw)

            dados_finais.append({
                'nome': nome,
                'tipo': tipo_recibo,
                'descricao': descricao,
                'valor': valor_float,
                'data': datetime.now().strftime('%d/%m/%Y'),
            })
            print(f"✅ Adicionado: {nome} - {tipo_recibo} - R$ {valor_float:,.2f}")

    except Exception as e:
        print(f"❌ Erro ao processar Excel: {e}")
        import traceback
        traceback.print_exc()
        return []

    print(f"✅ Total de registros processados (Excel): {len(dados_finais)}")
    return dados_finais


def processar_arquivo_vale_transporte(caminho_arquivo):
    """Processa CSV ou Excel (modelo padrão Combustível) para VT/Ajuda de Custo."""
    extensao = os.path.splitext(caminho_arquivo)[1].lower()
    if extensao in ('.xlsx', '.xls'):
        return processar_xlsx_vale_transporte(caminho_arquivo)
    return processar_csv_vale_transporte(caminho_arquivo)


def processar_csv_vale_transporte(caminho_csv):
    """Processa arquivo CSV com dados de vale transporte e ajuda de custo"""
    print(f"🔍 INICIANDO PROCESSAMENTO DO CSV: {caminho_csv}")
    
    # Verificar se o arquivo existe
    if not os.path.exists(caminho_csv):
        print(f"❌ Arquivo não encontrado: {caminho_csv}")
        return []
    
    # Verificar se o arquivo não está vazio
    tamanho_arquivo = os.path.getsize(caminho_csv)
    print(f"✅ Arquivo existe: {tamanho_arquivo} bytes")
    
    if tamanho_arquivo == 0:
        print("❌ Arquivo está vazio")
        return []
    
    dados_finais = []
    
    try:
        # Tentar diferentes encodings
        encodings = ['utf-8-sig', 'utf-8', 'latin-1', 'cp1252', 'iso-8859-1']
        arquivo_processado = False
        
        for encoding in encodings:
            try:
                print(f"🔍 Tentando encoding: {encoding}")
                with open(caminho_csv, 'r', encoding=encoding) as arquivo:
                    # Detectar delimitador automaticamente
                    sample = arquivo.read(1024)
                    arquivo.seek(0)
                    
                    # Remover BOM se existir
                    if sample.startswith('\ufeff'):
                        sample = sample[1:]
                    
                    print(f"📄 Primeiras linhas do arquivo ({encoding}):")
                    print(repr(sample[:200]))
                    
                    sniffer = csv.Sniffer()
                    try:
                        delimiter = sniffer.sniff(sample).delimiter
                        print(f"📊 Delimitador detectado: '{delimiter}'")
                    except:
                        # Se não conseguir detectar, tentar vírgula e ponto e vírgula
                        if ',' in sample:
                            delimiter = ','
                        elif ';' in sample:
                            delimiter = ';'
                        else:
                            delimiter = ','
                        print(f"📊 Delimitador assumido: '{delimiter}'")
                    
                    leitor = csv.DictReader(arquivo, delimiter=delimiter)
                    print(f"📋 Colunas encontradas: {leitor.fieldnames}")
                    
                    # Verificar se as colunas necessárias existem (case insensitive, com/sem acento)
                    # Modelo padrão Excel: Nome, Veículo, Valor
                    # Modelo legado CSV: Funcionário, descrição, Valor
                    colunas_necessarias = ['Funcionário', 'descrição', 'Valor']
                    fieldnames = leitor.fieldnames or []
                    colunas_encontradas = [_normalizar_nome_coluna_csv(col) for col in fieldnames]
                    
                    print(f"📋 Colunas necessárias: {colunas_necessarias}")
                    print(f"📋 Colunas encontradas: {colunas_encontradas}")
                    
                    # Verificar cada coluna individualmente
                    for col_necessaria in colunas_necessarias:
                        if any(_coluna_csv_corresponde(col, col_necessaria) for col in fieldnames):
                            print(f"✅ Coluna '{col_necessaria}' encontrada")
                        else:
                            print(f"❌ Coluna '{col_necessaria}' NÃO encontrada")
                    
                    if not all(
                        any(_coluna_csv_corresponde(col, col_necessaria) for col in fieldnames)
                        for col_necessaria in colunas_necessarias
                    ):
                        print(f"❌ Colunas necessárias não encontradas com encoding {encoding}")
                        continue
                    
                    # Mapear colunas para nomes corretos
                    mapeamento_colunas = {}
                    for col_original in fieldnames:
                        col_lower = _normalizar_nome_coluna_csv(col_original)
                        if col_lower in ('funcionário', 'funcionario', 'nome'):
                            mapeamento_colunas['Funcionário'] = col_original
                        elif col_lower in ('descrição', 'descricao', 'veículo', 'veiculo'):
                            mapeamento_colunas['descrição'] = col_original
                        elif col_lower == 'valor':
                            mapeamento_colunas['Valor'] = col_original
                    
                    print(f"📋 Mapeamento de colunas: {mapeamento_colunas}")
                    
                    if len(mapeamento_colunas) != 3:
                        print(f"❌ Não foi possível mapear todas as colunas necessárias")
                        continue
                    
                    arquivo_processado = True
                    break
                    
            except Exception as e:
                print(f"❌ Erro com encoding {encoding}: {e}")
                continue
        
        if not arquivo_processado:
            print("❌ Não foi possível processar o arquivo com nenhum encoding")
            return []
        
        # Processar o arquivo com o encoding que funcionou
        with open(caminho_csv, 'r', encoding=encoding) as arquivo:
            leitor = csv.DictReader(arquivo, delimiter=delimiter)
            
            # Verificar se o leitor tem fieldnames
            if not leitor.fieldnames:
                print("❌ Arquivo CSV não possui cabeçalho válido")
                return []
            
            # Verificar novamente o mapeamento antes de processar
            if 'Funcionário' not in mapeamento_colunas or 'descrição' not in mapeamento_colunas or 'Valor' not in mapeamento_colunas:
                print(f"❌ Mapeamento de colunas incompleto: {mapeamento_colunas}")
                return []
            
            for i, linha in enumerate(leitor):
                print(f"📄 Processando linha {i+1}: {linha}")
                
                # Extrair dados da linha usando o mapeamento
                funcionario = (linha.get(mapeamento_colunas.get('Funcionário', ''), '') or '').strip()
                descricao = (linha.get(mapeamento_colunas.get('descrição', ''), '') or '').strip()
                valor_str = (linha.get(mapeamento_colunas.get('Valor', ''), '') or '').strip()
                
                # Validações (descrição/veículo pode ficar vazia = Vale transporte)
                if not funcionario or not valor_str:
                    print(f"❌ Pulando linha {i+1}: dados incompletos")
                    continue
                
                # Converter valor
                try:
                    print(f"💰 Valor original: '{valor_str}'")
                    valor_float = _converter_valor_recibo(valor_str)
                    print(f"💰 Valor convertido: {valor_float}")
                    
                    if valor_float <= 0:
                        print(f"❌ Pulando linha {i+1}: valor inválido ({valor_float})")
                        continue
                        
                except ValueError as e:
                    print(f"❌ Pulando linha {i+1}: erro ao converter valor '{valor_str}': {e}")
                    continue
                
                tipo_recibo, descricao_final = _identificar_tipo_recibo(descricao)
                
                # Adicionar aos dados finais
                dados_finais.append({
                    'nome': funcionario,
                    'tipo': tipo_recibo,
                    'descricao': descricao_final,
                    'valor': valor_float,
                    'data': datetime.now().strftime('%d/%m/%Y')
                })
                
                print(f"✅ Adicionado: {funcionario} - {tipo_recibo} - R$ {valor_float:,.2f}")
    
    except Exception as e:
        print(f"❌ Erro ao processar CSV: {e}")
        import traceback
        traceback.print_exc()
        return []
    
    print(f"✅ Total de registros processados: {len(dados_finais)}")
    return dados_finais

def numero_para_palavras(valor):
    """Converte número para palavras em português (versão melhorada)"""
    unidades = ['', 'um', 'dois', 'três', 'quatro', 'cinco', 'seis', 'sete', 'oito', 'nove']
    dezenas = ['', '', 'vinte', 'trinta', 'quarenta', 'cinquenta', 'sessenta', 'setenta', 'oitenta', 'noventa']
    especiais = ['dez', 'onze', 'doze', 'treze', 'quatorze', 'quinze', 'dezesseis', 'dezessete', 'dezoito', 'dezenove']
    centenas = ['', 'cento', 'duzentos', 'trezentos', 'quatrocentos', 'quinhentos', 'seiscentos', 'setecentos', 'oitocentos', 'novecentos']
    
    # Separar parte inteira e decimal
    valor_str = f"{valor:.2f}"
    parte_inteira, parte_decimal = valor_str.split('.')
    
    # Converter parte inteira
    inteiro = int(parte_inteira)
    centavos = int(parte_decimal)
    
    def converter_centenas(num):
        if num == 0:
            return ""
        elif num < 10:
            return unidades[num]
        elif num < 20:
            return especiais[num - 10]
        elif num < 100:
            dezena = num // 10
            unidade = num % 10
            if unidade == 0:
                return dezenas[dezena]
            else:
                return f"{dezenas[dezena]} e {unidades[unidade]}"
        elif num < 1000:
            centena = num // 100
            resto = num % 100
            if resto == 0:
                return centenas[centena]
            elif centena == 1 and resto > 0:
                return f"cento e {converter_centenas(resto)}"
            else:
                return f"{centenas[centena]} e {converter_centenas(resto)}"
        else:
            # Para valores maiores que 1000
            milhares = num // 1000
            resto = num % 1000
            if resto == 0:
                if milhares == 1:
                    return "mil"
                else:
                    return f"{converter_centenas(milhares)} mil"
            else:
                if milhares == 1:
                    return f"mil e {converter_centenas(resto)}"
                else:
                    return f"{converter_centenas(milhares)} mil e {converter_centenas(resto)}"
    
    resultado = converter_centenas(inteiro)
    
    # Adicionar centavos
    if centavos > 0:
        centavos_texto = converter_centenas(centavos)
        resultado += f" reais e {centavos_texto} centavos"
    else:
        resultado += " reais"
    
    # Capitalizar primeira letra
    resultado = resultado.capitalize()
    
    return resultado

def extrair_dados_pdf(caminho_pdf):
    """Extrai dados do PDF do relatório tabular e soma comissão + premiação"""
    print(f"🔍 INICIANDO EXTRAÇÃO DE DADOS DO PDF: {caminho_pdf}")
    
    # Verificar se o arquivo existe
    if not os.path.exists(caminho_pdf):
        print(f"❌ Arquivo não encontrado: {caminho_pdf}")
        return []
    
    print(f"✅ Arquivo existe: {os.path.getsize(caminho_pdf)} bytes")
    
    dados_brutos = {}
    
    try:
        import pdfplumber
        print("🔍 Abrindo PDF com pdfplumber...")
        with pdfplumber.open(caminho_pdf) as pdf:
            print(f"✅ PDF aberto com sucesso. Páginas: {len(pdf.pages)}")
            
            for i, page in enumerate(pdf.pages):
                print(f"📄 Processando página {i+1}...")
                
                # Primeiro, tentar extrair como tabela
                print("🔍 Tentando extrair tabelas...")
                tables = page.extract_tables()
                if tables:
                    print(f"✅ Encontradas {len(tables)} tabelas na página {i+1}")
                    
                    for table_idx, table in enumerate(tables):
                        print(f"📊 Processando tabela {table_idx + 1}...")
                        
                        for row_idx, row in enumerate(table):
                            if not row or len(row) < 3:
                                continue
                                
                            # Verificar se é uma linha de dados válida
                            # Procurar por colunas: Classificação, Nome, Comissão, Origem
                            classificacao = row[0].strip() if len(row) > 0 and row[0] else ""
                            nome = row[3].strip() if len(row) > 3 and row[3] else ""  # Nome Pessoa
                            comissao_str = row[10].strip() if len(row) > 10 and row[10] else ""  # Comissão
                            origem = row[11].strip() if len(row) > 11 and row[11] else ""  # Origem
                            
                            print(f"Linha {row_idx}: Classificação='{classificacao}', Nome='{nome}', Comissão='{comissao_str}', Origem='{origem}'")
                            
                            # FILTRO RIGOROSO: Pular linhas vazias, cabeçalhos ou subtotais
                            if not nome or not nome.strip() or not comissao_str or not comissao_str.strip():
                                print(f"❌ Pulando linha sem nome ou comissão: Nome='{nome}', Comissão='{comissao_str}'")
                                continue
                            
                            if nome.upper() in ['NOME PESSOA', 'TOTAL', 'SUBTOTAL', 'CLASSIFICAÇÃO']:
                                print(f"❌ Pulando cabeçalho: {nome}")
                                continue
                            
                            # FILTRO CRÍTICO: Pular se o nome estiver vazio (linhas de totais)
                            if not nome.strip():
                                print(f"❌ Pulando linha com nome vazio (total): {row}")
                                continue
                            
                            # Pular se o nome estiver vazio ou contiver apenas espaços
                            if not nome.strip():
                                print(f"Pulando linha com nome vazio: {row}")
                                continue
                            
                            # FILTRO RIGOROSO: Pular valores gigantescos (totais)
                            try:
                                comissao_clean = re.sub(r'[^\d,.]', '', comissao_str)
                                if comissao_clean:
                                    if ',' in comissao_clean:
                                        partes = comissao_clean.split(',')
                                        if len(partes) == 2:
                                            parte_inteira = partes[0].replace('.', '')
                                            parte_decimal = partes[1]
                                            valor_str = f"{parte_inteira}.{parte_decimal}"
                                        else:
                                            valor_str = comissao_clean.replace('.', '').replace(',', '')
                                    else:
                                        valor_str = comissao_clean.replace('.', '')
                                    
                                    valor_teste = float(valor_str)
                                    # Se o valor for muito alto (provavelmente um total), pular
                                    if valor_teste > 100000:  # Mais de 100 mil (mais rigoroso)
                                        print(f"❌ Pulando valor muito alto (total): {comissao_str} -> {valor_teste}")
                                        continue
                            except:
                                pass
                                
                            # Pular registros que começam com ZZZ_
                            if nome.upper().startswith('ZZZ_'):
                                print(f"❌ Pulando registro ZZZ_: {nome}")
                                continue
                            
                            # Pular linhas que são claramente totais (sem nome mas com valor alto)
                            if not nome.strip() and comissao_str:
                                try:
                                    comissao_clean = re.sub(r'[^\d,.]', '', comissao_str)
                                    if comissao_clean:
                                        if ',' in comissao_clean:
                                            partes = comissao_clean.split(',')
                                            if len(partes) == 2:
                                                parte_inteira = partes[0].replace('.', '')
                                                parte_decimal = partes[1]
                                                valor_str = f"{parte_inteira}.{parte_decimal}"
                                            else:
                                                valor_str = comissao_clean.replace('.', '').replace(',', '')
                                        else:
                                            valor_str = comissao_clean.replace('.', '')
                                        
                                        valor_teste = float(valor_str)
                                        if valor_teste > 1000000:  # Mais de 1 milhão
                                            print(f"Pulando linha sem nome com valor alto (total): {comissao_str}")
                                            continue
                                except:
                                    pass
                            
                            # Pular linhas que são totais (apenas números, sem nome)
                            if not nome.strip() and classificacao.strip() and comissao_str:
                                # Verificar se a linha contém apenas números (total)
                                if re.match(r'^[\d\s,\.]+$', classificacao.strip()):
                                    print(f"Pulando linha de total: {row}")
                                    continue
                            
                            # FILTRO ESPECÍFICO: Pular totais conhecidos do relatório
                            total_patterns = [
                                '15.679.084,43',  # Total Emissores
                                '7.800.984,23',   # Total Executivos
                                '7.666.176,86',   # Total Gerente
                                '906,03',         # Total Serviços Gerais
                                '5.224.974,07',   # Total Supervisores
                                '44.038.302,48',  # Total Geral
                                '88.076.604,96'   # Total problemático
                            ]
                            
                            for pattern in total_patterns:
                                if pattern in comissao_str:
                                    print(f"❌ Pulando linha de total conhecido: {comissao_str}")
                                    continue
                            
                            # FILTRO ADICIONAL: Pular linhas que são apenas números (totais)
                            if re.match(r'^[\d\s,\.]+$', comissao_str.strip()):
                                print(f"❌ Pulando linha apenas com números (total): {comissao_str}")
                                continue
                            
                            # Tentar extrair valor da comissão
                            try:
                                # Limpar string de comissão (remover R$, espaços, etc.)
                                comissao_clean = re.sub(r'[^\d,.]', '', comissao_str)
                                if comissao_clean:
                                    print(f"Valor original: '{comissao_str}' -> Limpo: '{comissao_clean}'")
                                    
                                    # Converter formato brasileiro para float
                                    # Se tem vírgula, é formato brasileiro (1.234,56)
                                    if ',' in comissao_clean:
                                        # Separar parte inteira e decimal
                                        partes = comissao_clean.split(',')
                                        if len(partes) == 2:
                                            # Parte inteira: remover pontos (separadores de milhares)
                                            parte_inteira = partes[0].replace('.', '')
                                            # Parte decimal: usar como está
                                            parte_decimal = partes[1]
                                            valor_str = f"{parte_inteira}.{parte_decimal}"
                                        else:
                                            # Se tem vírgula mas não é formato decimal, tratar como inteiro
                                            valor_str = comissao_clean.replace('.', '').replace(',', '')
                                    else:
                                        # Se não tem vírgula, tratar como inteiro
                                        valor_str = comissao_clean.replace('.', '')
                                    
                                    valor = float(valor_str)
                                    print(f"Valor convertido: {valor}")
                                    
                                    if valor > 0:
                                        # Mapear classificação para setor
                                        setor_map = {
                                            'Emissor': 'Emissores',
                                            'Executivo de Contas': 'Executivos',
                                            'Diretor Comercial': 'Diretor',
                                            'Gerente Operacional': 'Gerente',
                                            'Supervisores': 'Supervisores',
                                            'Servicos Gerais': 'Serviços Gerais'
                                        }
                                        
                                        setor = setor_map.get(classificacao, 'Emissores')
                                        
                                        # CORREÇÃO ESPECÍFICA: ANA CAROLINA NERY FEITOSA é Diretora Comercial
                                        if 'ANA CAROLINA' in nome.upper() and 'FEITOSA' in nome.upper():
                                            setor = 'Diretor'
                                            print(f"CORRECAO: ANA CAROLINA detectada e forcada para setor 'Diretor'")
                                            print(f"Nome original: '{nome}'")
                                            print(f"Setor antes: '{setor_map.get(classificacao, 'Emissores')}'")
                                            print(f"Setor depois: '{setor}'")
                                        
                                        # Log da classificação e setor
                                        print(f"Classificação: '{classificacao}' -> Setor: '{setor}'")
                                        
                                        # Log específico para ANA CAROLINA
                                        if 'ANA CAROLINA' in nome.upper():
                                            print(f"🔍 ANA CAROLINA detectada: Nome='{nome}', Classificação='{classificacao}', Setor='{setor}'")
                                        
                                        # Validar se o nome não está vazio
                                        if not nome or nome.strip() == "":
                                            print(f"Pulando linha com nome vazio: {row}")
                                            continue
                                        
                                        # Chave única para cada funcionário
                                        chave_funcionario = f"{nome}_{setor}"
                                        
                                        if chave_funcionario not in dados_brutos:
                                            dados_brutos[chave_funcionario] = {
                                                'nome': nome.strip(),
                                                'setor': setor,
                                                'comissao': 0.0,
                                                'premiacao': 0.0,
                                                'total': 0.0,
                                                'data': datetime.now().strftime('%d/%m/%Y')
                                            }
                                        
                                        # Somar valores baseado na origem
                                        if origem.upper() == 'COMISSÃO' or origem.upper() == 'COMISSAO':
                                            dados_brutos[chave_funcionario]['comissao'] += valor
                                        elif origem.upper() == 'PREMIACAO':
                                            dados_brutos[chave_funcionario]['premiacao'] += valor
                                        else:
                                            # Se não especificado, assumir comissão
                                            dados_brutos[chave_funcionario]['comissao'] += valor
                                        
                                        print(f"✅ Adicionado: {nome.strip()} - {origem}: R$ {valor:,.2f}")
                                        
                                        print(f"Registro: Nome={nome}, Origem={origem}, Valor={valor}")
                                        
                            except (ValueError, IndexError) as e:
                                print(f"Erro ao processar linha {row_idx}: {e}")
                                continue
                
                # Se não encontrou tabelas, tentar extração por texto
                else:
                    print(f"Nenhuma tabela encontrada na página {i+1}, tentando extração por texto...")
                    text = page.extract_text()
                    
                    if text:
                        print(f"Texto extraído da página {i+1}:")
                        print("=" * 50)
                        print(text[:500] + "..." if len(text) > 500 else text)
                        print("=" * 50)
                        
                        # Processar texto para extrair informações dos funcionários
                        linhas = text.split('\n')
                        print(f"Total de linhas encontradas: {len(linhas)}")
                        
                        for j, linha in enumerate(linhas):
                            linha = linha.strip()
                            if not linha or linha.upper().startswith('ZZZ_'):
                                if linha.upper().startswith('ZZZ_'):
                                    print(f"❌ Pulando linha ZZZ_: {linha}")
                                continue
                                
                            print(f"Linha {j+1}: {linha}")
                            
                            # Procurar especificamente por COMISSÃO/COMISSAO ou PREMIACAO no final da linha
                            if 'COMISSÃO' in linha.upper() or 'COMISSAO' in linha.upper() or 'PREMIACAO' in linha.upper():
                                print(f"Processando linha com COMISSAO/PREMIACAO: {linha}")
                                # Padrão correto: buscar o valor da comissão/premiação na linha
                                # Exemplo: "... 0,50 3.140,00 COMISSAO" - pegar o 3.140,00
                                valor_patterns = [
                                    r'(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)\s+(COMISSÃO|COMISSAO|PREMIACAO)\s*$',  # 1.234,56 COMISSAO
                                    r'(\d+(?:,\d{2})?)\s+(COMISSÃO|COMISSAO|PREMIACAO)\s*$'                    # 1234,56 COMISSAO
                                ]
                            else:
                                # Se não tem COMISSÃO/PREMIACAO, pular esta linha
                                print(f"Pulando linha sem COMISSAO/PREMIACAO: {linha}")
                                continue
                            
                            valor_encontrado = None
                            origem_encontrada = None
                            
                            for pattern in valor_patterns:
                                match = re.search(pattern, linha)
                                if match:
                                    valor_str = match.group(1)
                                    origem_encontrada = match.group(2)
                                    
                                    try:
                                        print(f"Valor encontrado no texto: '{valor_str}'")
                                        print(f"Origem encontrada: '{origem_encontrada}'")
                                        print(f"Linha completa: {linha}")
                                        
                                        # Converter formato brasileiro para float
                                        if ',' in valor_str:
                                            # Separar parte inteira e decimal
                                            partes = valor_str.split(',')
                                            if len(partes) == 2:
                                                # Parte inteira: remover pontos (separadores de milhares)
                                                parte_inteira = partes[0].replace('.', '')
                                                # Parte decimal: usar como está
                                                parte_decimal = partes[1]
                                                valor_str_clean = f"{parte_inteira}.{parte_decimal}"
                                            else:
                                                # Se tem vírgula mas não é formato decimal, tratar como inteiro
                                                valor_str_clean = valor_str.replace('.', '').replace(',', '')
                                        else:
                                            # Se não tem vírgula, tratar como inteiro
                                            valor_str_clean = valor_str.replace('.', '')
                                        
                                        valor = float(valor_str_clean)
                                        print(f"Valor convertido do texto: {valor}")
                                        
                                        if valor > 0:  # Só aceitar valores positivos
                                            valor_encontrado = valor
                                            break
                                    except ValueError as e:
                                        print(f"Erro ao converter valor '{valor_str}': {e}")
                                        continue
                            
                            if not valor_encontrado:
                                print(f"❌ Nenhum valor encontrado na linha: {linha}")
                                continue
                            
                            if valor_encontrado:
                                print(f"Valor encontrado: {valor_encontrado}")
                                
                                # Tentar extrair nome e setor
                                linha_sem_valor = re.sub(r'R\$\s*\d{1,3}(?:\.\d{3})*(?:,\d{2})?', '', linha)
                                linha_sem_valor = re.sub(r'\d{1,3}(?:\.\d{3})*(?:,\d{2})?', '', linha_sem_valor)
                                linha_sem_valor = linha_sem_valor.strip()
                                
                                # Dividir em partes
                                partes = linha_sem_valor.split()
                                
                                if len(partes) >= 2:
                                    # Determinar setor baseado na linha original
                                    if 'Emissor' in linha:
                                        setor = 'Emissores'
                                    elif 'Executivo' in linha:
                                        setor = 'Executivos'
                                    elif 'Supervisores' in linha:
                                        setor = 'Supervisores'
                                    elif 'Diretor' in linha:
                                        setor = 'Diretor'
                                    elif 'Gerente' in linha:
                                        setor = 'Gerente'
                                    elif 'Servicos Gerais' in linha:
                                        setor = 'Serviços Gerais'
                                    else:
                                        setor = 'Emissores'  # Default
                                    
                                    # Extrair nome (remover classificação e unidade)
                                    nome = linha
                                    # Remover classificação do início
                                    if 'Emissor' in nome:
                                        nome = nome.replace('Emissor', '').strip()
                                    elif 'Executivo' in nome:
                                        nome = nome.replace('Executivo de Contas', '').strip()
                                    elif 'Supervisores' in nome:
                                        nome = nome.replace('Supervisores', '').strip()
                                    elif 'Diretor' in nome:
                                        nome = nome.replace('Diretor Comercial', '').strip()
                                    elif 'Gerente' in nome:
                                        nome = nome.replace('Gerente Operacional', '').strip()
                                    elif 'Servicos Gerais' in nome:
                                        nome = nome.replace('Servicos Gerais', '').strip()
                                    
                                    # Remover unidade (MASTEROP, etc.)
                                    nome = re.sub(r'MASTEROP\s+\w+\s+\d+\.\d+', '', nome).strip()
                                    nome = re.sub(r'MASTEROP\s+\w+', '', nome).strip()
                                    
                                    # Remover valores monetários
                                    nome = re.sub(r'\d{1,3}(?:\.\d{3})*(?:,\d{2})?', '', nome).strip()
                                    
                                    # Remover origem (COMISSÃO/PREMIACAO)
                                    nome = re.sub(r'(COMISSÃO|PREMIACAO)$', '', nome).strip()
                                    
                                    # Limpar espaços extras
                                    nome = ' '.join(nome.split())
                                    
                                    # Adicionar aos dados brutos (mesmo formato da extração por tabela)
                                    chave_funcionario = f"{nome}_{setor}"
                                    
                                    if chave_funcionario not in dados_brutos:
                                        dados_brutos[chave_funcionario] = {
                                            'nome': nome,
                                            'setor': setor,
                                            'comissao': 0.0,
                                            'premiacao': 0.0,
                                            'total': 0.0,
                                            'data': datetime.now().strftime('%d/%m/%Y')
                                        }
                                    
                                        # Usar a origem encontrada
                                        if origem_encontrada and origem_encontrada.upper() in ['COMISSÃO', 'COMISSAO']:
                                            dados_brutos[chave_funcionario]['comissao'] += valor_encontrado
                                            print(f"Adicionado COMISSAO: {nome} - R$ {valor_encontrado:,.2f}")
                                            print(f"Total atual: Comissao={dados_brutos[chave_funcionario]['comissao']:,.2f}, Premiacao={dados_brutos[chave_funcionario]['premiacao']:,.2f}")
                                        elif origem_encontrada and origem_encontrada.upper() == 'PREMIACAO':
                                            dados_brutos[chave_funcionario]['premiacao'] += valor_encontrado
                                            print(f"Adicionado PREMIACAO: {nome} - R$ {valor_encontrado:,.2f}")
                                            print(f"Total atual: Comissao={dados_brutos[chave_funcionario]['comissao']:,.2f}, Premiacao={dados_brutos[chave_funcionario]['premiacao']:,.2f}")
                                        else:
                                            # Se não conseguiu identificar origem, assumir comissão
                                            dados_brutos[chave_funcionario]['comissao'] += valor_encontrado
                                            print(f"Adicionado (assumido COMISSAO): {nome} - R$ {valor_encontrado:,.2f}")
                                            print(f"Total atual: Comissao={dados_brutos[chave_funcionario]['comissao']:,.2f}, Premiacao={dados_brutos[chave_funcionario]['premiacao']:,.2f}")
                                    
                                    print(f"Dados extraídos: Nome={nome}, Setor={setor}, Valor={valor_encontrado}")
                                else:
                                    # Se não conseguiu dividir bem, usar a linha inteira como nome
                                    chave_funcionario = f"{linha_sem_valor}_Emissores"
                                    
                                    if chave_funcionario not in dados_brutos:
                                        dados_brutos[chave_funcionario] = {
                                            'nome': linha_sem_valor,
                                            'setor': 'Emissores',
                                            'comissao': 0.0,
                                            'premiacao': 0.0,
                                            'total': 0.0,
                                            'data': datetime.now().strftime('%d/%m/%Y')
                                        }
                                    
                                        # Usar a origem encontrada
                                        if origem_encontrada and origem_encontrada.upper() in ['COMISSÃO', 'COMISSAO']:
                                            dados_brutos[chave_funcionario]['comissao'] += valor_encontrado
                                            print(f"Adicionado COMISSAO (simples): {linha_sem_valor} - R$ {valor_encontrado:,.2f}")
                                        elif origem_encontrada and origem_encontrada.upper() == 'PREMIACAO':
                                            dados_brutos[chave_funcionario]['premiacao'] += valor_encontrado
                                            print(f"Adicionado PREMIACAO (simples): {linha_sem_valor} - R$ {valor_encontrado:,.2f}")
                                        else:
                                            # Se não conseguiu identificar origem, assumir comissão
                                            dados_brutos[chave_funcionario]['comissao'] += valor_encontrado
                                            print(f"Adicionado (assumido COMISSAO simples): {linha_sem_valor} - R$ {valor_encontrado:,.2f}")
                                    
                                    print(f"Dados extraídos (simples): Nome={linha_sem_valor}, Valor={valor_encontrado}")
    
    except Exception as e:
        print(f"Erro ao processar PDF: {e}")
        import traceback
        traceback.print_exc()
    
    # Processar dados brutos e calcular totais
    dados_finais = []
    
    # Ordem dos setores para organização
    ordem_setores = [
        'Emissores',
        'Executivos', 
        'Supervisores',
        'Diretor',
        'Gerente',
        'Serviços Gerais'
    ]
    
    # Debug: mostrar dados brutos
    print(f"Total de funcionarios em dados_brutos: {len(dados_brutos)}")
    for chave, dados in dados_brutos.items():
        print(f"  - {chave}: {dados}")
    
    # Limpar e unificar funcionários duplicados
    funcionarios_unificados = {}
    
    for chave, dados in dados_brutos.items():
        # Limpar nome do funcionário (remover códigos como T.RIZ, A, C, etc.)
        nome_limpo = dados['nome']
        
        # Pular registros que começam com ZZZ_
        if nome_limpo.upper().startswith('ZZZ_'):
            print(f"❌ Pulando funcionário ZZZ_: {nome_limpo}")
            continue
        
        # Remover códigos comuns do início do nome
        codigos_remover = ['T.RIZ ', 'A ', 'C ', 'R ', 'T. ', 'T ', 'TR.IZ ', 'ADMINISTRAÇ ÃO. ']
        for codigo in codigos_remover:
            if nome_limpo.startswith(codigo):
                nome_limpo = nome_limpo[len(codigo):]
                break
        
        # Remover "COMISSAO" do final do nome se existir
        if nome_limpo.endswith(' COMISSAO'):
            nome_limpo = nome_limpo[:-9]
        
        # Usar nome limpo como chave
        if nome_limpo not in funcionarios_unificados:
            # CORREÇÃO ESPECÍFICA: ANA CAROLINA NERY FEITOSA é Diretora Comercial
            setor_correto = dados['setor']
            if 'ANA CAROLINA' in nome_limpo.upper() and 'FEITOSA' in nome_limpo.upper():
                setor_correto = 'Diretor'
                print(f"CORRECAO UNIFICACAO: ANA CAROLINA detectada e forcada para setor 'Diretor'")
                print(f"Nome limpo: '{nome_limpo}'")
                print(f"Setor original: '{dados['setor']}'")
                print(f"Setor corrigido: '{setor_correto}'")
            
            funcionarios_unificados[nome_limpo] = {
                'nome': nome_limpo,
                'setor': setor_correto,
                'comissao': 0.0,
                'premiacao': 0.0,
                'total': 0.0,
                'data': dados['data']
            }
        
        # Somar valores
        funcionarios_unificados[nome_limpo]['comissao'] += dados['comissao']
        funcionarios_unificados[nome_limpo]['premiacao'] += dados['premiacao']
        funcionarios_unificados[nome_limpo]['total'] = funcionarios_unificados[nome_limpo]['comissao'] + funcionarios_unificados[nome_limpo]['premiacao']
    
    # Organizar dados finais por setor
    for setor in ordem_setores:
        funcionarios_setor = [dados for dados in funcionarios_unificados.values() if dados['setor'] == setor]
        for funcionario in funcionarios_setor:
            dados_finais.append({
                'nome': funcionario['nome'],
                'setor': funcionario['setor'],
                'comissao': funcionario['comissao'],
                'premiacao': funcionario['premiacao'],
                'valor': funcionario['total'],  # Valor total para o recibo
                'data': funcionario['data']
            })
            
            print(f"Funcionário: {funcionario['nome']}")
            print(f"  Setor: {funcionario['setor']}")
            print(f"  Comissão: R$ {funcionario['comissao']:,.2f}")
            print(f"  Premiação: R$ {funcionario['premiacao']:,.2f}")
            print(f"  Total: R$ {funcionario.get('total', 0):,.2f}")
            print("-" * 40)
    
    print(f"Total de funcionários processados: {len(dados_finais)}")
    
    # Debug: mostrar alguns dados extraídos
    if dados_finais:
        print("✅ DADOS EXTRAÍDOS COM SUCESSO:")
        for i, func in enumerate(dados_finais[:3]):  # Mostrar apenas os 3 primeiros
            valor_total = func.get('valor', func.get('total', 0))
            print(f"  {i+1}. {func.get('nome', 'N/A')} - {func.get('setor', 'N/A')} - R$ {valor_total:,.2f}")
        if len(dados_finais) > 3:
            print(f"  ... e mais {len(dados_finais) - 3} funcionários")
    else:
        print("❌ NENHUM DADO EXTRAÍDO - Verificando logs acima...")
    
    return dados_finais

def gerar_recibo(nome, setor, valor, data, output_path):
    """Gera um recibo individual em PDF no formato tradicional brasileiro com layout personalizado"""
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.lib.utils import ImageReader
    from datetime import datetime, timedelta
    import os
    
    # Carregar configurações da empresa
    config = carregar_config_empresa()
    
    # Criar PDF
    c = canvas.Canvas(output_path, pagesize=A4)
    width, height = A4
    
    # Limpar nome do colaborador
    nome_limpo = nome
    
    # Pular registros que começam com ZZZ_
    if nome_limpo.upper().startswith('ZZZ_'):
        print(f"❌ Pulando funcionário ZZZ_: {nome_limpo}")
        return  # Não gerar recibo para ZZZ_
    
    codigos_remover = ['T.RIZ ', 'A ', 'C ', 'R ', 'T. ', 'T ', 'TR.IZ ', 'ADMINISTRAÇ ÃO. ']
    for codigo in codigos_remover:
        if nome_limpo.startswith(codigo):
            nome_limpo = nome_limpo[len(codigo):]
            break
    
    if nome_limpo.endswith(' COMISSAO'):
        nome_limpo = nome_limpo[:-9]
    
    # Calcular mês de referência (mês anterior)
    hoje = datetime.now()
    mes_anterior = hoje - timedelta(days=30)  # Aproximação para mês anterior
    
    # Mapear números para nomes dos meses
    meses = {
        1: 'JANEIRO', 2: 'FEVEREIRO', 3: 'MARÇO', 4: 'ABRIL',
        5: 'MAIO', 6: 'JUNHO', 7: 'JULHO', 8: 'AGOSTO',
        9: 'SETEMBRO', 10: 'OUTUBRO', 11: 'NOVEMBRO', 12: 'DEZEMBRO'
    }
    
    mes_referencia = meses[mes_anterior.month]
    ano_referencia = mes_anterior.year
    
    # Data atual para o recibo
    data_atual = hoje.strftime("%d/%m/%Y")
    
    # Formatar valor
    valor_formatado = f"R$ {valor:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    
    # Adicionar imagem de fundo se existir
    watermark_path = _asset_path('static', 'uploads', 'watermark_empresa.png')
    if os.path.exists(watermark_path):
        try:
            c.drawImage(watermark_path, 0, 0, width=width, height=height, mask='auto')
        except:
            pass  # Se houver erro, continua sem a imagem de fundo
    
    # Cabeçalho com logo da empresa
    c.setFillColor(colors.black)
    c.rect(50, 750, 500, 60, fill=1, stroke=0)
    
    # Logo da empresa (imagem ou texto)
    logo_path = _asset_path('static', 'uploads', 'logo_empresa.png')
    if os.path.exists(logo_path):
        try:
            c.drawImage(logo_path, 70, 760, width=100, height=40, mask='auto')
        except:
            # Se houver erro, usa texto
            c.setFillColor(colors.white)
            c.setFont("Helvetica-Bold", 28)
            c.drawString(70, 770, config['nome_empresa'])
    else:
        # Logo em texto
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 28)
        c.drawString(70, 770, config['nome_empresa'])
    
    c.setFont("Helvetica", 12)
    c.drawString(70, 755, "OPERADORA TURÍSTICA")
    
    # Valor destacado no canto superior direito
    c.setFillColor(colors.black)
    c.rect(400, 750, 150, 60, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(420, 770, valor_formatado)
    
    # Linha separadora
    c.setStrokeColor(colors.black)
    c.setLineWidth(2)
    c.line(50, 720, 550, 720)
    
    # Título do recibo
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 24)
    c.drawString(50, 680, "RECIBO")
    
    # Linha separadora fina
    c.setStrokeColor(colors.black)
    c.setLineWidth(1)
    c.line(50, 660, 550, 660)
    
    # Conteúdo do recibo
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 14)
    y_pos = 630
    
    c.drawString(50, y_pos, "Recebi de MASTEROP")
    y_pos -= 35
    
    valor_por_extenso = numero_para_palavras(valor)
    # Quebrar texto longo em múltiplas linhas se necessário
    texto_valor = f"a quantia de {valor_por_extenso}"
    if len(texto_valor) > 80:  # Se o texto for muito longo
        # Dividir em palavras e quebrar em linhas
        palavras = texto_valor.split()
        linha_atual = ""
        for palavra in palavras:
            if len(linha_atual + " " + palavra) <= 80:
                if linha_atual:
                    linha_atual += " " + palavra
                else:
                    linha_atual = palavra
            else:
                if linha_atual:
                    c.drawString(50, y_pos, linha_atual)
                    y_pos -= 25
                linha_atual = palavra
        # Desenhar a última linha
        if linha_atual:
            c.drawString(50, y_pos, linha_atual)
            y_pos -= 25
    else:
        c.drawString(50, y_pos, texto_valor)
        y_pos -= 35
    
    c.drawString(50, y_pos, f"referente PAGAMENTO DE COMISSÃO DO MÊS DE {mes_referencia} DE {ano_referencia}")
    y_pos -= 40
    
    # Descriminação dos valores (assumindo que é apenas comissão para recibos antigos)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y_pos, "Descriminação dos Valores:")
    y_pos -= 25
    
    c.setFont("Helvetica", 12)
    c.drawString(70, y_pos, f"Comissão: {valor_formatado}")
    y_pos -= 20
    
    y_pos -= 20
    
    # Linha separadora
    c.setStrokeColor(colors.black)
    c.setLineWidth(2)
    c.line(50, y_pos, 550, y_pos)
    y_pos -= 40
    
    # Quitação
    c.setFont("Helvetica", 12)
    c.drawString(50, y_pos, "Sendo verdade, dou plena e rasa quitação")
    y_pos -= 30
    
    # Local e data
    c.drawString(50, y_pos, "MACEIÓ-AL")
    y_pos -= 20
    c.drawString(50, y_pos, data_atual)
    y_pos -= 50
    
    # Assinatura
    c.setStrokeColor(colors.black)
    c.setLineWidth(1)
    c.line(50, y_pos, 350, y_pos)
    y_pos -= 25
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y_pos, nome_limpo)
    
    # Rodapé com informações da empresa
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 8)
    c.drawString(50, 50, f"{config['nome_empresa']} - Operadora Turística")
    c.drawString(50, 40, config['endereco'])
    if config['telefone']:
        c.drawString(50, 30, f"Tel: {config['telefone']}")
    if config['email']:
        c.drawString(50, 20, f"Email: {config['email']}")
    
    # Salvar PDF
    c.save()

def gerar_pdf_unico(dados, output_path):
    """Gera um único PDF com todos os recibos em páginas separadas com descriminação de valores"""
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.lib.utils import ImageReader
    from datetime import datetime, timedelta
    import os
    
    # Carregar configurações da empresa
    config = carregar_config_empresa()
    
    # Criar PDF
    c = canvas.Canvas(output_path, pagesize=A4)
    width, height = A4
    
    # Calcular mês de referência (mês anterior)
    hoje = datetime.now()
    mes_anterior = hoje - timedelta(days=30)  # Aproximação para mês anterior
    
    # Mapear números para nomes dos meses
    meses = {
        1: 'JANEIRO', 2: 'FEVEREIRO', 3: 'MARÇO', 4: 'ABRIL',
        5: 'MAIO', 6: 'JUNHO', 7: 'JULHO', 8: 'AGOSTO',
        9: 'SETEMBRO', 10: 'OUTUBRO', 11: 'NOVEMBRO', 12: 'DEZEMBRO'
    }
    
    mes_referencia = meses[mes_anterior.month]
    ano_referencia = mes_anterior.year
    data_atual = hoje.strftime("%d/%m/%Y")
    
    # Gerar uma página para cada funcionário
    for i, funcionario in enumerate(dados):
        # Limpar nome do colaborador
        nome_limpo = funcionario['nome']
        
        # Pular registros que começam com ZZZ_
        if nome_limpo.upper().startswith('ZZZ_'):
            print(f"❌ Pulando funcionário ZZZ_: {nome_limpo}")
            continue
        
        codigos_remover = ['T.RIZ ', 'A ', 'C ', 'R ', 'T. ', 'T ', 'TR.IZ ', 'ADMINISTRAÇ ÃO. ']
        for codigo in codigos_remover:
            if nome_limpo.startswith(codigo):
                nome_limpo = nome_limpo[len(codigo):]
                break
        
        if nome_limpo.endswith(' COMISSAO'):
            nome_limpo = nome_limpo[:-9]
        
        # Obter valores separados
        comissao = funcionario.get('comissao', 0)
        premiacao = funcionario.get('premiacao', 0)
        valor_total = funcionario['valor']
        
        # Formatar valores
        valor_formatado = f"R$ {valor_total:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
        comissao_formatada = f"R$ {comissao:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
        premiacao_formatada = f"R$ {premiacao:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
        
        # Adicionar imagem de fundo se existir
        watermark_path = _asset_path('static', 'uploads', 'watermark_empresa.png')
        if os.path.exists(watermark_path):
            try:
                c.drawImage(watermark_path, 0, 0, width=width, height=height, mask='auto')
            except:
                pass  # Se houver erro, continua sem a imagem de fundo
        
        # Cabeçalho com logo da empresa
        c.setFillColor(colors.black)
        c.rect(50, 750, 500, 60, fill=1, stroke=0)
        
        # Logo da empresa (imagem ou texto)
        logo_path = _asset_path('static', 'uploads', 'logo_empresa.png')
        if os.path.exists(logo_path):
            try:
                c.drawImage(logo_path, 70, 760, width=100, height=40, mask='auto')
            except:
                # Se houver erro, usa texto
                c.setFillColor(colors.white)
                c.setFont("Helvetica-Bold", 28)
                c.drawString(70, 770, config['nome_empresa'])
        else:
            # Logo em texto
            c.setFillColor(colors.white)
            c.setFont("Helvetica-Bold", 28)
            c.drawString(70, 770, config['nome_empresa'])
        
        c.setFont("Helvetica", 12)
        c.drawString(70, 755, "OPERADORA TURÍSTICA")
        
        # Valor destacado no canto superior direito
        c.setFillColor(colors.black)
        c.rect(400, 750, 150, 60, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 20)
        c.drawString(420, 770, valor_formatado)
        
        # Linha separadora
        c.setStrokeColor(colors.black)
        c.setLineWidth(2)
        c.line(50, 720, 550, 720)
        
        # Título do recibo
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 24)
        c.drawString(50, 680, "RECIBO")
        
        # Linha separadora fina
        c.setStrokeColor(colors.black)
        c.setLineWidth(1)
        c.line(50, 660, 550, 660)
        
        # Conteúdo do recibo
        c.setFillColor(colors.black)
        c.setFont("Helvetica", 14)
        y_pos = 630
        
        c.drawString(50, y_pos, "Recebi de MASTEROP")
        y_pos -= 35
        
        valor_por_extenso = numero_para_palavras(valor_total)
        # Quebrar texto longo em múltiplas linhas se necessário
        texto_valor = f"a quantia de {valor_por_extenso}"
        if len(texto_valor) > 80:  # Se o texto for muito longo
            # Dividir em palavras e quebrar em linhas
            palavras = texto_valor.split()
            linha_atual = ""
            for palavra in palavras:
                if len(linha_atual + " " + palavra) <= 80:
                    if linha_atual:
                        linha_atual += " " + palavra
                    else:
                        linha_atual = palavra
                else:
                    if linha_atual:
                        c.drawString(50, y_pos, linha_atual)
                        y_pos -= 25
                    linha_atual = palavra
            # Desenhar a última linha
            if linha_atual:
                c.drawString(50, y_pos, linha_atual)
                y_pos -= 25
        else:
            c.drawString(50, y_pos, texto_valor)
            y_pos -= 35
        
        c.drawString(50, y_pos, f"referente PAGAMENTO DE COMISSÃO DO MÊS DE {mes_referencia} DE {ano_referencia}")
        y_pos -= 40
        
        # Descriminação dos valores
        c.setFont("Helvetica-Bold", 12)
        c.drawString(50, y_pos, "Descriminação dos Valores:")
        y_pos -= 25
        
        c.setFont("Helvetica", 12)
        if comissao > 0:
            c.drawString(70, y_pos, f"Comissão: {comissao_formatada}")
            y_pos -= 20
        
        if premiacao > 0:
            c.drawString(70, y_pos, f"Gratificação: {premiacao_formatada}")
            y_pos -= 20
        
        y_pos -= 20
        
        # Linha separadora
        c.setStrokeColor(colors.black)
        c.setLineWidth(2)
        c.line(50, y_pos, 550, y_pos)
        y_pos -= 40
        
        # Quitação
        c.setFont("Helvetica", 12)
        c.drawString(50, y_pos, "Sendo verdade, dou plena e rasa quitação")
        y_pos -= 30
        
        # Local e data
        c.drawString(50, y_pos, "MACEIÓ-AL")
        y_pos -= 20
        c.drawString(50, y_pos, data_atual)
        y_pos -= 50
        
        # Assinatura
        c.setStrokeColor(colors.black)
        c.setLineWidth(1)
        c.line(50, y_pos, 350, y_pos)
        y_pos -= 25
        c.setFont("Helvetica-Bold", 12)
        c.drawString(50, y_pos, nome_limpo)
        
        # Rodapé com informações da empresa
        c.setFillColor(colors.black)
        c.setFont("Helvetica", 8)
        c.drawString(50, 50, f"{config['nome_empresa']} - Operadora Turística")
        c.drawString(50, 40, config['endereco'])
        if config['telefone']:
            c.drawString(50, 30, f"Tel: {config['telefone']}")
        if config['email']:
            c.drawString(50, 20, f"Email: {config['email']}")
        
        # Adicionar nova página se não for o último funcionário
        if i < len(dados) - 1:
            c.showPage()
    
    # Salvar PDF
    c.save()

def gerar_recibo_individual(nome, valor, data, observacoes, referencia, output_path):
    """Gera um recibo individual em PDF para recibo avulso com layout personalizado"""
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.lib.utils import ImageReader
    from datetime import datetime
    import os
    
    # Remover prefixos indesejados do nome (ex.: "T " antes de "Danielle")
    nome_limpo = nome.strip()
    codigos_remover = ['T.RIZ ', 'A ', 'C ', 'R ', 'T. ', 'T ', 'TR.IZ ', 'ADMINISTRAÇ ÃO. ']
    for codigo in codigos_remover:
        if nome_limpo.startswith(codigo):
            nome_limpo = nome_limpo[len(codigo):].strip()
            break
    
    # Carregar configurações da empresa
    config = carregar_config_empresa()
    
    # Criar PDF
    c = canvas.Canvas(output_path, pagesize=A4)
    width, height = A4
    
    # Formatar valor
    valor_formatado = f"R$ {valor:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    
    # Adicionar imagem de fundo se existir
    watermark_path = _asset_path('static', 'uploads', 'watermark_empresa.png')
    if os.path.exists(watermark_path):
        try:
            c.drawImage(watermark_path, 0, 0, width=width, height=height, mask='auto')
        except:
            pass  # Se houver erro, continua sem a imagem de fundo
    
    # Cabeçalho com logo da empresa
    c.setFillColor(colors.black)
    c.rect(50, 750, 500, 60, fill=1, stroke=0)
    
    # Logo da empresa (imagem ou texto)
    logo_path = _asset_path('static', 'uploads', 'logo_empresa.png')
    if os.path.exists(logo_path):
        try:
            c.drawImage(logo_path, 70, 760, width=100, height=40, mask='auto')
        except:
            # Se houver erro, usa texto
            c.setFillColor(colors.white)
            c.setFont("Helvetica-Bold", 28)
            c.drawString(70, 770, config['nome_empresa'])
    else:
        # Logo em texto
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 28)
        c.drawString(70, 770, config['nome_empresa'])
    
    c.setFont("Helvetica", 12)
    c.drawString(70, 755, "OPERADORA TURÍSTICA")
    
    # Valor destacado no canto superior direito
    c.setFillColor(colors.black)
    c.rect(400, 750, 150, 60, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(420, 770, valor_formatado)
    
    # Linha separadora
    c.setStrokeColor(colors.black)
    c.setLineWidth(2)
    c.line(50, 720, 550, 720)
    
    # Título do recibo
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 24)
    c.drawString(50, 680, "RECIBO")
    
    # Linha separadora fina
    c.setStrokeColor(colors.black)
    c.setLineWidth(1)
    c.line(50, 660, 550, 660)
    
    # Conteúdo do recibo
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 14)
    y_pos = 630
    
    c.drawString(50, y_pos, "Recebi de MASTEROP")
    y_pos -= 35
    
    valor_por_extenso = numero_para_palavras(valor)
    # Quebrar texto longo em múltiplas linhas se necessário
    texto_valor = f"a quantia de {valor_por_extenso}"
    if len(texto_valor) > 80:  # Se o texto for muito longo
        # Dividir em palavras e quebrar em linhas
        palavras = texto_valor.split()
        linha_atual = ""
        for palavra in palavras:
            if len(linha_atual + " " + palavra) <= 80:
                if linha_atual:
                    linha_atual += " " + palavra
                else:
                    linha_atual = palavra
            else:
                if linha_atual:
                    c.drawString(50, y_pos, linha_atual)
                    y_pos -= 25
                linha_atual = palavra
        # Desenhar a última linha
        if linha_atual:
            c.drawString(50, y_pos, linha_atual)
            y_pos -= 25
    else:
        c.drawString(50, y_pos, texto_valor)
        y_pos -= 35
    
    # Referência personalizada (se fornecida)
    if referencia:
        texto_referencia = f"referente {referencia}"
        if len(texto_referencia) > 80:  # Se o texto for muito longo
            # Dividir em palavras e quebrar em linhas
            palavras = texto_referencia.split()
            linha_atual = ""
            for palavra in palavras:
                if len(linha_atual + " " + palavra) <= 80:
                    if linha_atual:
                        linha_atual += " " + palavra
                    else:
                        linha_atual = palavra
                else:
                    if linha_atual:
                        c.drawString(50, y_pos, linha_atual)
                        y_pos -= 25
                    linha_atual = palavra
            # Desenhar a última linha
            if linha_atual:
                c.drawString(50, y_pos, linha_atual)
                y_pos -= 25
        else:
            c.drawString(50, y_pos, texto_referencia)
            y_pos -= 30
    else:
        c.drawString(50, y_pos, "referente pagamento de serviços")
        y_pos -= 30
    
    # Adicionar observações se existirem
    if observacoes:
        c.drawString(50, y_pos, f"Observações: {observacoes}")
        y_pos -= 30
    
    y_pos -= 20
    
    # Linha separadora
    c.setStrokeColor(colors.black)
    c.setLineWidth(2)
    c.line(50, y_pos, 550, y_pos)
    y_pos -= 40
    
    # Quitação
    c.setFont("Helvetica", 12)
    c.drawString(50, y_pos, "Sendo verdade, dou plena e rasa quitação")
    y_pos -= 30
    
    # Local e data
    c.drawString(50, y_pos, "MACEIÓ-AL")
    y_pos -= 20
    c.drawString(50, y_pos, data)
    y_pos -= 50
    
    # Assinatura
    c.setStrokeColor(colors.black)
    c.setLineWidth(1)
    c.line(50, y_pos, 350, y_pos)
    y_pos -= 25
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y_pos, nome_limpo)
    
    # Rodapé com informações da empresa
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 8)
    c.drawString(50, 50, f"{config['nome_empresa']} - Operadora Turística")
    c.drawString(50, 40, config['endereco'])
    if config['telefone']:
        c.drawString(50, 30, f"Tel: {config['telefone']}")
    if config['email']:
        c.drawString(50, 20, f"Email: {config['email']}")
    
    # Salvar PDF
    c.save()

def gerar_recibo_vale_transporte(nome, valor, data, output_path):
    """Gera recibo específico para vale transporte"""
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.lib.utils import ImageReader
    from datetime import datetime
    import os
    
    # Carregar configurações da empresa
    config = carregar_config_empresa()
    
    # Calcular mês subsequente
    hoje = datetime.now()
    if hoje.month == 12:
        mes_subsequente = 1
        ano_subsequente = hoje.year + 1
    else:
        mes_subsequente = hoje.month + 1
        ano_subsequente = hoje.year
    
    # Mapear números para nomes dos meses
    meses = {
        1: 'JANEIRO', 2: 'FEVEREIRO', 3: 'MARÇO', 4: 'ABRIL',
        5: 'MAIO', 6: 'JUNHO', 7: 'JULHO', 8: 'AGOSTO',
        9: 'SETEMBRO', 10: 'OUTUBRO', 11: 'NOVEMBRO', 12: 'DEZEMBRO'
    }
    
    mes_referencia = meses[mes_subsequente]
    ano_referencia = ano_subsequente
    
    # Criar PDF
    c = canvas.Canvas(output_path, pagesize=A4)
    width, height = A4
    
    # Formatar valor
    valor_formatado = f"R$ {valor:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    
    # Adicionar imagem de fundo se existir
    watermark_path = _asset_path('static', 'uploads', 'watermark_empresa.png')
    if os.path.exists(watermark_path):
        try:
            c.drawImage(watermark_path, 0, 0, width=width, height=height, mask='auto')
        except:
            pass
    
    # Cabeçalho com logo da empresa
    c.setFillColor(colors.black)
    c.rect(50, 750, 500, 60, fill=1, stroke=0)
    
    # Logo da empresa
    logo_path = _asset_path('static', 'uploads', 'logo_empresa.png')
    if os.path.exists(logo_path):
        try:
            c.drawImage(logo_path, 70, 760, width=100, height=40, mask='auto')
        except:
            c.setFillColor(colors.white)
            c.setFont("Helvetica-Bold", 28)
            c.drawString(70, 770, config['nome_empresa'])
    else:
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 28)
        c.drawString(70, 770, config['nome_empresa'])
    
    c.setFont("Helvetica", 12)
    c.drawString(70, 755, "OPERADORA TURÍSTICA")
    
    # Valor destacado
    c.setFillColor(colors.black)
    c.rect(400, 750, 150, 60, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(420, 770, valor_formatado)
    
    # Linha separadora
    c.setStrokeColor(colors.black)
    c.setLineWidth(2)
    c.line(50, 720, 550, 720)
    
    # Título do recibo
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 24)
    c.drawString(50, 680, "RECIBO DE VALE TRANSPORTE")
    
    # Linha separadora fina
    c.setStrokeColor(colors.black)
    c.setLineWidth(1)
    c.line(50, 660, 550, 660)
    
    # Conteúdo do recibo
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 14)
    y_pos = 630
    
    c.drawString(50, y_pos, "Recebi de MASTEROP")
    y_pos -= 35
    
    valor_por_extenso = numero_para_palavras(valor)
    texto_valor = f"a quantia de {valor_por_extenso}"
    if len(texto_valor) > 80:
        palavras = texto_valor.split()
        linha_atual = ""
        for palavra in palavras:
            if len(linha_atual + " " + palavra) <= 80:
                if linha_atual:
                    linha_atual += " " + palavra
                else:
                    linha_atual = palavra
            else:
                if linha_atual:
                    c.drawString(50, y_pos, linha_atual)
                    y_pos -= 25
                linha_atual = palavra
        if linha_atual:
            c.drawString(50, y_pos, linha_atual)
            y_pos -= 25
    else:
        c.drawString(50, y_pos, texto_valor)
        y_pos -= 35
    
    c.drawString(50, y_pos, f"referente VALE TRANSPORTE DO MÊS DE {mes_referencia} DE {ano_referencia}")
    y_pos -= 40
    
    # Descriminação dos valores
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y_pos, "Descriminação dos Valores:")
    y_pos -= 25
    
    c.setFont("Helvetica", 12)
    c.drawString(70, y_pos, f"Vale Transporte: {valor_formatado}")
    y_pos -= 20
    
    y_pos -= 20
    
    # Linha separadora
    c.setStrokeColor(colors.black)
    c.setLineWidth(2)
    c.line(50, y_pos, 550, y_pos)
    y_pos -= 40
    
    # Quitação
    c.setFont("Helvetica", 12)
    c.drawString(50, y_pos, "Sendo verdade, dou plena e rasa quitação")
    y_pos -= 30
    
    # Local e data
    c.drawString(50, y_pos, "MACEIÓ-AL")
    y_pos -= 20
    c.drawString(50, y_pos, data)
    y_pos -= 50
    
    # Assinatura
    c.setStrokeColor(colors.black)
    c.setLineWidth(1)
    c.line(50, y_pos, 350, y_pos)
    y_pos -= 25
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y_pos, nome)
    
    # Rodapé
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 8)
    c.drawString(50, 50, f"{config['nome_empresa']} - Operadora Turística")
    c.drawString(50, 40, config['endereco'])
    if config['telefone']:
        c.drawString(50, 30, f"Tel: {config['telefone']}")
    if config['email']:
        c.drawString(50, 20, f"Email: {config['email']}")
    
    c.save()

def gerar_recibo_ajuda_custo(nome, valor, data, output_path):
    """Gera recibo específico para ajuda de custo"""
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.lib.utils import ImageReader
    from datetime import datetime
    import os
    
    # Carregar configurações da empresa
    config = carregar_config_empresa()
    
    # Calcular mês subsequente
    hoje = datetime.now()
    if hoje.month == 12:
        mes_subsequente = 1
        ano_subsequente = hoje.year + 1
    else:
        mes_subsequente = hoje.month + 1
        ano_subsequente = hoje.year
    
    # Mapear números para nomes dos meses
    meses = {
        1: 'JANEIRO', 2: 'FEVEREIRO', 3: 'MARÇO', 4: 'ABRIL',
        5: 'MAIO', 6: 'JUNHO', 7: 'JULHO', 8: 'AGOSTO',
        9: 'SETEMBRO', 10: 'OUTUBRO', 11: 'NOVEMBRO', 12: 'DEZEMBRO'
    }
    
    mes_referencia = meses[mes_subsequente]
    ano_referencia = ano_subsequente
    
    # Criar PDF
    c = canvas.Canvas(output_path, pagesize=A4)
    width, height = A4
    
    # Formatar valor
    valor_formatado = f"R$ {valor:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    
    # Adicionar imagem de fundo se existir
    watermark_path = _asset_path('static', 'uploads', 'watermark_empresa.png')
    if os.path.exists(watermark_path):
        try:
            c.drawImage(watermark_path, 0, 0, width=width, height=height, mask='auto')
        except:
            pass
    
    # Cabeçalho com logo da empresa
    c.setFillColor(colors.black)
    c.rect(50, 750, 500, 60, fill=1, stroke=0)
    
    # Logo da empresa
    logo_path = _asset_path('static', 'uploads', 'logo_empresa.png')
    if os.path.exists(logo_path):
        try:
            c.drawImage(logo_path, 70, 760, width=100, height=40, mask='auto')
        except:
            c.setFillColor(colors.white)
            c.setFont("Helvetica-Bold", 28)
            c.drawString(70, 770, config['nome_empresa'])
    else:
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 28)
        c.drawString(70, 770, config['nome_empresa'])
    
    c.setFont("Helvetica", 12)
    c.drawString(70, 755, "OPERADORA TURÍSTICA")
    
    # Valor destacado
    c.setFillColor(colors.black)
    c.rect(400, 750, 150, 60, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 20)
    c.drawString(420, 770, valor_formatado)
    
    # Linha separadora
    c.setStrokeColor(colors.black)
    c.setLineWidth(2)
    c.line(50, 720, 550, 720)
    
    # Título do recibo
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 24)
    c.drawString(50, 680, "RECIBO DE AJUDA DE CUSTO")
    
    # Linha separadora fina
    c.setStrokeColor(colors.black)
    c.setLineWidth(1)
    c.line(50, 660, 550, 660)
    
    # Conteúdo do recibo
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 14)
    y_pos = 630
    
    c.drawString(50, y_pos, "Recebi de MASTEROP")
    y_pos -= 35
    
    valor_por_extenso = numero_para_palavras(valor)
    texto_valor = f"a quantia de {valor_por_extenso}"
    if len(texto_valor) > 80:
        palavras = texto_valor.split()
        linha_atual = ""
        for palavra in palavras:
            if len(linha_atual + " " + palavra) <= 80:
                if linha_atual:
                    linha_atual += " " + palavra
                else:
                    linha_atual = palavra
            else:
                if linha_atual:
                    c.drawString(50, y_pos, linha_atual)
                    y_pos -= 25
                linha_atual = palavra
        if linha_atual:
            c.drawString(50, y_pos, linha_atual)
            y_pos -= 25
    else:
        c.drawString(50, y_pos, texto_valor)
        y_pos -= 35
    
    c.drawString(50, y_pos, f"referente AJUDA DE CUSTO DO MÊS DE {mes_referencia} DE {ano_referencia}")
    y_pos -= 40
    
    # Descriminação dos valores
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y_pos, "Descriminação dos Valores:")
    y_pos -= 25
    
    c.setFont("Helvetica", 12)
    c.drawString(70, y_pos, f"Ajuda de Custo: {valor_formatado}")
    y_pos -= 20
    
    y_pos -= 20
    
    # Linha separadora
    c.setStrokeColor(colors.black)
    c.setLineWidth(2)
    c.line(50, y_pos, 550, y_pos)
    y_pos -= 40
    
    # Quitação
    c.setFont("Helvetica", 12)
    c.drawString(50, y_pos, "Sendo verdade, dou plena e rasa quitação")
    y_pos -= 30
    
    # Local e data
    c.drawString(50, y_pos, "MACEIÓ-AL")
    y_pos -= 20
    c.drawString(50, y_pos, data)
    y_pos -= 50
    
    # Assinatura
    c.setStrokeColor(colors.black)
    c.setLineWidth(1)
    c.line(50, y_pos, 350, y_pos)
    y_pos -= 25
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y_pos, nome)
    
    # Rodapé
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 8)
    c.drawString(50, 50, f"{config['nome_empresa']} - Operadora Turística")
    c.drawString(50, 40, config['endereco'])
    if config['telefone']:
        c.drawString(50, 30, f"Tel: {config['telefone']}")
    if config['email']:
        c.drawString(50, 20, f"Email: {config['email']}")
    
    c.save()

def gerar_pdf_unico_vale_transporte(dados, output_path):
    """Gera um único PDF com todos os recibos de vale transporte e ajuda de custo"""
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.lib import colors
    from reportlab.lib.utils import ImageReader
    from datetime import datetime
    import os
    
    # Carregar configurações da empresa
    config = carregar_config_empresa()
    
    # Calcular mês subsequente
    hoje = datetime.now()
    if hoje.month == 12:
        mes_subsequente = 1
        ano_subsequente = hoje.year + 1
    else:
        mes_subsequente = hoje.month + 1
        ano_subsequente = hoje.year
    
    # Mapear números para nomes dos meses
    meses = {
        1: 'JANEIRO', 2: 'FEVEREIRO', 3: 'MARÇO', 4: 'ABRIL',
        5: 'MAIO', 6: 'JUNHO', 7: 'JULHO', 8: 'AGOSTO',
        9: 'SETEMBRO', 10: 'OUTUBRO', 11: 'NOVEMBRO', 12: 'DEZEMBRO'
    }
    
    mes_referencia = meses[mes_subsequente]
    ano_referencia = ano_subsequente
    
    # Criar PDF
    c = canvas.Canvas(output_path, pagesize=A4)
    width, height = A4
    
    data_atual = datetime.now().strftime("%d/%m/%Y")
    
    # Gerar uma página para cada funcionário
    for i, funcionario in enumerate(dados):
        nome = funcionario['nome']
        tipo = funcionario['tipo']
        valor = funcionario['valor']
        data = funcionario['data']
        
        # Formatar valor
        valor_formatado = f"R$ {valor:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
        
        # Adicionar imagem de fundo se existir
        watermark_path = _asset_path('static', 'uploads', 'watermark_empresa.png')
        if os.path.exists(watermark_path):
            try:
                c.drawImage(watermark_path, 0, 0, width=width, height=height, mask='auto')
            except:
                pass
        
        # Cabeçalho com logo da empresa
        c.setFillColor(colors.black)
        c.rect(50, 750, 500, 60, fill=1, stroke=0)
        
        # Logo da empresa
        logo_path = _asset_path('static', 'uploads', 'logo_empresa.png')
        if os.path.exists(logo_path):
            try:
                c.drawImage(logo_path, 70, 760, width=100, height=40, mask='auto')
            except:
                c.setFillColor(colors.white)
                c.setFont("Helvetica-Bold", 28)
                c.drawString(70, 770, config['nome_empresa'])
        else:
            c.setFillColor(colors.white)
            c.setFont("Helvetica-Bold", 28)
            c.drawString(70, 770, config['nome_empresa'])
        
        c.setFont("Helvetica", 12)
        c.drawString(70, 755, "OPERADORA TURÍSTICA")
        
        # Valor destacado
        c.setFillColor(colors.black)
        c.rect(400, 750, 150, 60, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 20)
        c.drawString(420, 770, valor_formatado)
        
        # Linha separadora
        c.setStrokeColor(colors.black)
        c.setLineWidth(2)
        c.line(50, 720, 550, 720)
        
        # Título do recibo baseado no tipo
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 24)
        if tipo == 'vale_transporte':
            c.drawString(50, 680, "RECIBO DE VALE TRANSPORTE")
        else:
            c.drawString(50, 680, "RECIBO DE AJUDA DE CUSTO")
        
        # Linha separadora fina
        c.setStrokeColor(colors.black)
        c.setLineWidth(1)
        c.line(50, 660, 550, 660)
        
        # Conteúdo do recibo
        c.setFillColor(colors.black)
        c.setFont("Helvetica", 14)
        y_pos = 630
        
        c.drawString(50, y_pos, "Recebi de MASTEROP")
        y_pos -= 35
        
        valor_por_extenso = numero_para_palavras(valor)
        texto_valor = f"a quantia de {valor_por_extenso}"
        if len(texto_valor) > 80:
            palavras = texto_valor.split()
            linha_atual = ""
            for palavra in palavras:
                if len(linha_atual + " " + palavra) <= 80:
                    if linha_atual:
                        linha_atual += " " + palavra
                    else:
                        linha_atual = palavra
                else:
                    if linha_atual:
                        c.drawString(50, y_pos, linha_atual)
                        y_pos -= 25
                    linha_atual = palavra
            if linha_atual:
                c.drawString(50, y_pos, linha_atual)
                y_pos -= 25
        else:
            c.drawString(50, y_pos, texto_valor)
            y_pos -= 35
        
        # Referência baseada no tipo
        if tipo == 'vale_transporte':
            c.drawString(50, y_pos, f"referente VALE TRANSPORTE DO MÊS DE {mes_referencia} DE {ano_referencia}")
        else:
            c.drawString(50, y_pos, f"referente AJUDA DE CUSTO DO MÊS DE {mes_referencia} DE {ano_referencia}")
        y_pos -= 40
        
        # Descriminação dos valores
        c.setFont("Helvetica-Bold", 12)
        c.drawString(50, y_pos, "Descriminação dos Valores:")
        y_pos -= 25
        
        c.setFont("Helvetica", 12)
        if tipo == 'vale_transporte':
            c.drawString(70, y_pos, f"Vale Transporte: {valor_formatado}")
        else:
            c.drawString(70, y_pos, f"Ajuda de Custo: {valor_formatado}")
        y_pos -= 20
        
        y_pos -= 20
        
        # Linha separadora
        c.setStrokeColor(colors.black)
        c.setLineWidth(2)
        c.line(50, y_pos, 550, y_pos)
        y_pos -= 40
        
        # Quitação
        c.setFont("Helvetica", 12)
        c.drawString(50, y_pos, "Sendo verdade, dou plena e rasa quitação")
        y_pos -= 30
        
        # Local e data
        c.drawString(50, y_pos, "MACEIÓ-AL")
        y_pos -= 20
        c.drawString(50, y_pos, data)
        y_pos -= 50
        
        # Assinatura
        c.setStrokeColor(colors.black)
        c.setLineWidth(1)
        c.line(50, y_pos, 350, y_pos)
        y_pos -= 25
        c.setFont("Helvetica-Bold", 12)
        c.drawString(50, y_pos, nome)
        
        # Rodapé
        c.setFillColor(colors.black)
        c.setFont("Helvetica", 8)
        c.drawString(50, 50, f"{config['nome_empresa']} - Operadora Turística")
        c.drawString(50, 40, config['endereco'])
        if config['telefone']:
            c.drawString(50, 30, f"Tel: {config['telefone']}")
        if config['email']:
            c.drawString(50, 20, f"Email: {config['email']}")
        
        # Adicionar nova página se não for o último funcionário
        if i < len(dados) - 1:
            c.showPage()
    
    # Salvar PDF
    c.save()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/configuracoes')
def configuracoes():
    """Tela de configurações para personalizar recibos"""
    config = carregar_config_empresa()
    return render_template('configuracoes.html', config=config)

@app.route('/salvar_configuracoes', methods=['POST'])
def salvar_configuracoes():
    """Salva as configurações da empresa"""
    if IS_SERVERLESS:
        flash(
            'No Vercel as configurações vêm do arquivo config_empresa.json no repositório. '
            'Edite o arquivo, faça redeploy ou use variáveis de ambiente (EMPRESA_NOME, EMPRESA_ENDERECO, etc.).',
            'warning',
        )
        return redirect(url_for('configuracoes'))

    try:
        # Obter dados do formulário
        nome_empresa = request.form.get('nome_empresa', 'MASTEROP')
        endereco = request.form.get('endereco', 'Av. Gov. Osman Loureiro, 49 - 403 - Mangabeiras, Maceió - AL, 57037-630')
        telefone = request.form.get('telefone', '(82) 3216-2000')
        email = request.form.get('email', '')
        site = request.form.get('site', '')
        
        # Salvar configurações em arquivo JSON
        config = {
            'nome_empresa': nome_empresa,
            'endereco': endereco,
            'telefone': telefone,
            'email': email,
            'site': site
        }
        
        config_path = _asset_path('config_empresa.json')
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        
        flash('Configurações salvas com sucesso!', 'success')
        return redirect(url_for('configuracoes'))
        
    except Exception as e:
        flash(f'Erro ao salvar configurações: {str(e)}', 'error')
        return redirect(url_for('configuracoes'))

@app.route('/upload_logo', methods=['POST'])
def upload_logo():
    """Upload da logo da empresa"""
    if IS_SERVERLESS:
        flash('No Vercel o upload de logo não persiste. Coloque logo_empresa.png em static/uploads/ no repositório.', 'warning')
        return redirect(url_for('configuracoes'))

    try:
        if 'logo' not in request.files:
            flash('Nenhum arquivo selecionado', 'error')
            return redirect(url_for('configuracoes'))
        
        file = request.files['logo']
        if file.filename == '':
            flash('Nenhum arquivo selecionado', 'error')
            return redirect(url_for('configuracoes'))
        
        if file and allowed_image_file(file.filename):
            filename = secure_filename('logo_empresa.png')
            filepath = _asset_path('static', 'uploads', filename)
            file.save(filepath)
            
            flash('Logo salva com sucesso!', 'success')
        else:
            flash('Formato de arquivo não permitido. Use PNG, JPG ou JPEG', 'error')
            
        return redirect(url_for('configuracoes'))
        
    except Exception as e:
        flash(f'Erro ao fazer upload da logo: {str(e)}', 'error')
        return redirect(url_for('configuracoes'))

@app.route('/upload_watermark', methods=['POST'])
def upload_watermark():
    """Upload da imagem de fundo timbrado"""
    if IS_SERVERLESS:
        flash('No Vercel o upload de marca d\'água não persiste. Coloque watermark_empresa.png em static/uploads/ no repositório.', 'warning')
        return redirect(url_for('configuracoes'))

    try:
        if 'watermark' not in request.files:
            flash('Nenhum arquivo selecionado', 'error')
            return redirect(url_for('configuracoes'))
        
        file = request.files['watermark']
        if file.filename == '':
            flash('Nenhum arquivo selecionado', 'error')
            return redirect(url_for('configuracoes'))
        
        if file and allowed_image_file(file.filename):
            filename = secure_filename('watermark_empresa.png')
            filepath = _asset_path('static', 'uploads', filename)
            file.save(filepath)
            
            flash('Imagem de fundo salva com sucesso!', 'success')
        else:
            flash('Formato de arquivo não permitido. Use PNG, JPG ou JPEG', 'error')
            
        return redirect(url_for('configuracoes'))
        
    except Exception as e:
        flash(f'Erro ao fazer upload da imagem de fundo: {str(e)}', 'error')
        return redirect(url_for('configuracoes'))

def allowed_image_file(filename):
    """Verifica se o arquivo de imagem tem extensão permitida"""
    ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS

def carregar_config_empresa():
    """Carrega as configurações da empresa"""
    config = {
        'nome_empresa': 'MASTEROP',
        'endereco': 'Av. Gov. Osman Loureiro, 49 - 403 - Mangabeiras, Maceió - AL, 57037-630',
        'telefone': '(82) 3216-2000',
        'email': '',
        'site': '',
    }

    try:
        config_path = _asset_path('config_empresa.json')
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                config.update(json.load(f))
    except Exception:
        pass

    env_map = {
        'EMPRESA_NOME': 'nome_empresa',
        'EMPRESA_ENDERECO': 'endereco',
        'EMPRESA_TELEFONE': 'telefone',
        'EMPRESA_EMAIL': 'email',
        'EMPRESA_SITE': 'site',
    }
    for env_key, config_key in env_map.items():
        if os.environ.get(env_key):
            config[config_key] = os.environ[env_key]

    return config

@app.route('/previa')
def previa():
    """Mostra prévia dos dados extraídos"""
    # Buscar dados da sessão (garantir que nunca seja None)
    dados_previa = session.get('dados_previa') or []
    if not isinstance(dados_previa, list):
        dados_previa = []
    return render_template('previa_tabela.html', dados=dados_previa)

@app.route('/upload', methods=['POST'])
def upload_file():
    print("🔍 INICIANDO UPLOAD DE ARQUIVO...")
    
    if 'arquivo' not in request.files:
        print("❌ Nenhum arquivo encontrado na requisição")
        flash('Nenhum arquivo selecionado', 'error')
        return redirect(url_for('index'))
    
    file = request.files['arquivo']
    print(f"📁 Arquivo recebido: {file.filename}")
    print(f"📁 Tipo MIME: {file.content_type}")
    print(f"📁 Tamanho: {file.content_length if hasattr(file, 'content_length') else 'N/A'} bytes")
    
    if file.filename == '':
        print("❌ Nome do arquivo está vazio")
        flash('Nenhum arquivo selecionado', 'error')
        return redirect(url_for('index'))
    
    # Verificar se é um arquivo válido
    if not file:
        print("❌ Arquivo é None")
        flash('Arquivo inválido', 'error')
        return redirect(url_for('index'))
    
    # Verificar extensão
    if not allowed_file(file.filename):
        print(f"❌ Extensão não permitida: {file.filename}")
        flash('Tipo de arquivo não permitido. Use apenas PDF.', 'error')
        return redirect(url_for('index'))
    
    print("✅ Arquivo validado com sucesso")
    
    # Limpar nome do arquivo removendo caracteres problemáticos
    filename = secure_filename(file.filename)
    # Remover caracteres adicionais que podem causar problemas
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    filename = re.sub(r'[^\w\-_\.]', '_', filename)
    
    print(f"📁 Nome do arquivo limpo: {filename}")
    
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    print(f"📁 Caminho completo: {filepath}")
    
    try:
        file.save(filepath)
        print("✅ Arquivo salvo com sucesso")
        
        # Verificar se o arquivo foi salvo
        if not os.path.exists(filepath):
            print("❌ Arquivo não foi salvo corretamente")
            flash('Erro ao salvar arquivo', 'error')
            return redirect(url_for('index'))
        
        print(f"✅ Arquivo existe: {os.path.getsize(filepath)} bytes")
        
        # Extrair dados do PDF
        print("🔍 Iniciando extração de dados...")
        dados = extrair_dados_pdf(filepath)
        
        if not dados:
            print("❌ Nenhum dado extraído do PDF")
            flash('Nenhum dado válido encontrado no PDF. Verifique se o arquivo contém dados de comissão no formato esperado.', 'error')
            return redirect(url_for('index'))
        
        print(f"✅ Dados extraídos: {len(dados)} funcionários")
        
        flash(
            f'Dados extraídos com sucesso! {len(dados)} funcionários encontrados. Verifique a prévia antes de gerar os recibos.',
            'success',
        )
        return render_template('previa_tabela.html', dados=dados)
        
    except Exception as e:
        error_msg = f'Erro ao processar arquivo: {str(e)}'
        print(f"❌ ERRO DETALHADO: {error_msg}")
        print(f"❌ TIPO DO ERRO: {type(e).__name__}")
        import traceback
        print(f"❌ TRACEBACK: {traceback.format_exc()}")
        flash(error_msg, 'error')
    finally:
        # Limpar arquivo temporário
        if os.path.exists(filepath):
            print(f"🗑️ Removendo arquivo temporário: {filepath}")
            os.remove(filepath)
    
    return redirect(url_for('index'))

@app.route('/gerar_recibos', methods=['POST'])
def gerar_recibos():
    """Gera um único PDF com todos os recibos"""
    dados = _obter_dados_form_ou_sessao('dados_previa')
    
    if not dados:
        flash('Nenhum dado encontrado. Faça upload do PDF novamente.', 'error')
        return redirect(url_for('index'))
    
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        nome_arquivo = f"recibos_comissoes_{timestamp}.pdf"
        output_path = os.path.join(OUTPUT_FOLDER, nome_arquivo)
        
        gerar_pdf_unico(dados, output_path)
        session.pop('dados_previa', None)
        
        return send_file(
            output_path,
            as_attachment=True,
            download_name=nome_arquivo,
            mimetype='application/pdf',
        )
        
    except Exception as e:
        flash(f'Erro ao gerar recibos: {str(e)}', 'error')
        print(f"Erro ao gerar recibos: {e}")
    
    return redirect(url_for('index'))

@app.route('/download_pdf')
def download_pdf():
    """Download do PDF único gerado"""
    try:
        arquivo_pdf = session.get('arquivo_pdf_gerado')
        
        if not arquivo_pdf:
            flash('Nenhum PDF gerado encontrado. Gere os recibos primeiro.', 'error')
            return redirect(url_for('index'))
        
        arquivo_path = os.path.join(OUTPUT_FOLDER, arquivo_pdf)
        
        if not os.path.exists(arquivo_path):
            flash('Arquivo PDF não encontrado. Gere os recibos novamente.', 'error')
            return redirect(url_for('index'))
        
        return send_file(
            arquivo_path,
            as_attachment=True,
            download_name=arquivo_pdf,
            mimetype='application/pdf'
        )
        
    except Exception as e:
        flash(f'Erro ao baixar PDF: {str(e)}', 'error')
        return redirect(url_for('index'))

@app.route('/imprimir_todos', methods=['GET', 'POST'])
def imprimir_todos():
    """Visualiza o PDF único gerado para impressão"""
    try:
        if request.method == 'POST':
            dados = _obter_dados_form_ou_sessao('dados_previa')
            if not dados:
                flash('Nenhum dado encontrado. Faça upload do PDF novamente.', 'error')
                return redirect(url_for('index'))

            output_path = _arquivo_temporario('recibos_')
            gerar_pdf_unico(dados, output_path)
            with open(output_path, 'rb') as pdf_file:
                pdf_base64 = base64.b64encode(pdf_file.read()).decode('ascii')

            return render_template(
                'imprimir_todos.html',
                pdf_base64=pdf_base64,
                pdf_unico=None,
            )

        arquivo_pdf = session.get('arquivo_pdf_gerado')
        
        if not arquivo_pdf:
            flash('Nenhum PDF gerado encontrado. Gere os recibos primeiro.', 'error')
            return redirect(url_for('index'))
        
        arquivo_path = os.path.join(OUTPUT_FOLDER, arquivo_pdf)
        
        if not os.path.exists(arquivo_path):
            flash('Arquivo PDF não encontrado. Gere os recibos novamente.', 'error')
            return redirect(url_for('index'))
        
        return render_template('imprimir_todos.html', pdf_unico=arquivo_pdf, pdf_base64=None)
        
    except Exception as e:
        flash(f'Erro ao visualizar PDF: {str(e)}', 'error')
        return redirect(url_for('index'))

# Rota de download ZIP removida conforme solicitado
# @app.route('/download_zip')
# def download_zip():
#     # Funcionalidade removida
#     pass

@app.route('/api/status')
def api_status():
    """API para verificar status do servidor"""
    return jsonify({
        'status': 'online',
        'timestamp': datetime.now().isoformat(),
        'version': '2.0.0'
    })

@app.route('/teste_csv')
def teste_csv():
    """Rota para testar processamento CSV"""
    try:
        # Testar com arquivo de exemplo
        caminho_teste = 'teste_excel_format.csv'
        if os.path.exists(caminho_teste):
            dados = processar_csv_vale_transporte(caminho_teste)
            return jsonify({
                'sucesso': True,
                'dados': dados,
                'total': len(dados)
            })
        else:
            return jsonify({
                'sucesso': False,
                'erro': 'Arquivo de teste não encontrado'
            })
    except Exception as e:
        return jsonify({
            'sucesso': False,
            'erro': str(e)
        })

@app.route('/limpar')
def limpar_recibos():
    """Limpa todos os recibos gerados"""
    try:
        for root, dirs, files in os.walk(OUTPUT_FOLDER):
            for file in files:
                if file.endswith('.pdf'):
                    os.remove(os.path.join(root, file))
        flash('Todos os recibos foram removidos', 'success')
    except Exception as e:
        flash(f'Erro ao limpar recibos: {str(e)}', 'error')
    
    return redirect(url_for('index'))

@app.route('/recibo_avulso')
def recibo_avulso():
    """Página para gerar recibo avulso"""
    return render_template('recibo_avulso.html')

@app.route('/previa_recibo_avulso', methods=['POST'])
def previa_recibo_avulso():
    """Mostra prévia dos dados do recibo avulso para edição"""
    try:
        dados = _montar_dados_recibo_avulso_form()
        session['dados_recibo_avulso'] = dados
        return render_template('editar_recibo_avulso.html', dados=dados)
    except ValueError as e:
        flash(str(e), 'error')
        return redirect(url_for('recibo_avulso'))
    except Exception as e:
        import traceback
        print(f"ERRO em previa_recibo_avulso: {e}\n{traceback.format_exc()}")
        flash(f'Erro ao processar dados: {str(e)}', 'error')
        return redirect(url_for('recibo_avulso'))

@app.route('/editar_recibo_avulso')
def editar_recibo_avulso():
    """Página de edição dos dados do recibo avulso"""
    dados = session.get('dados_recibo_avulso')
    if not dados or not isinstance(dados, dict):
        flash('Nenhum dado encontrado. Preencha o formulário novamente.', 'error')
        return redirect(url_for('recibo_avulso'))
    # Garantir todas as chaves existem para evitar erro no template
    dados = {
        'nome': dados.get('nome', ''),
        'valor': float(dados.get('valor', 0)),
        'valor_formatado': dados.get('valor_formatado', 'R$ 0,00'),
        'data': dados.get('data', ''),
        'data_br': dados.get('data_br', ''),
        'observacoes': dados.get('observacoes', ''),
        'referencia': dados.get('referencia', ''),
        'valor_por_extenso': dados.get('valor_por_extenso', ''),
    }
    return render_template('editar_recibo_avulso.html', dados=dados)

@app.route('/atualizar_recibo_avulso', methods=['POST'])
def atualizar_recibo_avulso():
    """Atualiza os dados do recibo avulso"""
    try:
        dados = _montar_dados_recibo_avulso_form()
        session['dados_recibo_avulso'] = dados
        flash('Dados atualizados com sucesso!', 'success')
        return render_template('editar_recibo_avulso.html', dados=dados)
    except ValueError as e:
        flash(str(e), 'error')
        return redirect(url_for('recibo_avulso'))
    except Exception as e:
        flash(f'Erro ao atualizar dados: {str(e)}', 'error')
        return redirect(url_for('recibo_avulso'))

@app.route('/gerar_recibo_avulso_final', methods=['POST'])
def gerar_recibo_avulso_final():
    """Gera o recibo avulso final após edição"""
    try:
        dados = _montar_dados_recibo_avulso_form()
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        nome_arquivo = f"Recibo_Avulso_{dados['nome'].replace(' ', '_')}_{timestamp}.pdf"
        output_path = os.path.join(OUTPUT_FOLDER, nome_arquivo)
        
        gerar_recibo_individual(
            dados['nome'],
            dados['valor'],
            dados['data_br'],
            dados['observacoes'],
            dados.get('referencia', ''),
            output_path,
        )
        
        session.pop('dados_recibo_avulso', None)
        
        return send_file(
            output_path,
            as_attachment=True,
            download_name=nome_arquivo,
            mimetype='application/pdf',
        )
        
    except ValueError as e:
        flash(str(e), 'error')
        return redirect(url_for('recibo_avulso'))
    except Exception as e:
        flash(f'Erro ao gerar recibo: {str(e)}', 'error')
        return redirect(url_for('recibo_avulso'))

@app.route('/download_recibo_avulso')
def download_recibo_avulso():
    """Download do recibo avulso gerado"""
    try:
        arquivo_pdf = session.get('arquivo_recibo_avulso')
        
        if not arquivo_pdf:
            flash('Nenhum recibo avulso gerado encontrado.', 'error')
            return redirect(url_for('recibo_avulso'))
        
        arquivo_path = os.path.join(OUTPUT_FOLDER, arquivo_pdf)
        
        if not os.path.exists(arquivo_path):
            flash('Arquivo PDF não encontrado. Gere o recibo novamente.', 'error')
            return redirect(url_for('recibo_avulso'))
        
        return send_file(
            arquivo_path,
            as_attachment=True,
            download_name=arquivo_pdf,
            mimetype='application/pdf'
        )
        
    except Exception as e:
        flash(f'Erro ao baixar PDF: {str(e)}', 'error')
        return redirect(url_for('recibo_avulso'))

@app.route('/vale_transporte_ajuda_custo')
def vale_transporte_ajuda_custo():
    """Página para upload de planilha de vale transporte e ajuda de custo"""
    return render_template('vale_transporte_ajuda_custo.html')


@app.route('/download_modelo_combustivel')
def download_modelo_combustivel():
    """Baixa o modelo padrão Excel (Nome | Veículo | Valor)."""
    modelo_path = _asset_path('modelos', 'modelo_combustivel.xlsx')
    if not os.path.exists(modelo_path):
        # Fallback se o arquivo estiver em static/modelos (ambiente local antigo)
        modelo_path = _asset_path('static', 'modelos', 'modelo_combustivel.xlsx')
    if not os.path.exists(modelo_path):
        flash('Modelo padrão não encontrado.', 'error')
        return redirect(url_for('vale_transporte_ajuda_custo'))
    return send_file(
        modelo_path,
        as_attachment=True,
        download_name='modelo_combustivel.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )


@app.route('/upload_csv_vale_transporte', methods=['POST'])
def upload_csv_vale_transporte():
    """Processa upload de Excel/CSV de vale transporte e ajuda de custo"""
    print("INICIANDO UPLOAD DE PLANILHA...")

    filepath = None
    try:
        if 'arquivo' not in request.files:
            flash('Nenhum arquivo selecionado', 'error')
            return redirect(url_for('vale_transporte_ajuda_custo'))

        file = request.files['arquivo']
        print(f"Arquivo recebido: {file.filename}")

        if not file or file.filename == '':
            flash('Nenhum arquivo selecionado', 'error')
            return redirect(url_for('vale_transporte_ajuda_custo'))

        extensao = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
        if extensao not in ('csv', 'xlsx', 'xls'):
            flash('Tipo de arquivo não permitido. Use Excel (.xlsx) ou CSV.', 'error')
            return redirect(url_for('vale_transporte_ajuda_custo'))

        filename = secure_filename(file.filename) or f'planilha.{extensao}'
        filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
        filename = re.sub(r'[^\w\-_\.]', '_', filename)
        if not filename.lower().endswith(f'.{extensao}'):
            filename = f"{filename}.{extensao}"

        filepath = os.path.join(UPLOAD_FOLDER, filename)
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        file.save(filepath)

        dados = processar_arquivo_vale_transporte(filepath)

        if not dados:
            flash(
                'Nenhum dado válido encontrado. Use o modelo padrão com colunas '
                '"Nome", "Veículo" e "Valor". Se Veículo tiver Carro → Ajuda de Custo; '
                'qualquer outra informação → Vale transporte. '
                'Você pode baixar o modelo na página de upload.',
                'error',
            )
            return redirect(url_for('vale_transporte_ajuda_custo'))

        _salvar_dados_sessao('dados_csv_previa', dados)
        flash(
            f'Dados processados com sucesso! {len(dados)} registros encontrados. Verifique a prévia antes de gerar os recibos.',
            'success',
        )
        # Post-Redirect-Get: evita o navegador ficar na URL do POST (ERR_FAILED ao recarregar)
        return redirect(url_for('previa_csv_vale_transporte'))

    except Exception as e:
        error_msg = f'Erro ao processar arquivo: {str(e)}'
        print(f"ERRO DETALHADO: {error_msg}")
        flash(error_msg, 'error')
        return redirect(url_for('vale_transporte_ajuda_custo'))
    finally:
        if filepath and os.path.exists(filepath):
            try:
                os.remove(filepath)
            except OSError:
                pass


@app.route('/previa_csv_vale_transporte')
def previa_csv_vale_transporte():
    """Mostra prévia dos dados CSV processados"""
    dados_previa = _carregar_dados_sessao('dados_csv_previa')
    if not isinstance(dados_previa, list):
        dados_previa = []
    return render_template('previa_csv_vale_transporte.html', dados=dados_previa)

@app.route('/gerar_recibos_csv', methods=['POST'])
def gerar_recibos_csv():
    """Gera PDF único com todos os recibos de vale transporte e ajuda de custo"""
    dados = _obter_dados_form_ou_sessao('dados_csv_previa')
    
    if not dados:
        flash('Nenhum dado encontrado. Faça upload do CSV novamente.', 'error')
        return redirect(url_for('vale_transporte_ajuda_custo'))
    
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        nome_arquivo = f"recibos_vale_transporte_ajuda_custo_{timestamp}.pdf"
        output_path = os.path.join(OUTPUT_FOLDER, nome_arquivo)
        
        gerar_pdf_unico_vale_transporte(dados, output_path)
        session.pop('dados_csv_previa', None)
        
        return send_file(
            output_path,
            as_attachment=True,
            download_name=nome_arquivo,
            mimetype='application/pdf',
        )
        
    except Exception as e:
        flash(f'Erro ao gerar recibos: {str(e)}', 'error')
        print(f"Erro ao gerar recibos: {e}")
    
    return redirect(url_for('vale_transporte_ajuda_custo'))

@app.route('/download_pdf_csv')
def download_pdf_csv():
    """Download do PDF único gerado dos recibos CSV"""
    try:
        arquivo_pdf = session.get('arquivo_pdf_csv_gerado')
        
        if not arquivo_pdf:
            flash('Nenhum PDF gerado encontrado. Gere os recibos primeiro.', 'error')
            return redirect(url_for('vale_transporte_ajuda_custo'))
        
        arquivo_path = os.path.join(OUTPUT_FOLDER, arquivo_pdf)
        
        if not os.path.exists(arquivo_path):
            flash('Arquivo PDF não encontrado. Gere os recibos novamente.', 'error')
            return redirect(url_for('vale_transporte_ajuda_custo'))
        
        return send_file(
            arquivo_path,
            as_attachment=True,
            download_name=arquivo_pdf,
            mimetype='application/pdf'
        )
        
    except Exception as e:
        flash(f'Erro ao baixar PDF: {str(e)}', 'error')
        return redirect(url_for('vale_transporte_ajuda_custo'))

@app.route('/imprimir_csv', methods=['GET', 'POST'])
def imprimir_csv():
    """Visualiza o PDF único gerado dos recibos CSV para impressão"""
    try:
        if request.method == 'POST':
            dados = _obter_dados_form_ou_sessao('dados_csv_previa')
            if not dados:
                flash('Nenhum dado encontrado. Faça upload do CSV novamente.', 'error')
                return redirect(url_for('vale_transporte_ajuda_custo'))

            output_path = _arquivo_temporario('recibos_csv_')
            gerar_pdf_unico_vale_transporte(dados, output_path)
            with open(output_path, 'rb') as pdf_file:
                pdf_base64 = base64.b64encode(pdf_file.read()).decode('ascii')

            return render_template(
                'imprimir_csv.html',
                pdf_base64=pdf_base64,
                pdf_unico=None,
            )

        arquivo_pdf = session.get('arquivo_pdf_csv_gerado')
        
        if not arquivo_pdf:
            flash('Nenhum PDF gerado encontrado. Gere os recibos primeiro.', 'error')
            return redirect(url_for('vale_transporte_ajuda_custo'))
        
        arquivo_path = os.path.join(OUTPUT_FOLDER, arquivo_pdf)
        
        if not os.path.exists(arquivo_path):
            flash('Arquivo PDF não encontrado. Gere os recibos novamente.', 'error')
            return redirect(url_for('vale_transporte_ajuda_custo'))
        
        return render_template('imprimir_csv.html', pdf_unico=arquivo_pdf, pdf_base64=None)
        
    except Exception as e:
        flash(f'Erro ao visualizar PDF: {str(e)}', 'error')
        return redirect(url_for('vale_transporte_ajuda_custo'))


@app.route('/app', strict_slashes=False)
@app.route('/app/', strict_slashes=False)
@app.route('/app/<path:subpath>')
def vite_frontend(subpath=''):
    """Serve o bundle Vite (React). Compilar: cd frontend && npm install && npm run build."""
    base = os.path.join(_BASE_DIR, 'static', 'app')
    index_path = os.path.join(base, 'index.html')
    if not os.path.isfile(index_path):
        return (
            '<!DOCTYPE html><html lang="pt-BR"><head><meta charset="UTF-8"><title>Recibo Express</title></head>'
            '<body style="font-family:sans-serif;padding:2rem;max-width:40rem;">'
            '<h1>Frontend Vite ainda não foi compilado</h1>'
            '<p>Abre uma consola na pasta <code>frontend</code> do projeto e executa:</p>'
            '<pre style="background:#f1f5f9;padding:1rem;">npm install\nnpm run build</pre>'
            '<p>Depois recarrega esta página. Vê <code>MIGRACAO_VITE.md</code> para o plano completo.</p>'
            '<p><a href="/">Voltar à aplicação atual (Flask)</a></p></body></html>',
            503,
        )
    if subpath:
        try:
            candidate = safe_join(base, subpath)
        except ValueError:
            abort(404)
        if os.path.isfile(candidate):
            rel = os.path.relpath(candidate, base)
            if rel.startswith('..'):
                abort(404)
            return send_from_directory(base, rel)
    return send_from_directory(base, 'index.html')


@app.errorhandler(500)
def erro_interno(e):
    """Trata erro 500 e registra para diagnóstico"""
    import traceback
    tb = traceback.format_exc()
    print(f"ERRO 500 (Internal Server Error):\n{tb}")
    try:
        inicio = url_for('index')
        recibo_avulso = url_for('recibo_avulso')
    except Exception:
        inicio = '/'
        recibo_avulso = '/recibo_avulso'
    return f"""<html><head><meta charset="UTF-8"><title>Erro no servidor</title></head>
    <body style="font-family: sans-serif; padding: 2rem; max-width: 600px; margin: 0 auto;">
    <h1>Erro interno do servidor</h1>
    <p>Ocorreu um erro ao processar sua solicitação. Tente novamente.</p>
    <p><a href="{inicio}">Voltar ao início</a> | <a href="{recibo_avulso}">Recibo avulso</a></p>
    <p style="color:#666; font-size:0.9rem;">Se o problema continuar, verifique o console/terminal do servidor para mais detalhes.</p>
    </body></html>""", 500

if __name__ == '__main__':
    print("=== RECIBO EXPRESS v2.0 ===")
    print("Iniciando servidor...")
    print("Diretorios criados:")
    print(f"   - Uploads: {os.path.abspath(UPLOAD_FOLDER)}")
    print(f"   - Recibos: {os.path.abspath(OUTPUT_FOLDER)}")
    print("Servidor rodando em: http://localhost:5002")
    print("Pressione Ctrl+C para parar o servidor")
    print("=" * 50)
    
    app.run(debug=True, host='0.0.0.0', port=5002)