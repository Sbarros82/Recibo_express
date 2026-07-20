<?php

declare(strict_types=1);

namespace ReciboExpress;

final class ConfigRepository
{
    private string $path;

    public function __construct()
    {
        $this->path = re_storage_path('config_empresa.json');
    }

    /** @return array{nome_empresa:string,endereco:string,telefone:string,email:string,site:string} */
    public function load(): array
    {
        $defaults = [
            'nome_empresa' => 'MASTEROP',
            'endereco' => 'Av. Gov. Osman Loureiro, 49 - 403 - Mangabeiras, Maceió - AL, 57037-630',
            'telefone' => '(82) 3216-2000',
            'email' => '',
            'site' => '',
        ];

        if (!is_file($this->path)) {
            return $defaults;
        }

        try {
            $json = file_get_contents($this->path);
            if ($json === false) {
                return $defaults;
            }
            $data = json_decode($json, true, 512, JSON_THROW_ON_ERROR);
            if (!is_array($data)) {
                return $defaults;
            }

            return array_merge($defaults, array_intersect_key($data, $defaults));
        } catch (\Throwable) {
            return $defaults;
        }
    }

    /** @param array{nome_empresa?:string,endereco?:string,telefone?:string,email?:string,site?:string} $data */
    public function save(array $data): void
    {
        $current = $this->load();
        $merged = array_merge($current, $data);
        $dir = dirname($this->path);
        if (!is_dir($dir)) {
            mkdir($dir, 0755, true);
        }
        file_put_contents(
            $this->path,
            json_encode($merged, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT) . "\n",
            LOCK_EX
        );
    }
}
