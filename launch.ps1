# Запуск фабрики роликов с ярлыка: поднять сервер и открыть окно в браузере.
#
# Файл обязан лежать в UTF-8 с BOM. Без BOM Windows PowerShell 5.1 читает его
# в кодировке ANSI, кириллица превращается в мусор и падает разбор скрипта.

$port = 8420
$url = "http://127.0.0.1:$port/"
$log = Join-Path $PSScriptRoot "server.log"
$errLog = Join-Path $PSScriptRoot "server.err"

function Test-Ready {
    $client = New-Object Net.Sockets.TcpClient
    try {
        $client.Connect("127.0.0.1", $port)
        $client.Close()
        return $true
    } catch {
        return $false
    }
}

function Show-Failure {
    Write-Host ""
    Write-Host "  Сервер не запустился." -ForegroundColor Red
    if (Test-Path $errLog) {
        Write-Host "  Последние строки из server.err:"
        Get-Content $errLog -Tail 12 | ForEach-Object { Write-Host "    $_" }
    }
    Write-Host ""
    Read-Host "  Enter, чтобы закрыть"
}

# Фабрика уже работает — второй сервер не нужен, просто открываем окно.
if (Test-Ready) {
    Start-Process $url
    exit 0
}

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Host ""
    Write-Host "  Рядом с этим файлом нет окружения .venv" -ForegroundColor Red
    Write-Host "  Ожидался путь: $python"
    Write-Host ""
    Read-Host "  Enter, чтобы закрыть"
    exit 1
}

Write-Host ""
Write-Host "  Запускаю фабрику роликов." -ForegroundColor Yellow
Write-Host "  Первый запуск занимает около минуты: грузится модель озвучки."
Write-Host "  Браузер откроется сам, это окно можно не трогать."
Write-Host ""

# Три попытки: на этой машине процесс изредка не рождается вовсе — рушится сам
# интерпретатор, до кода дело не доходит. Со второго раза стартует.
foreach ($attempt in 1..3) {
    # Вывод сервера уходит в файлы, иначе причина падения исчезает вместе с окном.
    $server = Start-Process -FilePath $python `
        -ArgumentList "-m", "uvicorn", "app.web.api:app", "--host", "127.0.0.1", "--port", "$port" `
        -WorkingDirectory $PSScriptRoot `
        -RedirectStandardOutput $log -RedirectStandardError $errLog `
        -WindowStyle Minimized -PassThru

    foreach ($i in 1..60) {
        Start-Sleep -Seconds 2
        if (Test-Ready) {
            Start-Process $url
            exit 0
        }
        # Процесс исчез, ждать больше нечего — либо пробуем снова, либо сдаёмся.
        if ($server.HasExited) { break }
    }

    if (-not $server.HasExited) {
        # Процесс жив, но порт молчит две минуты: повтор тут не поможет.
        Show-Failure
        exit 1
    }
    Write-Host "  Попытка $attempt сорвалась, запускаю снова." -ForegroundColor DarkYellow
}

Show-Failure
exit 1
