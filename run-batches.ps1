# Сторож очереди батчей: ведёт списки тем по порядку, пока все не соберутся.
#
# Зачем не разовый запуск:
#   1. Компьютер выключают — вместе с ним умирает и сборка. Задача в
#      планировщике повторяется каждые 15 минут и поднимает работу заново.
#   2. На этой машине процесс сборки изредка исчезает молча, рушится сам
#      интерпретатор. Внутренний цикл ловит и это.
#
# Что осталось собрать, спрашиваем у pending.py: он сверяет темы по именам
# готовых файлов. Считать сами файлы нельзя — после перезапуска тема может
# собраться дважды, и счётчик покажет полный комплект там, где его нет.
# Именно на этом сторож обманулся 12.08: 50 файлов при 44 собранных темах.
#
# Файл обязан лежать в UTF-8 с BOM: иначе PowerShell 5.1 прочтёт его как ANSI
# и пути с кириллицей превратятся в мусор.

$root = "C:\Users\veron\Desktop\shorts-factory"
$python = "$root\.venv\Scripts\python.exe"
$env:PYTHONIOENCODING = "utf-8"

# Порядок важен: параллельно гнать нельзя, всё упирается в скорость стоков,
# два батча просто поделят один канал пополам.
$jobs = @(
    @{
        Name    = "космос"
        Prompts = "prompts/space.txt"
        Dir     = "out/videos/факты про космос"
    },
    @{
        Name    = "заработок на ИИ"
        Prompts = "prompts/ai-money.txt"
        Dir     = "out/videos/как легко заработать деньги с помощью искусственного интеллекта"
    }
)

function Note($text) {
    "{0:dd.MM HH:mm:ss}  {1}" -f (Get-Date), $text |
        Out-File "$root\space-supervisor.log" -Append -Encoding utf8
}

function Get-Pending($job) {
    # Возвращает число несобранных тем и попутно пишет их в .pending.txt
    $n = & $python "$root\pending.py" $job.Prompts $job.Dir 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $n) { return -1 }
    return [int]($n | Select-Object -Last 1)
}

$allDone = $true

foreach ($job in $jobs) {
    $outDir = Join-Path $root $job.Dir
    if (-not (Test-Path $outDir)) { New-Item -ItemType Directory $outDir -Force | Out-Null }

    $env:VIDEO_DIR = $job.Dir
    $pendingFile = [IO.Path]::ChangeExtension($job.Prompts, ".pending.txt")
    $failedFile = Join-Path $root ([IO.Path]::ChangeExtension($job.Prompts, ".failed.txt"))
    $run = 0

    while ($true) {
        $left = Get-Pending $job
        if ($left -lt 0) { Note "$($job.Name): не смог посчитать оставшееся"; $allDone = $false; break }
        if ($left -eq 0) { Note "$($job.Name): собраны все темы"; break }

        $run++
        Note "$($job.Name): попытка $run, осталось тем: $left"

        $proc = Start-Process -FilePath $python `
            -ArgumentList "batch.py", "--file", $pendingFile `
            -WorkingDirectory $root `
            -RedirectStandardOutput "$root\batch-run$run-$($job.Name.Replace(' ', '-')).log" `
            -RedirectStandardError "$root\batch-run$run-$($job.Name.Replace(' ', '-')).err" `
            -WindowStyle Hidden -PassThru
        $proc.WaitForExit()

        $after = Get-Pending $job
        Note "$($job.Name): попытка $run закончилась, осталось $after"

        if ($after -ge $left) {
            # Ни одной темы за попытку — первая в очереди не поддаётся,
            # откладываем её и идём дальше, иначе застрянем навсегда.
            $stuck = (Get-Content (Join-Path $root $pendingFile) -Encoding UTF8 |
                Select-Object -First 1)
            if ($stuck) {
                $stuck | Out-File $failedFile -Append -Encoding utf8
                Note "$($job.Name): тема не далась, откладываю — $stuck"
            }
            Start-Sleep -Seconds 10
        }
    }

    if ((Get-Pending $job) -ne 0) { $allDone = $false }
}

# Задача повторяется каждые 15 минут ради живучести. Когда всё собрано, снимаем
# её — иначе она будет впустую будить python до скончания века.
if ($allDone) {
    Note "все очереди пройдены, задача из планировщика удалена"
    schtasks /delete /tn "ShortsFactorySpace" /f | Out-Null
}
