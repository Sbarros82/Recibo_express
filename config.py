"""
Configurações do Recibo Express
"""

import os
from datetime import datetime

class Config:
    """Configurações principais da aplicação"""
    
    # Configurações básicas
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'recibo_express_2024_secure_key'
    DEBUG = True
    
    # Diretórios
    UPLOAD_FOLDER = 'uploads'
    OUTPUT_FOLDER = 'static/recibos'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    
    # Configurações de PDF
    PDF_PAGE_SIZE = 'A4'
    PDF_MARGIN = 2 * 2.54  # 2cm em pontos
    
    # Configurações de processamento
    IGNORE_PREFIX = 'ZZZ_'  # Prefixo para ignorar registros
    SUPPORTED_EXTENSIONS = {'pdf'}
    
    # Configurações de empresa (personalizáveis)
    EMPRESA_NOME = 'Empresa XYZ Ltda'
    EMPRESA_CNPJ = '00.000.000/0001-00'
    EMPRESA_ENDERECO = 'Rua Exemplo, 123 - Centro - Cidade/UF'
    
    # Setores padrão
    SETORES_PADRAO = [
        'Emissores',
        'Executivos de Contas',
        'Diretor Comercial',
        'Gerente Operacional',
        'Supervisores'
    ]
    
    # Configurações de recibo
    RECIBO_TITULO = 'RECIBO DE COMISSÃO'
    RECIBO_DESCRICAO = 'Comissão referente ao período'
    
    # Configurações de servidor
    HOST = '0.0.0.0'
    PORT = 5002
    
    @staticmethod
    def get_data_atual():
        """Retorna a data atual formatada"""
        return datetime.now().strftime('%d/%m/%Y')
    
    @staticmethod
    def get_timestamp():
        """Retorna timestamp atual"""
        return datetime.now().strftime('%Y%m%d_%H%M%S')
    
    @staticmethod
    def formatar_valor(valor):
        """Formata valor monetário"""
        return f"R$ {valor:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    
    @staticmethod
    def sanitizar_nome(nome):
        """Sanitiza nome para nome de arquivo"""
        import re
        # Remove caracteres especiais e substitui espaços por underscore
        nome_limpo = re.sub(r'[^\w\s-]', '', nome)
        nome_limpo = re.sub(r'[-\s]+', '_', nome_limpo)
        return nome_limpo.strip('_')

class DevelopmentConfig(Config):
    """Configurações para desenvolvimento"""
    DEBUG = True
    TESTING = False

class ProductionConfig(Config):
    """Configurações para produção"""
    DEBUG = False
    TESTING = False
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'production_secret_key_change_this'

class TestingConfig(Config):
    """Configurações para testes"""
    DEBUG = True
    TESTING = True
    WTF_CSRF_ENABLED = False

# Configuração padrão
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
