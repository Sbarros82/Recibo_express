<?php

declare(strict_types=1);

namespace ReciboExpress;

final class View
{
    public static function render(string $name, array $data = []): string
    {
        $path = RE_PROJECT_ROOT . '/views/' . $name . '.php';
        if (!is_file($path)) {
            return '<p>View em falta: ' . re_h($name) . '</p>';
        }
        extract($data, EXTR_SKIP);
        ob_start();
        require $path;

        return (string) ob_get_clean();
    }

    /** Layout principal com sidebar */
    public static function layout(string $title, string $currentNav, string $innerHtml): string
    {
        return self::render('layout', [
            'title' => $title,
            'currentNav' => $currentNav,
            'innerHtml' => $innerHtml,
        ]);
    }
}
