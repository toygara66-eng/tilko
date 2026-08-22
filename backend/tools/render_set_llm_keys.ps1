# Nebius + yedek anahtarlarini Render tilko-api'ye yazar.
# 1) https://dashboard.render.com/u/settings#api-keys  -> API Key
# 2) backend/.env icine NEBIUS_API_KEY yaz
# 3) PowerShell:
#    $env:RENDER_API_KEY = "rnd_...."
#    .\backend\tools\render_set_llm_keys.ps1

$ErrorActionPreference = "Stop"
$token = $env:RENDER_API_KEY
if (-not $token) {
  Write-Host "RENDER_API_KEY yok. dashboard.render.com/u/settings#api-keys adresinden al."
  exit 1
}

$envFile = Join-Path $PSScriptRoot "..\.env"
$map = @{}
Get-Content $envFile | ForEach-Object {
  if ($_ -match '^\s*#' -or $_ -notmatch '=') { return }
  $k, $v = $_.Split('=', 2)
  $map[$k.Trim()] = $v.Trim()
}

$nebius = $map['NEBIUS_API_KEY']
$groq = $map['GROQ_API_KEY']
$cerebras = $map['CEREBRAS_API_KEY']
if (-not $nebius -and -not $groq -and -not $cerebras) {
  Write-Host "backend/.env icinde NEBIUS_API_KEY (veya Groq/Cerebras) dolu olmali."
  exit 1
}

$headers = @{ Authorization = "Bearer $token"; Accept = "application/json" }
$services = Invoke-RestMethod -Headers $headers -Uri "https://api.render.com/v1/services?limit=50"
$svc = $services | Where-Object { $_.service.name -eq "tilko-api" } | Select-Object -First 1
if (-not $svc) {
  Write-Host "tilko-api servisi bulunamadi."
  exit 1
}
$id = $svc.service.id
Write-Host "Servis: tilko-api ($id)"

function Set-Env([string]$key, [string]$value) {
  if (-not $value) { return }
  $body = @{ value = $value } | ConvertTo-Json
  Invoke-RestMethod -Method Put -Headers $headers -ContentType "application/json" `
    -Uri "https://api.render.com/v1/services/$id/env-vars/$key" -Body $body | Out-Null
  Write-Host "  set $key"
}

Set-Env "LLM_PROVIDER" "nebius"
Set-Env "LLM_FALLBACK" "cerebras"
Set-Env "NEBIUS_MODEL" "google/gemma-3-27b-it"
Set-Env "NEBIUS_BASE_URL" "https://api.tokenfactory.nebius.com/v1/"
Set-Env "CEREBRAS_MODEL" "gemma-4-31b"
Set-Env "GROQ_MODEL" "llama-3.1-8b-instant"
Set-Env "NEBIUS_API_KEY" $nebius
Set-Env "CEREBRAS_API_KEY" $cerebras
Set-Env "GROQ_API_KEY" $groq

$deploy = Invoke-RestMethod -Method Post -Headers $headers -ContentType "application/json" `
  -Uri "https://api.render.com/v1/services/$id/deploys" -Body '{"clearCache":"do_not_clear"}'
Write-Host "Deploy basladi: $($deploy.id)"
Write-Host "Bitti. Birkaç dakika sonra tilko.site yenile."
