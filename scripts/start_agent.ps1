# Запускает агента в диалоговом режиме — то, что видно на записи.
#
#   ./start_agent.ps1                             диалог в терминале
#   ./start_agent.ps1 -Task "..."                 одна задача и выход
#   ./start_agent.ps1 -Rehearsal                  репетиция: спрашивает перед
#                                                 необратимым, память не пишет
#   ./start_agent.ps1 -Prompt system.baseline.md  другая редакция промпта
#
# Всё, что способно сорвать дубль, проверяется ДО того, как управление уйдёт
# агенту: венв, .env, живой порт отладки. Стектрейс на камеру стоит дороже
# трёх секунд проверок.
#
# Файл сохранён в UTF-8 С BOM — см. шапку start_browser.ps1 и ADR-033.

param(
    [string]$Task,
    [string]$Prompt,
    [switch]$Rehearsal,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Passthrough
)

$ErrorActionPreference = "Stop"

$Root = Split-Path $PSScriptRoot -Parent
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$EnvFile = Join-Path $Root ".env"

function Fail([string]$message, [string]$hint) {
    Write-Host ""
    Write-Host $message -ForegroundColor Red
    if ($hint) { Write-Host $hint }
    exit 1
}

if (-not (Test-Path $Python)) {
    Fail "Виртуальное окружение не найдено: $Python" `
         "Создайте его и поставьте проект: python -m venv .venv; .venv\Scripts\pip install -e ."
}
if (-not (Test-Path $EnvFile)) {
    Fail "Нет файла .env" "Скопируйте .env.example в .env и впишите ключ провайдера."
}

# Читаем из .env только то, что показываем в шапке. Ключи не запрашиваются
# и в вывод не попадают — файл открыт в терминале, который пишется на видео.
function Get-EnvValue([string]$name, [string]$fallback) {
    $hit = Select-String -Path $EnvFile -Pattern "^\s*$name\s*=" -Encoding utf8 | Select-Object -First 1
    if (-not $hit) { return $fallback }
    $value = ($hit.Line -split "=", 2)[1].Trim()
    if ($value) { return $value } else { return $fallback }
}

$provider = Get-EnvValue "LLM_PROVIDER" "zai"
$navigator = Get-EnvValue "MODEL_NAVIGATOR" "(по умолчанию)"
$maxSteps = Get-EnvValue "MAX_STEPS" "60"
$cdpUrl = Get-EnvValue "CDP_URL" "http://127.0.0.1:9222"
$confirm = (Get-EnvValue "CONFIRM_DESTRUCTIVE" "false").ToLower() -in @("1", "true", "yes", "on")
$memory = (Get-EnvValue "PERSIST_MEMORY" "true").ToLower() -in @("1", "true", "yes", "on")

if ($Rehearsal) {
    $confirm = $true
    $memory = $false
}

# Браузер поднимается отдельно и живёт дольше агента: у него персистентный
# профиль с ручными логинами, перезапускать его на каждую задачу нельзя.
try {
    $null = Invoke-RestMethod "$cdpUrl/json/version" -TimeoutSec 3
} catch {
    Fail "Chrome не отвечает на $cdpUrl" "Сначала запустите scripts\start_browser.ps1"
}

$promptFile = if ($Prompt) { $Prompt } else { "system.md" }

Write-Host ""
Write-Host "── агент ──────────────────────────────" -ForegroundColor DarkGray
Write-Host ("  провайдер     {0}" -f $provider)
Write-Host ("  навигатор     {0}" -f $navigator)
Write-Host ("  промпт        {0}" -f $promptFile)
Write-Host ("  шагов максим. {0}" -f $maxSteps)
Write-Host ("  подтверждения {0}" -f $(if ($confirm) { "спрашивает" } else { "не спрашивает" }))
Write-Host ("  память        {0}" -f $(if ($memory) { "пишет" } else { "не пишет" }))
Write-Host "───────────────────────────────────────" -ForegroundColor DarkGray

if (-not $confirm) {
    Write-Host "Боевой режим: необратимые действия выполняются без вопроса." -ForegroundColor Yellow
}
Write-Host ""

# Кириллица в stdout Python на Windows иначе падает в cp1251.
$env:PYTHONIOENCODING = "utf-8"
if ($Prompt) { $env:SYSTEM_PROMPT_FILE = $Prompt }

$agentArgs = @()
if ($Task) { $agentArgs += @("--task", $Task) } else { $agentArgs += "--cli" }
$agentArgs += "-v"
if ($Rehearsal) { $agentArgs += @("--confirm-destructive", "--no-memory") }
if ($Passthrough) { $agentArgs += $Passthrough }

Push-Location $Root
try {
    & $Python -m agent.main @agentArgs
    $code = $LASTEXITCODE
} finally {
    Pop-Location
}

exit $code
