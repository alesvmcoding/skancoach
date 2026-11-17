$ErrorActionPreference = "Stop"

$projectDir = $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($projectDir)) {
    throw 'Execute o arquivo setup_neon.ps1 com & e o caminho completo, em vez de colar seu conteúdo no terminal.'
}
if (-not (Test-Path -LiteralPath (Join-Path $projectDir 'backend\database.py') -PathType Leaf)) {
    throw 'Coloque setup_neon.ps1 na pasta raiz do Skan Coach, que contém as pastas backend, frontend e data.'
}
$nodeDir = Join-Path $env:ProgramFiles "nodejs"
$nodeExe = Join-Path $nodeDir "node.exe"
$npmCmd = Join-Path $nodeDir "npm.cmd"
$cliDir = Join-Path $projectDir ".neon-cli"
$cliBin = Join-Path $cliDir "node_modules\.bin"
$neonCmd = Join-Path $cliBin "neon.cmd"
$privateCache = Join-Path $projectDir ".npm-cache"
$safeLogDir = Join-Path $projectDir ".neon-setup-logs"

if (-not (Test-Path $nodeExe) -or -not (Test-Path $npmCmd)) {
    throw "Não encontrei Node.js e npm em $nodeDir. Confirme a instalação do Node.js LTS."
}

New-Item -ItemType Directory -Force -Path $safeLogDir | Out-Null
New-Item -ItemType Directory -Force -Path $cliDir | Out-Null
$env:PATH = "$nodeDir;$cliBin;$env:PATH"
$env:npm_config_cache = $privateCache

if (-not (Test-Path $neonCmd)) {
    Write-Host "Instalando o CLI do Neon localmente para este projeto..."
    try {
        $ErrorActionPreference = "Continue"
        & $npmCmd install --prefix $cliDir neon@latest --no-audit --no-fund *> (Join-Path $safeLogDir "install.log")
    } finally {
        $ErrorActionPreference = "Stop"
    }
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $neonCmd)) {
        throw "A instalação do CLI Neon falhou (código $LASTEXITCODE). Nenhuma saída com valores de conexão foi exibida."
    }
}

Push-Location -LiteralPath $projectDir
try {
    Write-Host "Preparando a conexão com o projeto Neon..."
    try {
        $ErrorActionPreference = "Continue"
        & $neonCmd init -y --org-id org-holy-smoke-90784000 --project-id misty-truth-09156766 --branch production --services postgres *> (Join-Path $safeLogDir "init.log")
    } finally {
        $ErrorActionPreference = "Stop"
    }
    if ($LASTEXITCODE -ne 0) {
        throw "A inicialização do Neon falhou (código $LASTEXITCODE). Nenhum segredo foi exibido."
    }

    Write-Host "Gerando as variáveis locais de conexão..."
    try {
        $ErrorActionPreference = "Continue"
        & $neonCmd deploy *> (Join-Path $safeLogDir "deploy.log")
    } finally {
        $ErrorActionPreference = "Stop"
    }
    if ($LASTEXITCODE -ne 0) {
        throw "O deploy do Neon falhou (código $LASTEXITCODE). Nenhum segredo foi exibido."
    }
} finally {
    Pop-Location
}

$envFile = Join-Path $projectDir ".env.local"
if (-not (Test-Path $envFile)) {
    throw "O Neon CLI terminou, mas não encontrei .env.local na pasta do projeto. Não exibi nenhuma saída do CLI."
}

$keys = Get-Content -LiteralPath $envFile | ForEach-Object {
    if ($_ -match '^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=') { $Matches[1] }
} | Sort-Object -Unique
Write-Host ".env.local criado. Nomes das variáveis encontradas (valores ocultos):"
$keys | ForEach-Object { Write-Host " - $_" }
Write-Host "O arquivo está excluído do Git. Não compartilhe nem publique esse arquivo."
