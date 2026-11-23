# AK980 Manager - control software for the AJAZZ AK980 (V2) PRO keyboard
# Copyright (C) 2026 j0p3s. GPL-3.0-or-later (see LICENSE). Not affiliated with or endorsed by AJAZZ.
"""The Screen page: frame list, small picture editor, GIF import / export and upload to the keyboard's 240x135 display."""
import glob
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import ak980
import theme
from pages import Page, Palette, hex_rgb
from theme import C, Btn, Card, Seg, Slider, label, listbox

W, H, ZOOM = ak980.Keyboard.SCREEN_W, ak980.Keyboard.SCREEN_H, 2          # the editor shows the picture at 2x
MIN_DELAY, MAX_DELAY = 2, 508                                             # the keyboard stores delay/2 in one byte
UNDO_LEVELS = 15


def fit_delay(ms):
    return max(MIN_DELAY, min(MAX_DELAY, int(ms) // 2 * 2))


def original_animation_path():
    """The animation the official app ships for this keyboard (probably what the keyboard shows out of the box), or None."""
    hits = glob.glob(r'C:\Program Files (x86)\AJAZZ AK980*\gif\*\0.gif') + glob.glob(r'C:\Program Files\AJAZZ AK980*\gif\*\0.gif')
    return hits[0] if hits else None


class Frame:
    def __init__(self, name, img, delay=50):
        self.name, self.img, self.delay, self.undo = name, img, fit_delay(delay), []

    def push_undo(self):
        self.undo.append(self.img.copy())
        del self.undo[:-UNDO_LEVELS]


class ScreenPage(Page):
    title, subtitle = 'Screen', 'Build pictures and animations for the keyboard\'s little display: import, draw, order, export, upload.'

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.frames, self.photo, self.cur, self.last = [], None, None, None
        self.tool, self.size, self.color = tk.StringVar(value='Brush'), tk.IntVar(value=6), '#ffffff'
        self.text, self.fsize, self.delay = tk.StringVar(value='Hello'), tk.IntVar(value=28), tk.IntVar(value=50)
        top = tk.Frame(self, bg=C['bg'])
        top.pack(fill='x')
        for text, cmd, kind in (('Add images / GIF...', self.add, 'primary'), ('Add video...', self.add_video, 'ghost'), ('New blank frame', self.new_frame, 'ghost'),
                                ('Duplicate', self.duplicate, 'ghost'), ('Delete', self.remove, 'ghost'),
                                ('Move up', lambda: self.move(-1), 'ghost'), ('Move down', lambda: self.move(1), 'ghost'),
                                ('Clear all', self.clear, 'ghost')):
            Btn(top, text, cmd, kind, height=32, size=9).pack(side='left', padx=(0, 6))
        Btn(top, 'Sync clock', self.sync, height=32, size=9).pack(side='right')
        Btn(top, 'Export GIF...', self.export, height=32, size=9).pack(side='right', padx=6)
        body = tk.Frame(self, bg=C['bg'])
        body.pack(fill='both', expand=True, pady=10)
        left = Card(body, 'Frames')
        left.pack(side='left', fill='y', padx=(0, 12))
        self.lb = listbox(left.body, 14)
        self.lb.configure(width=24)
        self.lb.pack(fill='y', expand=True)
        self.lb.bind('<<ListboxSelect>>', self._select)
        orig = original_animation_path()
        if orig:
            Btn(left.body, 'Load original animation', lambda: self._load_file(orig, replace=True), height=30, size=9).pack(anchor='w', pady=(8, 0))
        right = Card(body, 'Editor')
        right.pack(side='left', fill='both', expand=True)
        self.cv = tk.Canvas(right.body, width=W * ZOOM, height=H * ZOOM, bg='#000000', highlightthickness=1, highlightbackground=C['line'],
                            cursor='crosshair')
        self.cv.pack(anchor='w')
        self.cv.bind('<ButtonPress-1>', self._down)
        self.cv.bind('<B1-Motion>', self._drag)
        self.cv.bind('<ButtonRelease-1>', lambda e: setattr(self, 'last', None))
        self.cv.bind('<MouseWheel>', self._wheel)
        tools = tk.Frame(right.body, bg=C['card'])
        tools.pack(fill='x', pady=(10, 0))
        Seg(tools, ('Brush', 'Eraser', 'Text', 'Fill'), self.tool, self._tool_changed, width=70).pack(side='left')
        Btn(tools, 'Undo', self.undo, height=30, size=9).pack(side='left', padx=10)
        self.swatch = tk.Canvas(tools, width=30, height=26, bg=C['card'], highlightthickness=0)
        self.swatch.pack(side='left', padx=(6, 0))
        Palette(right.body, self.set_color, self.color).pack(anchor='w', pady=(8, 0))
        opts = tk.Frame(right.body, bg=C['card'])
        opts.pack(fill='x', pady=(8, 0))
        self.size_slider = Slider(opts, 'Size', self.size, 1, 40, 1, width=200)
        self.size_slider.pack(side='left')
        self.text_box = tk.Frame(opts, bg=C['card'])
        label(self.text_box, 'Text', 10, False, C['muted'], C['card']).pack(side='left', padx=(20, 6))
        ttk.Entry(self.text_box, textvariable=self.text, width=22).pack(side='left')
        self.text_hint = label(self.text_box, 'click to place; mouse wheel changes the size', 9, False, C['muted'], C['card'])
        self.text_hint.pack(side='left', padx=8)
        foot = tk.Frame(self, bg=C['bg'])
        foot.pack(fill='x')
        Slider(foot, 'Delay of this frame', self.delay, MIN_DELAY, MAX_DELAY, 2, self._delay_changed, width=250, unit=' ms').pack(side='left')
        Btn(foot, 'Apply to all', self.delay_all, height=30, size=9).pack(side='left', padx=10)
        self.bar = ttk.Progressbar(foot, length=160, mode='determinate')
        self.bar.pack(side='left', padx=14)
        self.up = Btn(foot, 'Upload to keyboard', self.upload, 'primary', height=38)
        self.up.pack(side='right')
        label(self, 'Up to %d frames. Do not unplug the keyboard while uploading.' % ak980.Keyboard.MAX_FRAMES, 9, False, C['muted']).pack(
            anchor='w', pady=(6, 0))
        self._tool_changed()
        self.set_color(self.color)

    # ------------------------------------------------------------------ frames
    def _need_pil(self):
        try:
            import PIL.Image  # noqa: F401
            return True
        except ImportError:
            messagebox.showerror('Screen', 'The Pillow package is missing. Restart the program once while online to install it.')
            return False

    def add(self):
        if not self._need_pil():
            return
        for f in filedialog.askopenfilenames(filetypes=[('Images', '*.png *.jpg *.jpeg *.bmp *.gif')]):
            self._load_file(f)

    def add_video(self):
        """Add the first frames of a video (needs ffmpeg)."""
        if not self._need_pil():
            return
        from tkinter import simpledialog
        import shutil
        import videoframes
        f = filedialog.askopenfilename(filetypes=[('Video', '*.mp4 *.mkv *.mov *.avi *.webm *.m4v *.gif'), ('All files', '*.*')])
        if not f:
            return
        room = ak980.Keyboard.MAX_FRAMES - len(self.frames)
        if room <= 0:
            messagebox.showinfo('Screen', 'The screen already has the most frames the keyboard takes (%d).' % ak980.Keyboard.MAX_FRAMES)
            return
        fps = simpledialog.askinteger('Video', 'Frames per second to take from the video (1-25).\n\nThe keyboard takes at most %d frames in total, '
                                      'so %d fps gives %.0f seconds.' % (ak980.Keyboard.MAX_FRAMES, 10, room / 10.0), initialvalue=10,
                                      minvalue=1, maxvalue=25, parent=self)
        if not fps:
            return
        self.app.status_msg('Reading the video...', 'info')
        self.update_idletasks()
        try:
            files, tmp = videoframes.extract(f, fps, room)
        except OSError as e:
            messagebox.showerror('Video', str(e))
            return
        try:
            from PIL import Image
            delay = fit_delay(1000.0 / fps)
            for i, p in enumerate(files):
                with Image.open(p) as im:
                    self.frames.append(Frame('%s #%d' % (os.path.basename(f), i + 1), im.convert('RGB').resize((W, H)).copy(), delay))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        self._refresh(len(self.frames) - 1)
        self.app.status_msg('%d video frames added' % len(files), 'ok')

    def _load_file(self, f, replace=False):
        if not self._need_pil():
            return
        from PIL import Image, ImageSequence
        if replace:
            if self.frames and not messagebox.askyesno('Screen', 'Replace the current frames?'):
                return
            self.frames = []
        try:
            im = Image.open(f)
            for i, fr in enumerate(ImageSequence.Iterator(im)):
                if len(self.frames) >= ak980.Keyboard.MAX_FRAMES:
                    messagebox.showinfo('Screen', 'The keyboard takes at most %d frames; the rest were not added.' % ak980.Keyboard.MAX_FRAMES)
                    break
                dur = fr.info.get('duration') or 50
                self.frames.append(Frame('%s #%d' % (os.path.basename(f), i + 1), fr.convert('RGB').resize((W, H)).copy(), dur))
        except Exception as e:
            messagebox.showerror('Image', '%s: %s' % (f, e))
        self._refresh(len(self.frames) - 1 if self.frames else None)

    def new_frame(self):
        if not self._need_pil():
            return
        from PIL import Image
        if len(self.frames) >= ak980.Keyboard.MAX_FRAMES:
            return
        self.frames.insert((self.cur + 1) if self.cur is not None else len(self.frames), Frame('blank', Image.new('RGB', (W, H), '#000000'), self.delay.get()))
        self._refresh((self.cur + 1) if self.cur is not None else len(self.frames) - 1)

    def duplicate(self):
        if self.cur is None or len(self.frames) >= ak980.Keyboard.MAX_FRAMES:
            return
        f = self.frames[self.cur]
        self.frames.insert(self.cur + 1, Frame(f.name + ' copy', f.img.copy(), f.delay))
        self._refresh(self.cur + 1)

    def remove(self):
        if self.cur is None:
            return
        del self.frames[self.cur]
        self._refresh(min(self.cur, len(self.frames) - 1) if self.frames else None)

    def move(self, d):
        if self.cur is None or not 0 <= self.cur + d < len(self.frames):
            return
        self.frames[self.cur], self.frames[self.cur + d] = self.frames[self.cur + d], self.frames[self.cur]
        self._refresh(self.cur + d)

    def clear(self):
        if self.frames and not messagebox.askyesno('Screen', 'Remove all frames?'):
            return
        self.frames = []
        self._refresh(None)

    def _refresh(self, select=None):
        self.lb.delete(0, 'end')
        for i, f in enumerate(self.frames):
            self.lb.insert('end', ' %3d  %s  (%d ms)' % (i + 1, f.name[:16], f.delay))
        self.cur = select
        if select is not None:
            self.lb.selection_clear(0, 'end')
            self.lb.selection_set(select)
            self.lb.see(select)
            self.delay.set(self.frames[select].delay)
        self._draw()

    def _select(self, _=None):
        s = self.lb.curselection()
        if s:
            self.cur = s[0]
            self.delay.set(self.frames[self.cur].delay)
            self._draw()

    def _draw(self):
        self.cv.delete('all')
        if self.cur is None or not self.frames:
            self.cv.create_text(W, H, text='Add pictures or a GIF, or make a blank frame', fill=C['muted'], font=theme.font(10))
            return
        try:
            from PIL import ImageTk
            self.photo = ImageTk.PhotoImage(self.frames[self.cur].img.resize((W * ZOOM, H * ZOOM)))
            self.cv.create_image(0, 0, image=self.photo, anchor='nw')
        except Exception:
            pass

    # ------------------------------------------------------------------ delays
    def _delay_changed(self):
        if self.cur is not None:
            self.frames[self.cur].delay = fit_delay(self.delay.get())
            self.lb.delete(self.cur)
            f = self.frames[self.cur]
            self.lb.insert(self.cur, ' %3d  %s  (%d ms)' % (self.cur + 1, f.name[:16], f.delay))
            self.lb.selection_set(self.cur)

    def delay_all(self):
        d = fit_delay(self.delay.get())
        for f in self.frames:
            f.delay = d
        self._refresh(self.cur)

    # ------------------------------------------------------------------ drawing
    def set_color(self, c):
        self.color = c
        self.swatch.delete('all')
        theme.rrect(self.swatch, 0, 0, 30, 26, 7, fill=c, outline=C['line'])

    def _tool_changed(self):
        t = self.tool.get()
        if t == 'Text':
            self.text_box.pack(side='left')
        else:
            self.text_box.pack_forget()
        self.cv.configure(cursor='xterm' if t == 'Text' else 'crosshair')

    def undo(self):
        if self.cur is not None and self.frames[self.cur].undo:
            self.frames[self.cur].img = self.frames[self.cur].undo.pop()
            self._draw()

    def _wheel(self, e):
        if self.tool.get() == 'Text':
            self.fsize.set(max(6, min(120, self.fsize.get() + (3 if e.delta > 0 else -3))))
        else:
            self.size.set(max(1, min(40, self.size.get() + (1 if e.delta > 0 else -1))))
        self.size_slider.refresh() if hasattr(self.size_slider, 'refresh') else None

    def _down(self, e):
        if self.cur is None:
            return
        from PIL import ImageDraw
        f = self.frames[self.cur]
        x, y = e.x // ZOOM, e.y // ZOOM
        t = self.tool.get()
        f.push_undo()
        d = ImageDraw.Draw(f.img)
        if t == 'Fill':
            d.rectangle([0, 0, W, H], fill=self.color)
        elif t == 'Text':
            d.text((x, y), self.text.get(), fill=self.color, font=self._font())
        else:
            self.last = (x, y)
            self._stroke(d, x, y, x, y)
        self._draw()

    def _drag(self, e):
        if self.cur is None or self.last is None or self.tool.get() not in ('Brush', 'Eraser'):
            return
        from PIL import ImageDraw
        x, y = e.x // ZOOM, e.y // ZOOM
        self._stroke(ImageDraw.Draw(self.frames[self.cur].img), self.last[0], self.last[1], x, y)
        self.last = (x, y)
        self._draw()

    def _stroke(self, d, x0, y0, x1, y1):
        col = '#000000' if self.tool.get() == 'Eraser' else self.color
        r = max(1, self.size.get() // 2)
        d.line([x0, y0, x1, y1], fill=col, width=max(1, self.size.get()))
        for x, y in ((x0, y0), (x1, y1)):
            d.ellipse([x - r, y - r, x + r, y + r], fill=col)

    def _font(self):
        from PIL import ImageFont
        for name in ('segoeui.ttf', 'arial.ttf', 'DejaVuSans.ttf'):
            try:
                return ImageFont.truetype(name, int(self.fsize.get()))
            except OSError:
                continue
        return ImageFont.load_default()

    # ------------------------------------------------------------------ export / upload
    def export(self):
        if not self.frames or not self._need_pil():
            return
        dest = filedialog.asksaveasfilename(defaultextension='.gif', filetypes=[('GIF', '*.gif')], initialfile='keyboard-screen.gif')
        if not dest:
            return
        try:
            imgs = [f.img for f in self.frames]
            imgs[0].save(dest, save_all=True, append_images=imgs[1:], duration=[max(20, f.delay // 10 * 10) for f in self.frames], loop=0)
            self.app.status_msg('GIF saved (%d frames)' % len(imgs), 'ok')
        except Exception as e:
            messagebox.showerror('Export GIF', str(e))

    def sync(self):
        if self.app.require_kb():
            self.app.run(lambda kb: kb.set_time(), 'Clock synced')

    def upload(self):
        if not self.frames or not self.app.require_kb():
            return
        imgs = [f.img for f in self.frames]
        delays = [f.delay for f in self.frames]
        try:                                           # keep the user's own picture: the live screen puts it back after its cards
            import live
            os.makedirs(os.path.dirname(live.USER_GIF), exist_ok=True)
            imgs[0].convert('RGB').save(live.USER_GIF, save_all=True, append_images=[i.convert('RGB') for i in imgs[1:]], duration=delays, loop=0)
        except Exception:
            pass
        self.bar.configure(maximum=1, value=0)
        self.up.set_enabled(False)

        def prog(i, n):
            self.app.post(lambda: self.bar.configure(maximum=n, value=i))
        self.app.run(lambda kb: kb.upload_screen(imgs, delays, prog), 'Screen uploaded', after=lambda: self.up.set_enabled(True))
