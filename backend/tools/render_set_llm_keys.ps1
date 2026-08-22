# En ucuz LLM yolu: Cerebras + Groq anahtarlarini Render tilko-api'ye yazar.
# 1) https://dashboard.render.com/u/settings#api-keys  -> API Key olustur
# 2) PowerShell:
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

$groq = $map['GROQ_API_KEY']
$cerebras = $map['CEREBRAS_API_KEY']
if (-not $groq -or -not $cerebras) {
  Write-Host "backend/.env icinde GROQ_API_KEY ve CEREBRAS_API_KEY dolu olmali."
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
  $body = @{ value = $value } | ConvertTo-Json
  Invoke-RestMethod -Method Put -Headers $headers -ContentType "application/json" `
    -Uri "https://api.render.com/v1/services/$id/env-vars/$key" -Body $body | Out-Null
  Write-Host "  set $key"
}

Set-Env "LLM_PROVIDER" "cerebras"
Set-Env "LLM_FALLBACK" "groq"
Set-Env "CEREBRAS_MODEL" "gemma-4-31b"
Set-Env "GROQ_MODEL" "llama-3.1-8b-instant"
Set-Env "CEREBRAS_API_KEY" $cerebras
Set-Env "GROQ_API_KEY" $groq

$deploy = Invoke-RestMethod -Method Post -Headers $headers -ContentType "application/json" `
  -Uri "https://api.render.com/v1/services/$id/deploys" -Body '{"clearCache":"do_not_clear"}'
Write-Host "Deploy basladi: $($deploy.id)"
Write-Host "Bitti. Birkaç dakika sonra tilko.site yenile."
