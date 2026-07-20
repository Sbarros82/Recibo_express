<?php

declare(strict_types=1);

/**
 * Autoload PSR-4 mínimo (ReciboExpress\) — não exige Composer no servidor.
 */
spl_autoload_register(static function (string $class): void {
    $prefix = 'ReciboExpress\\';
    $baseDir = RE_PROJECT_ROOT . DIRECTORY_SEPARATOR . 'src' . DIRECTORY_SEPARATOR;

    if (!str_starts_with($class, $prefix)) {
        return;
    }

    $relative = substr($class, strlen($prefix));
    $file = $baseDir . str_replace('\\', DIRECTORY_SEPARATOR, $relative) . '.php';

    if (is_file($file)) {
        require $file;
    }
});
