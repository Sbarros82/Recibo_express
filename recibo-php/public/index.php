<?php

declare(strict_types=1);

define('RE_PROJECT_ROOT', dirname(__DIR__));

$autoload = RE_PROJECT_ROOT . '/vendor/autoload.php';
if (is_file($autoload)) {
    require $autoload;
} else {
    require RE_PROJECT_ROOT . '/src/autoload.php';
}

require RE_PROJECT_ROOT . '/bootstrap.php';

foreach ([
    re_storage_path(''),
    re_storage_path('cache'),
    re_public_path('static/uploads'),
    re_public_path('static/recibos'),
] as $p) {
    if (!is_dir($p)) {
        mkdir($p, 0755, true);
    }
}

use ReciboExpress\Kernel\Dispatcher;

(new Dispatcher())->run();
