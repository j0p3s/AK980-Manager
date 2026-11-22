"""Log the HID traffic of the official AJAZZ app (DeviceDriver.exe) with Frida. Read-only: it only observes.

Usage (official app running, `pip install frida`):
    python frida_hid_logger.py <pid of DeviceDriver.exe> [output.log]

Hooks HidD_SetFeature, HidD_SetOutputReport, DeviceIoControl (HID IOCTLs) and WriteFile and writes one line per call
(time, call, handle, length, hex payload). The constant status polls (04 02 / 04 f5) are skipped.
Copyright (C) 2026 j0p3s - GPL-3.0-or-later (see LICENSE).
"""
import sys, time, frida

OUT = sys.argv[2] if len(sys.argv) > 2 else 'hid_log.txt'
JS = r"""
const paths = {};
function hex(p, n) { try { return Array.from(new Uint8Array(p.readByteArray(Math.min(n, 8192)))).map(b => ('0' + b.toString(16)).slice(-2)).join(''); } catch (e) { return '?'; } }
function hook(mod, name, cb) {
  let a = null;
  try { a = Process.getModuleByName(mod).findExportByName(name); } catch (e) { send({t: 'nomod', mod: mod}); }
  if (a) Interceptor.attach(a, cb); else send({t: 'missing', name: name});
}
hook('kernel32.dll', 'CreateFileW', {
  onEnter(args) { this.p = args[0].readUtf16String(); },
  onLeave(ret) { if (this.p && this.p.toLowerCase().indexOf('vid_') >= 0) { paths[ret.toString()] = this.p; send({t: 'open', h: ret.toString(), path: this.p}); } }
});
hook('hid.dll', 'HidD_SetFeature', { onEnter(args) { const n = args[2].toInt32(); send({t: 'SetFeature', h: args[0].toString(), path: paths[args[0].toString()], n: n, d: hex(args[1], n)}); } });
hook('hid.dll', 'HidD_SetOutputReport', { onEnter(args) { const n = args[2].toInt32(); send({t: 'SetOutput', h: args[0].toString(), path: paths[args[0].toString()], n: n, d: hex(args[1], n)}); } });
hook('kernel32.dll', 'DeviceIoControl', { onEnter(args) { const code = args[1].toInt32() >>> 0; if ((code >>> 16) === 0xb) { const n = args[3].toInt32(); send({t: 'IOCTL' + code.toString(16), h: args[0].toString(), path: paths[args[0].toString()], n: n, d: hex(args[2], n)}); } } });
hook('kernel32.dll', 'WriteFile', { onEnter(args) { const h = args[0].toString(); const nn = args[2].toInt32(); if (paths[h] || nn >= 9) { send({t: 'WriteFile', h: h, path: paths[h], n: nn, d: hex(args[1], nn)}); } } });
"""
f = open(OUT, 'w', buffering=1)


def on_msg(m, data):
    if m['type'] != 'send':
        f.write('ERR %s\n' % m)
        return
    p = m['payload']
    d = p.get('d', '')
    if p.get('t') in ('open', 'IOCTLb0192', 'IOCTLb01a2', 'IOCTLb0193'):  # opens and GET_* noise
        return
    if p.get('t') in ('SetFeature', 'SetOutput') or str(p.get('t')).startswith('IOCTL'):
        if d[:4] in ('0402', '04f5') or d[2:6] in ('0402', '04f5'):  # status polls
            return
    f.write('%.3f %s\n' % (time.time(), p))


session = frida.attach(int(sys.argv[1]))
script = session.create_script(JS)
script.on('message', on_msg)
script.load()
f.write('attached %s\n' % sys.argv[1])
while True:
    time.sleep(1)
