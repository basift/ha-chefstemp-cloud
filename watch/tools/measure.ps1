param([string]$Img = "$PSScriptRoot\..\build\calib.png")
Add-Type -AssemblyName System.Drawing
$b = [System.Drawing.Bitmap]::FromFile((Resolve-Path $Img))
# red markers: pure-ish red blobs
$reds = @()
for ($y = 0; $y -lt $b.Height; $y++) {
    for ($x = 0; $x -lt $b.Width; $x++) {
        $c = $b.GetPixel($x, $y)
        if ($c.R -gt 200 -and $c.G -lt 50 -and $c.B -lt 50) { $reds += ,@($x, $y) }
    }
}
$minY = ($reds | ForEach-Object { $_[1] } | Measure-Object -Minimum).Minimum
$row = $reds | Where-Object { $_[1] -eq $minY } | ForEach-Object { $_[0] } | Sort-Object
# group marker x ranges
$groups = @(); $start = $row[0]; $prev = $row[0]
foreach ($x in $row[1..($row.Count - 1)]) { if ($x -gt $prev + 1) { $groups += ,@($start, $prev); $start = $x }; $prev = $x }
$groups += ,@($start, $prev)
$scale = (($groups[1][0] - $groups[0][0]) / 55.0)
"markerY=$minY scale=$([math]::Round($scale,3)) groups=$($groups.Count)"
for ($i = 0; $i -lt $groups.Count; $i++) {
    $x0 = $groups[$i][1] + 2
    $x1 = if ($i + 1 -lt $groups.Count) { $groups[$i + 1][0] - 2 } else { $x0 + 40 }
    $top = $null; $bot = $null
    for ($y = $minY - 5; $y -lt $minY + 250; $y++) {
        for ($x = $x0; $x -lt $x1; $x++) {
            $c = $b.GetPixel($x, $y)
            if ($c.R -gt 180 -and $c.G -gt 180 -and $c.B -gt 180) { if ($top -eq $null) { $top = $y }; $bot = $y; break }
        }
    }
    "font $i glyphTop=$([math]::Round(($top - $minY) / $scale,1)) glyphBottom=$([math]::Round(($bot - $minY) / $scale,1))"
}
