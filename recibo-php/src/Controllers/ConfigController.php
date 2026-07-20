<?php

declare(strict_types=1);

namespace ReciboExpress\Controllers;

use ReciboExpress\ConfigRepository;
use ReciboExpress\Flash;
use ReciboExpress\View;

final class ConfigController
{
    private ConfigRepository $config;

    public function __construct()
    {
        $this->config = new ConfigRepository();
    }

    public function show(): string
    {
        $config = $this->config->load();
        $inner = View::render('configuracoes', [
            'config' => $config,
            'flashes' => Flash::pull(),
        ]);

        return View::layout('Configurações — Recibo Express', 'configuracoes', $inner);
    }

    public function save(): string
    {
        if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
            header('Location: index.php?r=configuracoes', true, 302);
            exit;
        }

        try {
            $this->config->save([
                'nome_empresa' => (string) ($_POST['nome_empresa'] ?? ''),
                'endereco' => (string) ($_POST['endereco'] ?? ''),
                'telefone' => (string) ($_POST['telefone'] ?? ''),
                'email' => (string) ($_POST['email'] ?? ''),
                'site' => (string) ($_POST['site'] ?? ''),
            ]);
            Flash::add('success', 'Configurações salvas com sucesso!');
        } catch (\Throwable $e) {
            Flash::add('error', 'Erro ao salvar: ' . $e->getMessage());
        }

        header('Location: index.php?r=configuracoes', true, 302);
        exit;
    }

    public function uploadLogo(): string
    {
        return $this->handleImageUpload('logo', 'logo_empresa.png', 'Logo salva com sucesso!');
    }

    public function uploadWatermark(): string
    {
        return $this->handleImageUpload('watermark', 'watermark_empresa.png', 'Imagem de fundo salva com sucesso!');
    }

    private function handleImageUpload(string $field, string $targetName, string $successMsg): string
    {
        if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') {
            header('Location: index.php?r=configuracoes', true, 302);
            exit;
        }

        if (!isset($_FILES[$field]) || !is_array($_FILES[$field]) || ($_FILES[$field]['error'] ?? UPLOAD_ERR_NO_FILE) === UPLOAD_ERR_NO_FILE) {
            Flash::add('error', 'Nenhum arquivo selecionado');
            header('Location: index.php?r=configuracoes', true, 302);
            exit;
        }

        $f = $_FILES[$field];
        if (($f['error'] ?? UPLOAD_ERR_OK) !== UPLOAD_ERR_OK) {
            Flash::add('error', 'Erro no upload.');
            header('Location: index.php?r=configuracoes', true, 302);
            exit;
        }

        $orig = (string) ($f['name'] ?? '');
        $ext = strtolower(pathinfo($orig, PATHINFO_EXTENSION));
        $allowed = ['png', 'jpg', 'jpeg', 'gif'];
        if (!in_array($ext, $allowed, true)) {
            Flash::add('error', 'Formato não permitido. Use PNG, JPG ou JPEG.');
            header('Location: index.php?r=configuracoes', true, 302);
            exit;
        }

        $destDir = re_public_path('static/uploads');
        if (!is_dir($destDir)) {
            mkdir($destDir, 0755, true);
        }
        $dest = $destDir . DIRECTORY_SEPARATOR . $targetName;
        if (!move_uploaded_file((string) $f['tmp_name'], $dest)) {
            Flash::add('error', 'Não foi possível guardar o ficheiro.');
            header('Location: index.php?r=configuracoes', true, 302);
            exit;
        }

        Flash::add('success', $successMsg);
        header('Location: index.php?r=configuracoes', true, 302);
        exit;
    }
}
