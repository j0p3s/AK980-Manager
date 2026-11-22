# Capture USB traffic on USBPcap hub 1 into numbered .pcap files. Run from an ELEVATED PowerShell with USBPcap installed.
#   powershell -ExecutionPolicy Bypass -File usbpcap_capture.ps1 [-Out captures] [-Hub 1]
# Start a new file:  Set-Content <Out>\rotate.flag "step1_effect"     Stop:  New-Item <Out>\stop.flag
# Copyright (C) 2026 j0p3s - GPL-3.0-or-later (see LICENSE).
param([string]$Out = (Join-Path $PSScriptRoot "captures"), [int]$Hub = 1)
$cmd = "C:\Program Files\USBPcap\USBPcapCMD.exe"
New-Item -ItemType Directory -Force $Out | Out-Null
$stop = Join-Path $Out "stop.flag"
$rot  = Join-Path $Out "rotate.flag"   # file content = label for the next capture
Remove-Item $stop, $rot -ErrorAction SilentlyContinue
function Start-Cap($label) {
  Start-Process -FilePath $cmd -ArgumentList @("-d", "\\.\USBPcap$Hub", "-o", (Join-Path $Out "$label.pcap"), "-A") -PassThru -WindowStyle Hidden
}
$p = Start-Cap "step0_idle"
while (-not (Test-Path $stop)) {
  if (Test-Path $rot) {
    $label = (Get-Content $rot -Raw).Trim()
    Remove-Item $rot -ErrorAction SilentlyContinue
    if (-not $p.HasExited) { Stop-Process -Id $p.Id -Force }
    Start-Sleep -Milliseconds 300
    $p = Start-Cap $label
  }
  Start-Sleep -Milliseconds 200
}
if (-not $p.HasExited) { Stop-Process -Id $p.Id -Force }
