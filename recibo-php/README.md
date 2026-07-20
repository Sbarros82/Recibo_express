# Recibo Express (PHP)

Reescrita em **PHP 8.1+** para correr em **Hostinger partilhada** (sem Python).

## Instalação local

```bash
cd recibo-php
php -S localhost:8080 -t public
```

Não é obrigatório o Composer: o autoload está em `src/autoload.php`. *(Opcional: `composer install` se o teu PHP tiver OpenSSL.)*

Abre: `http://localhost:8080/index.php?r=home`

## Hostinger

1. Sobe **toda** a pasta `recibo-php` para o servidor (ou compacta e extrai).
2. No domínio, define a **raiz do documento** (`Document root`) para a pasta **`recibo-php/public`**  
   *(no hPanel: Websites → Domínio → raiz do site → apontar para `.../recibo-php/public`)*.
3. Se **não** puderes mudar a raiz e só puderes usar `public_html`: copia o **conteúdo** de `public/` para `public_html` e coloca `src`, `views`, `storage`, `bootstrap.php`, `composer.json` **um nível acima** de `public_html` (espelhando o repositório). O `RE_PROJECT_ROOT` em `public/index.php` deve apontar para a pasta que contém `src` e `views`.

4. Garante que a pasta **`storage/`** é **gravável** (755 ou 775).

## Rotas (por agora)

| GET/POST | Parâmetro `r` |
|----------|----------------|
| GET | `home` |
| GET | `configuracoes` |
| POST | `salvar_configuracoes` |
| POST | `upload_logo` |
| POST | `upload_watermark` |

O plano completo de migração está em **`PLANO_MIGRACAO_PHP.md`**.
