# Поднимает Chrome для агента и дожидается, пока порт отладки реально отвечает.
#
#   ./start_browser.ps1
#
# Чем отличается от launch_chrome.ps1: тот запускает процесс и сразу отдаёт
# управление — в этот момент порт ещё не слушает. Здесь запуск и готовность
# разведены: скрипт не завершится, пока Chrome не ответит на /json/version.
# Для записи это существенно: агент, стартовавший на полсекунды раньше
# браузера, падает с BrowserUnavailable уже на камеру.
#
# Файл сохранён в UTF-8 С BOM и должен таким остаться: Windows PowerShell 5.1
# без BOM читает .ps1 как ANSI, и кириллица разваливается ещё до первой
# команды (docs/DECISIONS.md ADR-033).

$ErrorActionPreference = "Stop"

$Port = 9222
# 127.0.0.1, а не localhost: Chrome держит отладочный порт только на IPv4,
# а localhost на Windows резолвится сначала в ::1 (docs/DECISIONS.md ADR-004).
$Origin = "http://127.0.0.1:$Port"

& (Join-Path $PSScriptRoot "launch_chrome.ps1")

Write-Host ""
Write-Host "Жду порт отладки" -NoNewline

$version = $null
foreach ($attempt in 1..30) {
    try {
        $version = Invoke-RestMethod "$Origin/json/version" -TimeoutSec 2
        break
    } catch {
        Start-Sleep -Milliseconds 500
        Write-Host "." -NoNewline
    }
}
Write-Host ""

if (-not $version) {
    Write-Host ""
    Write-Host "Chrome не поднял порт $Port за 15 секунд." -ForegroundColor Red
    Write-Host "Частая причина: окно с этим же профилем уже открыто, но было"
    Write-Host "запущено без --remote-debugging-port. Порт задаётся только при"
    Write-Host "старте процесса — закройте окно и запустите скрипт заново."
    exit 1
}

$pages = @(Invoke-RestMethod "$Origin/json/list" | Where-Object { $_.type -eq "page" })

Write-Host ""
Write-Host "Браузер готов." -ForegroundColor Green
Write-Host "  $($version.Browser)"
Write-Host "  вкладок: $($pages.Count)"
Write-Host ""
Write-Host "Залогиньтесь вручную в нужные сервисы — профиль между запусками сохраняется."
Write-Host "Дальше: scripts\start_agent.ps1"
