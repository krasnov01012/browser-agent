# Запускает Chrome с портом отладки и отдельным персистентным профилем.
# Профиль живёт между запусками — логинитесь вручную один раз.
#
#   ./launch_chrome.ps1              порт слушает только 127.0.0.1
#   ./launch_chrome.ps1 -ForDocker   порт открыт наружу; для Docker Desktop
#                                    НЕ нужен — он проксирует host.docker.internal
#                                    в loopback (docs/ADR.md ADR-026)
#
# Файл сохранён в UTF-8 С BOM и должен таким остаться: Windows PowerShell 5.1
# без BOM читает .ps1 как ANSI, русские строки распадаются на мусор, и скрипт
# падает разбором ещё до первой команды (docs/ADR.md ADR-033).

param(
    [switch]$ForDocker
)

$ErrorActionPreference = "Stop"

$Port = 9222
$ProfileDir = Join-Path $env:LOCALAPPDATA "browser-agent-profile"

$Candidates = @(
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
    "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
)

$Chrome = $Candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $Chrome) {
    throw "Chrome не найден. Проверьте пути в scripts/launch_chrome.ps1"
}

# Уже слушает? Адрес именно 127.0.0.1: Chrome держит отладочный порт только
# на IPv4, а localhost на Windows резолвится сначала в ::1 — проверка через
# него всегда уходила бы в catch, и скрипт поднимал бы второй Chrome поверх
# работающего.
$listening = $false
try {
    $null = Invoke-WebRequest "http://127.0.0.1:$Port/json/version" -TimeoutSec 2 -UseBasicParsing
    $listening = $true
} catch { }

if ($listening) {
    Write-Host "Chrome уже слушает порт $Port" -ForegroundColor Green
    exit 0
}

if (-not (Test-Path $ProfileDir)) {
    New-Item -ItemType Directory -Path $ProfileDir | Out-Null
}

# Не $Args: так называется автоматическая переменная PowerShell.
$ChromeArgs = @(
    "--remote-debugging-port=$Port",
    "--user-data-dir=$ProfileDir",
    "--no-first-run",
    "--no-default-browser-check"
)

if ($ForDocker) {
    # Из контейнера localhost — это сам контейнер, поэтому порт нужно открыть
    # наружу. Делайте это только в доверенной сети: любой, кто дотянется
    # до порта, получит полный контроль над браузером.
    $ChromeArgs += "--remote-debugging-address=0.0.0.0"
    $ChromeArgs += "--remote-allow-origins=*"
}

Write-Host "Запускаю Chrome"
Write-Host "  профиль: $ProfileDir"
Write-Host "  порт:    $Port$(if ($ForDocker) { ' (открыт наружу)' })"

# Start-Process, а не `& $Chrome`: оператор вызова ждёт завершения процесса,
# а браузерный процесс Chrome живёт, пока открыто окно. Скрипт из-за этого
# не возвращал управление до закрытия браузера, и обёртка start_browser.ps1
# никогда не доходила до проверки порта.
Start-Process -FilePath $Chrome -ArgumentList ($ChromeArgs + "about:blank")

Write-Host ""
Write-Host "Готово. Залогиньтесь вручную в нужные сервисы — профиль сохранится." -ForegroundColor Green
Write-Host "Проверка: http://127.0.0.1:$Port/json/version"
