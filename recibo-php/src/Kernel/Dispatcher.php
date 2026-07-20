<?php

declare(strict_types=1);

namespace ReciboExpress\Kernel;

use ReciboExpress\Controllers\ConfigController;
use ReciboExpress\Controllers\HomeController;

final class Dispatcher
{
    public function run(): void
    {
        $route = preg_replace('/[^a-z0-9_]/i', '', (string) ($_GET['r'] ?? 'home'));
        $method = $_SERVER['REQUEST_METHOD'] ?? 'GET';

        $map = [
            'GET' => [
                'home' => [HomeController::class, 'index'],
                'configuracoes' => [ConfigController::class, 'show'],
            ],
            'POST' => [
                'salvar_configuracoes' => [ConfigController::class, 'save'],
                'upload_logo' => [ConfigController::class, 'uploadLogo'],
                'upload_watermark' => [ConfigController::class, 'uploadWatermark'],
            ],
        ];

        $handler = $map[$method][$route] ?? null;
        if ($handler === null) {
            http_response_code(404);
            echo '<h1>404</h1><p>Rota não encontrada.</p><p><a href="index.php?r=home">Início</a></p>';
            return;
        }

        [$class, $action] = $handler;
        $controller = new $class();
        echo $controller->$action();
    }
}
