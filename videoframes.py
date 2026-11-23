# Ajazz AK980 V2 Manager - control software for the AJAZZ AK980 (V2) PRO keyboard
# Copyright (C) 2026 j0p3s. GPL-3.0-or-later (see LICENSE). Not affiliated with or endorsed by AJAZZ.
"""Video to screen frames with ffmpeg (used when it is installed; nothing is bundled): the first frames of a video, scaled to fit
the keyboard screen (240x135, black bars if the shape differs)."""
import glob
import os
import shutil
import subprocess
import tempfile

NO_WINDOW = 0x08000000
HINT = 'ffmpeg was not found. Install it (in a terminal: winget install Gyan.FFmpeg), then restart this program.'


def find_ffmpeg():
    p = shutil.which('ffmpeg')
    if p:
        return p
    hits = glob.glob(os.path.expandvars(r'%LOCALAPPDATA%\Microsoft\WinGet\Packages\*FFmpeg*\**\ffmpeg.exe'), recursive=True)
    return hits[0] if hits else None


def command(ffmpeg, video, fps, max_frames, outdir):
    vf = 'fps=%d,scale=240:135:force_original_aspect_ratio=decrease,pad=240:135:(ow-iw)/2:(oh-ih)/2' % fps
    return [ffmpeg, '-hide_banner', '-loglevel', 'error', '-i', video, '-vf', vf, '-frames:v', str(max_frames),
            os.path.join(outdir, 'f%04d.png')]


def extract(video, fps=10, max_frames=140):
    """(frame file paths, temp folder). The caller loads the files and then removes the folder. Raises OSError with a readable message."""
    exe = find_ffmpeg()
    if not exe:
        raise OSError(HINT)
    fps = max(1, min(25, int(fps)))
    out = tempfile.mkdtemp(prefix='ak980_video_')
    try:
        r = subprocess.run(command(exe, video, fps, max(1, min(140, int(max_frames))), out), capture_output=True, text=True,
                           timeout=300, creationflags=NO_WINDOW)
    except (OSError, subprocess.SubprocessError) as e:
        shutil.rmtree(out, ignore_errors=True)
        raise OSError('ffmpeg could not run: %s' % e)
    files = sorted(glob.glob(os.path.join(out, 'f*.png')))
    if not files:
        shutil.rmtree(out, ignore_errors=True)
        raise OSError('no frames could be read from this video (%s)' % (r.stderr.strip().splitlines() or ['unknown error'])[-1])
    return files, out
