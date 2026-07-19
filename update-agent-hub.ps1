# Safely update the current Agent Hub branch while preserving local changes.

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

function Invoke-Git {
  param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
  & git @Arguments
  if ($LASTEXITCODE -ne 0) {
    throw "git $($Arguments -join ' ') failed with exit code $LASTEXITCODE"
  }
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
  Write-Error "Git was not found. Install Git and try again."
  exit 1
}

& git rev-parse --is-inside-work-tree *> $null
if ($LASTEXITCODE -ne 0) {
  Write-Error "This folder is not a Git clone. Downloaded ZIP folders cannot be updated with Git."
  exit 1
}

$Branch = (& git branch --show-current).Trim()
if (-not $Branch) {
  Write-Error "The repository is in detached HEAD state. Switch to a branch before updating."
  exit 1
}

& git remote get-url origin *> $null
if ($LASTEXITCODE -ne 0) {
  Write-Error "Git remote 'origin' is not configured."
  exit 1
}

$RemoteUrl = (& git remote get-url origin).Trim()
$Stashed = $false
$PullCompleted = $false
$StashLabel = "agent-hub-auto-update-$(Get-Date -Format 'yyyyMMdd-HHmmss')"

function Restore-LocalChanges {
  if (-not $script:Stashed) { return $true }
  Write-Host "Restoring local changes..."
  & git stash pop --index
  if ($LASTEXITCODE -eq 0) {
    $script:Stashed = $false
    return $true
  }
  Write-Host ""
  Write-Warning "Local changes are preserved in git stash but need conflict resolution."
  Write-Host "Run: git stash list"
  Write-Host "Then resolve conflicts and run: git stash pop"
  return $false
}

Write-Host "=========================================="
Write-Host "  Agent Hub - GitHub updater"
Write-Host "=========================================="
Write-Host ""
Write-Host "Folder : $Root"
Write-Host "Branch : $Branch"
Write-Host "Remote : $RemoteUrl"
Write-Host ""

try {
  $Status = (& git status --porcelain --untracked-files=normal) -join "`n"
  if ($Status) {
    Write-Host "Saving local changes temporarily..."
    $BeforeStash = (& git rev-parse -q --verify refs/stash 2>$null) -join ""
    Invoke-Git stash push --include-untracked -m $StashLabel
    $AfterStash = (& git rev-parse -q --verify refs/stash 2>$null) -join ""
    if ($AfterStash -and $AfterStash -ne $BeforeStash) {
      $Stashed = $true
    }
  }

  Write-Host "Fetching updates from GitHub..."
  Invoke-Git fetch --prune origin

  Write-Host "Updating $Branch with fast-forward only..."
  Invoke-Git pull --ff-only origin $Branch
  $PullCompleted = $true

  if (-not (Restore-LocalChanges)) {
    throw "GitHub was updated, but local changes need conflict resolution."
  }

  $Commit = (& git rev-parse --short HEAD).Trim()
  $Subject = (& git log -1 --pretty=%s).Trim()
  Write-Host ""
  Write-Host "Update complete."
  Write-Host "Commit : $Commit"
  Write-Host "Version: $Subject"
  Write-Host ""
  Write-Host "Restart Agent Hub to load the new code."
  exit 0
}
catch {
  if ($Stashed -and -not $PullCompleted) {
    Restore-LocalChanges | Out-Null
  }
  Write-Host ""
  Write-Error $_.Exception.Message
  exit 1
}
