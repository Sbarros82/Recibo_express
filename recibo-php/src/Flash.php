<?php

declare(strict_types=1);

namespace ReciboExpress;

final class Flash
{
    private const KEY = '_flash_messages';

    public static function add(string $type, string $message): void
    {
        $_SESSION[self::KEY] ??= [];
        $_SESSION[self::KEY][] = ['type' => $type, 'message' => $message];
    }

    /** @return list<array{type:string,message:string}> */
    public static function pull(): array
    {
        $m = $_SESSION[self::KEY] ?? [];
        unset($_SESSION[self::KEY]);

        return $m;
    }
}
