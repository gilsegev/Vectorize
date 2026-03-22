param(
  [string]$EnvFile = "backend/.env"
)

if (!(Test-Path $EnvFile)) {
  Write-Error "Env file not found: $EnvFile"
  exit 1
}

$lines = Get-Content $EnvFile
$updated = @()
$active = "legacy"

foreach ($line in $lines) {
  if ($line -match '^ACTIVE_TUNED_PROMPT_PROFILE=') {
    $active = $line.Split('=')[1]
    continue
  }
  $updated += $line
}

$updated = $updated | Where-Object { $_ -notmatch '^ENABLE_TUNED_PROMPTS=' -and $_ -notmatch '^ENABLE_TUNED_CLEANUP=' -and $_ -notmatch '^ENABLE_AUTO_SELECTION=' -and $_ -notmatch '^ACTIVE_TUNED_PROMPT_PROFILE=' -and $_ -notmatch '^PREVIOUS_TUNED_PROMPT_PROFILE=' }
$updated += "ENABLE_TUNED_PROMPTS=false"
$updated += "ENABLE_TUNED_CLEANUP=false"
$updated += "ENABLE_AUTO_SELECTION=false"
$updated += "ACTIVE_TUNED_PROMPT_PROFILE=legacy"
$updated += "PREVIOUS_TUNED_PROMPT_PROFILE=$active"

Set-Content -Path $EnvFile -Value $updated -Encoding utf8
Write-Output "Rollback defaults applied in $EnvFile"
