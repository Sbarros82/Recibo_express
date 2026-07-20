<?php

declare(strict_types=1);

namespace ReciboExpress\Controllers;

use ReciboExpress\View;

final class HomeController
{
    public function index(): string
    {
        $inner = View::render('home', []);

        return View::layout('Recibo Express', 'home', $inner);
    }
}
