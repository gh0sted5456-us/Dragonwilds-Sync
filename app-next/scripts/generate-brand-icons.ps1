param(
  [string]$Source = (Join-Path $PSScriptRoot "..\public\icon-build.png"),
  [string]$OutputDirectory = (Join-Path $PSScriptRoot "..\public")
)

Add-Type -AssemblyName System.Drawing

function Write-RsdwIcon([string]$Target, [System.Drawing.Color]$Background) {
  $size = 512
  $bitmap = [System.Drawing.Bitmap]::new($size, $size, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
  $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
  $logo = [System.Drawing.Image]::FromFile($Source)
  try {
    $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $graphics.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
    $graphics.Clear($Background)

    $gold = [System.Drawing.Color]::FromArgb(255, 208, 165, 68)
    $pen = [System.Drawing.Pen]::new($gold, 12)
    try { $graphics.DrawRectangle($pen, 7, 7, $size - 14, $size - 14) } finally { $pen.Dispose() }

    # Keep the official mark unchanged and give it enough breathing room to stay
    # readable in Windows taskbar, tray, Start menu, and installer sizes.
    $padding = 58
    $graphics.DrawImage($logo, $padding, $padding, $size - (2 * $padding), $size - (2 * $padding))
    $bitmap.Save($Target, [System.Drawing.Imaging.ImageFormat]::Png)
  } finally {
    $logo.Dispose()
    $graphics.Dispose()
    $bitmap.Dispose()
  }
}

New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
Write-RsdwIcon (Join-Path $OutputDirectory "icon-dark.png") ([System.Drawing.Color]::FromArgb(255, 11, 12, 18))
Write-RsdwIcon (Join-Path $OutputDirectory "icon-light.png") ([System.Drawing.Color]::FromArgb(255, 255, 253, 248))
