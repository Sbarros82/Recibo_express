<?php
/** @var string $title */
/** @var string $currentNav */
/** @var string $innerHtml */
?>
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title><?= re_h($title) ?></title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <style>
        body { background: #f8fafc; font-family: 'Segoe UI', system-ui, sans-serif; }
        .sidebar { width: 280px; background: #1a202c; color: #fff; position: fixed; height: 100vh; left: 0; top: 0; z-index: 1000; overflow-y: auto; }
        .sidebar-header { padding: 1.5rem; border-bottom: 1px solid #2d3748; }
        .sidebar-header h1 { font-size: 1.25rem; margin: 0; }
        .sidebar-header p { font-size: 0.85rem; color: #a0aec0; margin: 0.25rem 0 0; }
        .nav-item { display: block; color: #a0aec0; padding: 0.65rem 1.25rem; text-decoration: none; border-left: 3px solid transparent; }
        .nav-item:hover { color: #fff; background: #2d3748; border-left-color: #4299e1; }
        .nav-item.active { color: #fff; background: #2d3748; border-left-color: #4299e1; }
        .nav-item i { margin-right: 0.5rem; width: 1.2rem; text-align: center; }
        .main-content { margin-left: 280px; padding: 1.5rem; min-height: 100vh; }
        .badge-soon { font-size: 0.65rem; vertical-align: middle; }
    </style>
</head>
<body>
<aside class="sidebar">
    <div class="sidebar-header">
        <h1>Recibo Express</h1>
        <p>PHP — migração</p>
    </div>
    <nav class="py-2">
        <a class="nav-item <?= $currentNav === 'home' ? 'active' : '' ?>" href="index.php?r=home"><i class="fas fa-home"></i> Início</a>
        <a class="nav-item <?= $currentNav === 'configuracoes' ? 'active' : '' ?>" href="index.php?r=configuracoes"><i class="fas fa-cog"></i> Configurações</a>
        <span class="nav-item text-muted"><i class="fas fa-file-pdf"></i> Prévia PDF <span class="badge bg-secondary badge-soon">em breve</span></span>
        <span class="nav-item text-muted"><i class="fas fa-receipt"></i> Recibo avulso <span class="badge bg-secondary badge-soon">em breve</span></span>
        <span class="nav-item text-muted"><i class="fas fa-bus"></i> Vale transporte <span class="badge bg-secondary badge-soon">em breve</span></span>
    </nav>
</aside>
<div class="main-content">
    <?= $innerHtml ?>
</div>
</body>
</html>
