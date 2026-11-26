<#
.SYNOPSIS
    Run the whole pipeline: regression check, then phantom validation, then real data.

.DESCRIPTION
    Three steps, in order of how much you can trust the answer:

      1. test_frame_convention.py  -- known answer. Is the (x,y,z) -> (z,y,x)
                                      conversion between Stage 2 and Stage 3
                                      still correct?
      2. run_pipeline.py           -- known truth. A localized crossing must
                                      score CROSSING; a kissing pair must not
                                      invent a junction.
      3. run_pipeline.py --i74     -- no ground truth. Only meaningful if 1 and
                                      2 passed.

    Each step must exit 0 before the next runs. A failure stops the script and
    returns that step's exit code, so this is safe to use as a check in CI or a
    scheduled job -- not just something you read.

.PARAMETER Radius
    Half-width of the analysed cube. The main cost knob; time scales ~radius^3.

.PARAMETER Stride
    Spacing of the patch grid. Larger is faster and coarser.

.PARAMETER Iters
    Stage 3 optimisation iterations.

.PARAMETER SkipI74
    Run only the two known-answer steps. Use when you have no volume, or when
    you just want to know whether the code still works.

.PARAMETER Quick
    Small, fast settings for a smoke test (radius 16, 1 iteration).

.PARAMETER Python
    Interpreter to use. Defaults to .venv in the repository root (README.md,
    'Setup'); if that does not exist, to a venv outside the repository at
    %USERPROFILE%\venvs\hipct-structure-tensor, for repositories kept in a
    synced folder such as OneDrive.

.EXAMPLE
    .\tools\run_all.ps1
    Full run with defaults.

.EXAMPLE
    .\tools\run_all.ps1 -Quick -SkipI74
    Fast check that nothing is broken. About a minute.

.EXAMPLE
    .\tools\run_all.ps1 -Radius 48 -Iters 5
    A larger, slower run on real data.
#>

[CmdletBinding()]
param(
    [int]$Radius = 24,
    [int]$Stride = 8,
    [int]$Iters  = 3,
    [switch]$SkipI74,
    [switch]$Quick,
    [string]$Python = ""
)

# Stop on unhandled errors rather than limping onward with bad state.
$ErrorActionPreference = "Stop"

# $PSScriptRoot is the folder holding THIS file (tools/), and the repository root
# is its parent, so the script works no matter which directory you run it from.
# Resolving paths against the current directory instead is the classic way a
# script "works on my machine".
$Repo = Split-Path -Parent $PSScriptRoot
Set-Location $Repo

# Default interpreter: the repository's own .venv (the README's setup), else the
# venv kept outside the repository for synced folders.
if (-not $Python) {
    $Python = Join-Path $Repo ".venv\Scripts\python.exe"
    if (-not (Test-Path $Python)) {
        $Python = "$env:USERPROFILE\venvs\hipct-structure-tensor\Scripts\python.exe"
    }
}

# Force a non-interactive matplotlib backend. Without this a plotting import can
# try to open a window and block forever when run headless.
$env:MPLBACKEND = "Agg"

if ($Quick) {
    $Radius = 16
    $Iters  = 1
}

function Write-Banner {
    param([string]$Text, [string]$Colour = "Cyan")
    Write-Host ""
    Write-Host ("=" * 78) -ForegroundColor $Colour
    Write-Host "  $Text"                -ForegroundColor $Colour
    Write-Host ("=" * 78) -ForegroundColor $Colour
}

function Invoke-Step {
    param([string]$Name, [string[]]$Arguments)

    Write-Banner $Name
    & $Python @Arguments
    $code = $LASTEXITCODE

    if ($code -ne 0) {
        Write-Host ""
        Write-Host "FAILED: $Name  (exit code $code)" -ForegroundColor Red
        Write-Host "Stopping -- later steps are not meaningful once an earlier one fails." -ForegroundColor Red
        exit $code
    }
    Write-Host "PASSED: $Name" -ForegroundColor Green
}

# --- preflight -------------------------------------------------------------
if (-not (Test-Path $Python)) {
    Write-Host "Python not found at: $Python" -ForegroundColor Red
    Write-Host "Create the environment first (see README.md, Setup):" -ForegroundColor Yellow
    Write-Host '  python -m venv .venv'
    Write-Host '  .venv\Scripts\python.exe -m pip install -r requirements.txt'
    Write-Host 'or pass an existing interpreter with -Python <path to python.exe>.'
    exit 1
}

$started = Get-Date
Write-Banner "PIPELINE -- radius $Radius, stride $Stride, iters $Iters" "Magenta"
Write-Host "  python : $Python"
Write-Host "  repo   : $Repo"

# --- 1. known answer -------------------------------------------------------
Invoke-Step "1/3  Frame convention (regression check)" `
            @("3_global_tractography\test_frame_convention.py")

# --- 2. known truth --------------------------------------------------------
Invoke-Step "2/3  Phantom validation (known truth)" `
            @("-u", "3_global_tractography\run_pipeline.py",
              "--radius", "$Radius", "--stride", "$Stride", "--iters", "$Iters")

# --- 3. no ground truth ----------------------------------------------------
if ($SkipI74) {
    Write-Host ""
    Write-Host "Skipping the real-data step (-SkipI74)." -ForegroundColor Yellow
}
else {
    Invoke-Step "3/3  Real volume (no ground truth)" `
                @("-u", "3_global_tractography\run_pipeline.py", "--i74",
                  "--radius", "$Radius", "--stride", "$Stride", "--iters", "$Iters")
}

$elapsed = (Get-Date) - $started
Write-Banner ("ALL STEPS PASSED  ({0:mm}m {0:ss}s)" -f $elapsed) "Green"
Write-Host "  Results written to: $Repo\results"

# The figures are the point of looking at a run rather than only reading it:
# each is the greyscale image with the recovered orientations drawn on top, so
# a field that does not follow the fibres is visible immediately.
$figs = Get-ChildItem "$Repo\results\field_*.png" -ErrorAction SilentlyContinue
if ($figs) {
    Write-Host ""
    Write-Host "  Orientation overlays:" -ForegroundColor Cyan
    foreach ($f in $figs) {
        Write-Host ("    {0,-26} {1,7:N0} KB" -f $f.Name, ($f.Length / 1KB))
    }
    Write-Host ""
    Write-Host "  Open them with:  ii `"$Repo\results`""
}
Write-Host ""
exit 0
