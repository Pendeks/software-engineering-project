param(
  [string]$SubscriptionId = '8778f6f4-61df-4a9f-bd67-b02f02b1ba67',
  [string]$ResourceGroup = 'rg-flowdesk-demo',
  [string]$AppName = 'flowdesk-demo-399203'
)

$ErrorActionPreference = 'Stop'
$azCommand = Get-Command az -ErrorAction SilentlyContinue
if ($azCommand) {
  $az = $azCommand.Source
} else {
  $az = Join-Path $env:ProgramFiles 'Microsoft SDKs\Azure\CLI2\wbin\az.cmd'
  if (-not (Test-Path -LiteralPath $az)) {
    throw 'Azure CLI was not found on PATH or in its standard Windows installation folder.'
  }
}
$projectRoot = $PSScriptRoot
$stagePath = Join-Path ([System.IO.Path]::GetTempPath()) ('flowdesk-deploy-' + [guid]::NewGuid())
$zipPath = "$stagePath.zip"

function Invoke-Az {
  param([string[]]$Arguments)

  & $script:az @Arguments | Out-Null
  if ($LASTEXITCODE -ne 0) {
    throw "Azure CLI failed with exit code $LASTEXITCODE."
  }
}

try {
  Invoke-Az -Arguments @('account', 'set', '--subscription', $SubscriptionId)
  Invoke-Az -Arguments @(
    'webapp', 'show',
    '--name', $AppName,
    '--resource-group', $ResourceGroup,
    '--subscription', $SubscriptionId,
    '--query', 'name',
    '-o', 'tsv'
  )

  & npm --prefix $projectRoot run build
  if ($LASTEXITCODE -ne 0) {
    throw "FlowDesk build failed with exit code $LASTEXITCODE."
  }

  New-Item -ItemType Directory -Path $stagePath | Out-Null
  Copy-Item -LiteralPath (Join-Path $projectRoot 'package.json') -Destination $stagePath
  Copy-Item -LiteralPath (Join-Path $projectRoot 'package-lock.json') -Destination $stagePath
  Copy-Item -LiteralPath (Join-Path $projectRoot 'dist') -Destination $stagePath -Recurse
  Copy-Item -LiteralPath (Join-Path $projectRoot 'public') -Destination $stagePath -Recurse

  & npm ci --omit=dev --prefix $stagePath
  if ($LASTEXITCODE -ne 0) {
    throw "Production dependency installation failed with exit code $LASTEXITCODE."
  }

  & tar.exe -a -c -f $zipPath -C $stagePath dist public node_modules package.json package-lock.json
  if ($LASTEXITCODE -ne 0) {
    throw "ZIP packaging failed with exit code $LASTEXITCODE."
  }

  Invoke-Az -Arguments @(
    'webapp', 'config', 'appsettings', 'set',
    '--name', $AppName,
    '--resource-group', $ResourceGroup,
    '--subscription', $SubscriptionId,
    '--settings', 'PORT=3000'
  )
  Invoke-Az -Arguments @(
    'webapp', 'config', 'set',
    '--name', $AppName,
    '--resource-group', $ResourceGroup,
    '--subscription', $SubscriptionId,
    '--startup-file', 'npm start'
  )
  Invoke-Az -Arguments @(
    'webapp', 'deploy',
    '--name', $AppName,
    '--resource-group', $ResourceGroup,
    '--subscription', $SubscriptionId,
    '--src-path', $zipPath,
    '--type', 'zip',
    '--clean', 'true',
    '--track-status', 'true',
    '--timeout', '120000'
  )

  $baseUrl = "https://$AppName.azurewebsites.net"
  $health = Invoke-RestMethod -Uri "$baseUrl/api/health" -TimeoutSec 30
  if ($health.status -ne 'ok' -or $health.service -ne 'flowdesk') {
    throw "Unexpected health response from $baseUrl/api/health."
  }

  $ready = Invoke-RestMethod -Uri "$baseUrl/api/readyz" -TimeoutSec 30
  if ($ready.status -ne 'ready') {
    throw "Unexpected readiness response from $baseUrl/api/readyz."
  }

  Write-Output "FlowDesk deployed and healthy at $baseUrl"
}
finally {
  if (Test-Path -LiteralPath $stagePath) {
    Remove-Item -LiteralPath $stagePath -Recurse -Force
  }
  if (Test-Path -LiteralPath $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
  }
}
