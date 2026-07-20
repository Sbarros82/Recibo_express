<?php

declare(strict_types=1);

/**
 * Arranque global (sessão, helpers).
 * RE_PROJECT_ROOT é definido em public/index.php antes deste require.
 */
if (!defined('RE_PROJECT_ROOT')) {
    throw new RuntimeException('RE_PROJECT_ROOT não definido.');
}

if (session_status() === PHP_SESSION_NONE) {
    session_start([
        'cookie_httponly' => true,
        'cookie_samesite' => 'Lax',
    ]);
}

function re_h(?string $s): string
{
    return htmlspecialchars((string) $s, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
}

function re_storage_path(string $sub = ''): string
{
    $base = RE_PROJECT_ROOT . DIRECTORY_SEPARATOR . 'storage';
    return $sub === '' ? $base : $base . DIRECTORY_SEPARATOR . str_replace(['/', '\\'], DIRECTORY_SEPARATOR, $sub);
}

function re_public_path(string $sub = ''): string
{
    $base = RE_PROJECT_ROOT . DIRECTORY_SEPARATOR . 'public';
    return $sub === '' ? $base : $base . DIRECTORY_SEPARATOR . str_replace(['/', '\\'], DIRECTORY_SEPARATOR, $sub);
}
