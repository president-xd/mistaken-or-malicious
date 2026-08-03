# Runs the three structurally distinct mesh scenarios concurrently.
# Each scenario runs seven agents concurrently, allowing up to 21 API requests
# in flight. Temporary API failures are retried automatically.

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot "venv\Scripts\python.exe"
$results = Join-Path $projectRoot "results"
$scenarioLogs = Join-Path $results "scenario-logs"
$maxConcurrentScenarios = 3
$maxAttempts = 3

if (-not (Test-Path -LiteralPath $python)) {
    throw "Project Python was not found at: $python"
}

New-Item -ItemType Directory -Path $results -Force | Out-Null
New-Item -ItemType Directory -Path $scenarioLogs -Force | Out-Null

$pending = [System.Collections.Generic.Queue[System.IO.FileInfo]]::new()
$configs = Get-ChildItem -LiteralPath $PSScriptRoot -Filter "mesh_*.yaml" |
    Sort-Object Name

if ($configs.Count -ne 3) {
    throw "Expected exactly three mesh configurations, but found $($configs.Count)."
}

foreach ($config in $configs) {
    $result = Join-Path $results ($config.BaseName + ".json")
    if (Test-Path -LiteralPath $result) {
        Write-Host "[SKIP] $($config.Name) - result already exists"
    }
    else {
        $pending.Enqueue($config)
    }
}

$active = @{}
$attempts = @{}

try {
    while ($pending.Count -gt 0 -or $active.Count -gt 0) {
        while ($pending.Count -gt 0 -and
               $active.Count -lt $maxConcurrentScenarios) {
            $config = $pending.Dequeue()
            if (-not $attempts.ContainsKey($config.FullName)) {
                $attempts[$config.FullName] = 0
            }
            $attempts[$config.FullName] += 1
            $stdout = Join-Path $scenarioLogs ($config.BaseName + ".log")
            $stderr = Join-Path $scenarioLogs ($config.BaseName + ".err.log")

            $process = Start-Process -FilePath $python -ArgumentList @(
                "-m", "p2p", $config.FullName, "--result", "json"
            ) -WorkingDirectory $projectRoot -RedirectStandardOutput $stdout -RedirectStandardError $stderr -WindowStyle Hidden -PassThru

            $active[$process.Id] = [PSCustomObject]@{
                Process = $process
                Config = $config
                Stdout = $stdout
                Stderr = $stderr
            }
            Write-Host "[RUN ] $($config.Name) attempt $($attempts[$config.FullName]) (PID $($process.Id))"
        }

        Start-Sleep -Seconds 1

        foreach ($id in @($active.Keys)) {
            $item = $active[$id]
            $item.Process.Refresh()
            if (-not $item.Process.HasExited) {
                continue
            }

            if ($item.Process.ExitCode -ne 0) {
                $details = ""
                if (Test-Path -LiteralPath $item.Stderr) {
                    $details = Get-Content -LiteralPath $item.Stderr -Raw
                }
                $temporary = $details -match "APITimeoutError|Request timed out|RateLimitError|429|APIConnectionError"
                if ($temporary -and
                    $attempts[$item.Config.FullName] -lt $maxAttempts) {
                    Write-Host "[RETRY] $($item.Config.Name) after a temporary API failure"
                    $active.Remove($id)
                    $pending.Enqueue($item.Config)
                    continue
                }
                if ($details) {
                    Write-Error $details
                }
                throw "Experiment failed: $($item.Config.Name). See $($item.Stderr)"
            }

            Write-Host "[DONE] $($item.Config.Name)"
            $active.Remove($id)
        }
    }
}
catch {
    foreach ($item in $active.Values) {
        if (-not $item.Process.HasExited) {
            Stop-Process -Id $item.Process.Id -Force -ErrorAction SilentlyContinue
        }
    }
    throw
}

Write-Host "All three mesh scenarios are complete. Results are in: $results"

