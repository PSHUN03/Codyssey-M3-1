# Finalize the draft deck with PowerPoint (Windows only).
# 1) Temporarily registers the Paperlogy fonts for this session (no permanent install)
# 2) Opens _draft.pptx in PowerPoint and saves it with the fonts embedded
# 3) Exports a PDF (and optional PNG previews for visual QA)
# 4) Unregisters the fonts again
#
# Usage: powershell -ExecutionPolicy Bypass -File docs/presentation/finalize_deck.ps1 -FontDir <folder with Paperlogy-*.ttf> [-PreviewDir <folder>]
param(
    [Parameter(Mandatory = $true)][string]$FontDir,
    [string]$PreviewDir = ""
)
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$draft = Join-Path $here "_draft.pptx"
$final = Join-Path $here "sadari_presentation.pptx"
$pdf = Join-Path $here "sadari_presentation.pdf"

Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class FontRes {
    [DllImport("gdi32.dll", CharSet = CharSet.Unicode)] public static extern int AddFontResourceW(string file);
    [DllImport("gdi32.dll", CharSet = CharSet.Unicode)] public static extern bool RemoveFontResourceW(string file);
    [DllImport("user32.dll")] public static extern IntPtr SendMessageTimeout(IntPtr hWnd, uint msg, IntPtr wParam, IntPtr lParam, uint flags, uint timeout, out IntPtr result);
}
"@

function Notify-FontChange {
    $result = [IntPtr]::Zero
    [void][FontRes]::SendMessageTimeout([IntPtr]0xffff, 0x001D, [IntPtr]::Zero, [IntPtr]::Zero, 2, 2000, [ref]$result)
}

$fonts = Get-ChildItem -Path $FontDir -Filter "Paperlogy-*.ttf"
if ($fonts.Count -eq 0) { throw "No Paperlogy fonts found in $FontDir" }
foreach ($f in $fonts) { [void][FontRes]::AddFontResourceW($f.FullName) }
Notify-FontChange

$app = $null
try {
    $app = New-Object -ComObject PowerPoint.Application
    # Open(FileName, ReadOnly, Untitled, WithWindow)
    $pres = $app.Presentations.Open($draft, -1, 0, 0)
    # 24 = ppSaveAsOpenXMLPresentation, -1 = msoTrue (EmbedTrueTypeFonts)
    $pres.SaveAs($final, 24, -1)
    # 32 = ppSaveAsPDF
    $pres.SaveAs($pdf, 32)
    if ($PreviewDir) {
        New-Item -ItemType Directory -Force $PreviewDir | Out-Null
        for ($i = 1; $i -le $pres.Slides.Count; $i++) {
            $pres.Slides.Item($i).Export((Join-Path $PreviewDir ("slide-{0:D2}.png" -f $i)), "PNG", 1600, 900)
        }
    }
    $pres.Close()
    Write-Output "Saved: $final"
    Write-Output "Saved: $pdf"
}
finally {
    if ($app -and $app.Presentations.Count -eq 0) { $app.Quit() }
    foreach ($f in $fonts) { [void][FontRes]::RemoveFontResourceW($f.FullName) }
    Notify-FontChange
}
