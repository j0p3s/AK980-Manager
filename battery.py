# Ajazz AK980 V2 Manager - control software for the AJAZZ AK980 (V2) PRO keyboard
# Copyright (C) 2026 j0p3s. GPL-3.0-or-later (see LICENSE). Not affiliated with or endorsed by AJAZZ.
"""Battery level of a keyboard paired over Bluetooth, read-only.

Windows owns the keyboard's Bluetooth typing and exposes the standard Battery Service of a paired Bluetooth LE device as a device
property, so nothing is written to the keyboard (its vendor Bluetooth service is the firmware-update channel and is never touched;
this approach follows Keymotion's notes, Apache-2.0 / MIT). Over the USB cable and the 2.4G dongle the keyboard has no battery
read-out that this program knows; its own screen shows it there.
"""
import json
import subprocess

NO_WINDOW = 0x08000000
PROPERTY = '{104EA319-6EE2-4701-BD47-8DDBF425BBE5} 2'          # "battery percent" of a paired Bluetooth LE device
SCRIPT = r"""
$out = @()
Get-PnpDevice -ErrorAction SilentlyContinue | Where-Object {
    ($_.InstanceId -like 'BTHLE\DEV_*' -or $_.InstanceId -like 'BTHENUM\DEV_*') -and $_.FriendlyName -match 'AK980|AJAZZ|Ajazz'
} | ForEach-Object {
    $p = Get-PnpDeviceProperty -InstanceId $_.InstanceId -KeyName '%s' -ErrorAction SilentlyContinue
    $out += [pscustomobject]@{ name = $_.FriendlyName; connected = ($_.Status -eq 'OK'); battery = $p.Data }
}
ConvertTo-Json -InputObject @($out) -Compress
""" % PROPERTY


def parse(text):
    """Turn the script's JSON into [(name, connected, percent or None)]; tolerant of empty or odd output."""
    try:
        data = json.loads(text.strip() or '[]')
    except ValueError:
        return []
    if isinstance(data, dict):
        data = [data]
    out = []
    for d in data if isinstance(data, list) else []:
        if not isinstance(d, dict):
            continue
        b = d.get('battery')
        out.append((str(d.get('name', 'Keyboard')), bool(d.get('connected')),
                    int(b) if isinstance(b, (int, float)) and 0 <= b <= 100 else None))
    return out


def read():
    """[(name, connected, percent or None)] for AK980 keyboards paired over Bluetooth. Takes a few seconds."""
    r = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', SCRIPT], capture_output=True, text=True, errors='replace',
                       timeout=40, creationflags=NO_WINDOW)
    return parse(r.stdout)


def summary(found):
    """One sentence for the interface."""
    if not found:
        return 'No AK980 keyboard is paired over Bluetooth. Pair it in Windows Settings (Bluetooth and devices) first.'
    lines = []
    for name, connected, pct in found:
        state = 'connected' if connected else 'paired, not connected'
        lines.append('%s: %s' % (name, ('%d %%' % pct if pct is not None else 'battery level not reported') + ' (%s)' % state))
    return '\n'.join(lines)
