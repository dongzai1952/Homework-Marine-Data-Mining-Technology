$ErrorActionPreference = 'Stop'
Push-Location -LiteralPath $PSScriptRoot
try {
    & xelatex -interaction=nonstopmode -halt-on-error -file-line-error main.tex
    if ($LASTEXITCODE -ne 0) { throw 'XeLaTeX first pass failed; see main.log.' }
    & biber main
    if ($LASTEXITCODE -ne 0) { throw 'Biber failed; see main.blg.' }
    & xelatex -interaction=nonstopmode -halt-on-error -file-line-error main.tex
    if ($LASTEXITCODE -ne 0) { throw 'XeLaTeX second pass failed; see main.log.' }
    & xelatex -interaction=nonstopmode -halt-on-error -file-line-error main.tex
    if ($LASTEXITCODE -ne 0) { throw 'XeLaTeX final pass failed; see main.log.' }
    Write-Host 'Compiled main.pdf. Review layout again after editing.'
} finally {
    Pop-Location
}
