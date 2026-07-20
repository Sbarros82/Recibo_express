<?php
/** @var array $config */
/** @var array $flashes */
?>
<div class="card shadow-sm border-0 mb-4">
    <div class="card-header bg-dark text-white rounded-top">
        <h5 class="mb-0"><i class="fas fa-building me-2"></i>Dados da empresa</h5>
    </div>
    <div class="card-body">
        <?php foreach ($flashes as $f): ?>
            <div class="alert alert-<?= $f['type'] === 'success' ? 'success' : 'danger' ?> alert-dismissible fade show" role="alert">
                <?= re_h($f['message']) ?>
                <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
            </div>
        <?php endforeach; ?>

        <form method="post" action="index.php?r=salvar_configuracoes" class="mb-4">
            <div class="mb-3">
                <label class="form-label" for="nome_empresa">Nome da empresa</label>
                <input class="form-control" id="nome_empresa" name="nome_empresa" required
                       value="<?= re_h($config['nome_empresa']) ?>">
            </div>
            <div class="mb-3">
                <label class="form-label" for="telefone">Telefone</label>
                <input class="form-control" id="telefone" name="telefone" value="<?= re_h($config['telefone']) ?>">
            </div>
            <div class="mb-3">
                <label class="form-label" for="endereco">Endereço</label>
                <textarea class="form-control" id="endereco" name="endereco" rows="3" required><?= re_h($config['endereco']) ?></textarea>
            </div>
            <div class="mb-3">
                <label class="form-label" for="email">E-mail</label>
                <input type="email" class="form-control" id="email" name="email" value="<?= re_h($config['email']) ?>">
            </div>
            <div class="mb-3">
                <label class="form-label" for="site">Site</label>
                <input type="url" class="form-control" id="site" name="site" value="<?= re_h($config['site']) ?>">
            </div>
            <button type="submit" class="btn btn-primary"><i class="fas fa-save me-1"></i> Salvar</button>
        </form>

        <hr>

        <div class="row g-4">
            <div class="col-md-6">
                <h6 class="text-muted">Logo (PNG/JPG)</h6>
                <form method="post" action="index.php?r=upload_logo" enctype="multipart/form-data">
                    <input type="file" name="logo" accept=".png,.jpg,.jpeg,.gif" class="form-control mb-2" required>
                    <button type="submit" class="btn btn-outline-primary btn-sm">Enviar logo</button>
                </form>
            </div>
            <div class="col-md-6">
                <h6 class="text-muted">Imagem de fundo / timbrado</h6>
                <form method="post" action="index.php?r=upload_watermark" enctype="multipart/form-data">
                    <input type="file" name="watermark" accept=".png,.jpg,.jpeg,.gif" class="form-control mb-2" required>
                    <button type="submit" class="btn btn-outline-primary btn-sm">Enviar imagem</button>
                </form>
            </div>
        </div>
    </div>
</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/js/bootstrap.bundle.min.js"></script>
