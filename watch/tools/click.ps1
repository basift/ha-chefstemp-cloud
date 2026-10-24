param([int]$X, [int]$Y, [int]$HoldMs = 80)
# Sends a click to the simulator window via window messages; the real mouse is not touched.
# X/Y are relative to the simulator's outer window rectangle (same as shot.ps1 images).
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class M {
  [StructLayout(LayoutKind.Sequential)] public struct POINT { public int X, Y; }
  public struct RECT { public int L, T, R, B; }
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
  [DllImport("user32.dll")] public static extern bool ScreenToClient(IntPtr h, ref POINT p);
  [DllImport("user32.dll")] public static extern IntPtr WindowFromPoint(POINT p);
  [DllImport("user32.dll")] public static extern IntPtr ChildWindowFromPointEx(IntPtr h, POINT p, uint flags);
  [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr h, uint msg, IntPtr w, IntPtr l);
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
}
"@
$p = Get-Process simulator | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1
$top = $p.MainWindowHandle
$r = New-Object M+RECT
[M]::GetWindowRect($top, [ref]$r) | Out-Null
$sx = $r.L + $X; $sy = $r.T + $Y
# descend to the deepest child window under the point
$target = $top
while ($true) {
    $pt = New-Object M+POINT; $pt.X = $sx; $pt.Y = $sy
    [M]::ScreenToClient($target, [ref]$pt) | Out-Null
    $child = [M]::ChildWindowFromPointEx($target, $pt, 5)
    if ($child -eq [IntPtr]::Zero -or $child -eq $target) { break }
    $target = $child
}
$pt = New-Object M+POINT; $pt.X = $sx; $pt.Y = $sy
[M]::ScreenToClient($target, [ref]$pt) | Out-Null
$l = [IntPtr](($pt.Y -shl 16) -bor ($pt.X -band 0xFFFF))
[M]::PostMessage($target, 0x0200, [IntPtr]0, $l) | Out-Null
[M]::PostMessage($target, 0x0201, [IntPtr]1, $l) | Out-Null
Start-Sleep -Milliseconds $HoldMs
[M]::PostMessage($target, 0x0202, [IntPtr]0, $l) | Out-Null
Start-Sleep -Milliseconds 1200
