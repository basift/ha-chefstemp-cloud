param([int]$Size = 40, [string]$Out = "$PSScriptRoot\..\resources\drawables\launcher_icon.png")
Add-Type -AssemblyName System.Drawing
$bmp = New-Object System.Drawing.Bitmap $Size, $Size
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.SmoothingMode = "AntiAlias"
$g.Clear([System.Drawing.Color]::Black)
$orange = [System.Drawing.Color]::FromArgb(255, 85, 0)
$brush = New-Object System.Drawing.SolidBrush $orange
$pen = New-Object System.Drawing.Pen $orange, ([Math]::Max(2, $Size / 16))
$s = $Size / 40.0
$g.FillPie($brush, 6 * $s, 4 * $s, 28 * $s, 26 * $s, 0, 180)
$g.DrawLine($pen, 5 * $s, 16 * $s, 35 * $s, 16 * $s)
$g.DrawLine($pen, 13 * $s, 27 * $s, 9 * $s, 37 * $s)
$g.DrawLine($pen, 27 * $s, 27 * $s, 31 * $s, 37 * $s)
$g.DrawLine($pen, 20 * $s, 30 * $s, 20 * $s, 37 * $s)
$flame = [System.Drawing.PointF[]]@(
    (New-Object System.Drawing.PointF (14 * $s), (14 * $s)),
    (New-Object System.Drawing.PointF (13 * $s), (7 * $s)),
    (New-Object System.Drawing.PointF (17 * $s), (9 * $s)),
    (New-Object System.Drawing.PointF (20 * $s), (2 * $s)),
    (New-Object System.Drawing.PointF (23 * $s), (9 * $s)),
    (New-Object System.Drawing.PointF (27 * $s), (6 * $s)),
    (New-Object System.Drawing.PointF (26 * $s), (14 * $s))
)
$g.FillPolygon($brush, $flame)
$bmp.Save((Resolve-Path -LiteralPath (Split-Path $Out)).Path + "\" + (Split-Path $Out -Leaf), [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose(); $bmp.Dispose()
