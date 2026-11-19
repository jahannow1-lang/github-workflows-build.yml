# -*- coding: utf-8 -*-
# Ali STT - تبدیل صدا به متن (فارسی/دری/هزارگی/کابلی) - سازنده: عبدالعلی رحیمی
import os, json, time, zlib, struct, zipfile, threading
from kivy.app import App
from kivy.clock import Clock, mainthread
from kivy.core.window import Window
from kivy.core.text import Label as CoreLabel
from kivy.metrics import dp
from kivy.storage.jsonstore import JsonStore
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner, SpinnerOption
from kivy.uix.textinput import TextInput
from kivy.utils import platform

import arabic_reshaper
from bidi.algorithm import get_display
import requests

Window.clearcolor = (0.06, 0.07, 0.10, 1)
FONTS = ["/system/fonts/NotoNaskhArabic-Regular.ttf", "/system/fonts/NotoSansArabic-Regular.ttf",
         "/system/fonts/DroidSansArabic.ttf", "/system/fonts/Roboto-Regular.ttf"]
FONT = next((f for f in FONTS if os.path.exists(f)), None)
ACCENT = (0.25, 0.55, 1, 1)
DIALECTS = {
    "فارسی دری (افغانستان)": ("fa-AF", "متن به زبان فارسی دری است. لهجه کابلی."),
    "هزارگی": ("fa-AF", "متن به لهجه هزارگی افغانستان است. گپ‌ها به شکل محاوره‌ای نوشته شود."),
    "کابلی": ("fa-AF", "متن به لهجه کابلی است. گپ‌ها به شکل محاوره‌ای نوشته شود."),
    "فارسی ایران": ("fa-IR", "متن به زبان فارسی ایران است."),
    "تاجیکی": ("tg-TJ", "متن به زبان فارسی تاجیکی است."),
}
AUDIO_EXT = ("mp3", "wav", "m4a", "ogg", "flac", "aac", "wma", "opus", "mp4", "mkv", "webm", "3gp", "mov", "mpeg", "mpga")


class FaOption(SpinnerOption):
    font_name = FONT or "Roboto"
    background_normal = ""
    background_color = (0.14, 0.16, 0.22, 1)


def fa(s):
    """Reshape + bidi so Persian displays correctly in Kivy."""
    try:
        return get_display(arabic_reshaper.reshape(s))
    except Exception:
        return s


def out_dir():
    paths = []
    if platform == "android":
        from android.storage import primary_external_storage_path
        paths.append(os.path.join(primary_external_storage_path(), "Download", "AliSTT"))
    paths.append(os.path.join(App.get_running_app().user_data_dir, "AliSTT"))
    for p in paths:
        try:
            os.makedirs(p, exist_ok=True)
            t = os.path.join(p, ".t"); open(t, "w").close(); os.remove(t)
            return p
        except Exception:
            continue
    return "."


# ---------------- exporters ----------------
def save_txt(text, path):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def save_docx(text, path):
    paras = "".join(
        '<w:p><w:pPr><w:bidi/><w:jc w:val="left"/></w:pPr><w:r><w:rPr><w:rtl/><w:lang w:bidi="fa-IR"/></w:rPr>'
        '<w:t xml:space="preserve">%s</w:t></w:r></w:p>' % esc(l) for l in text.split("\n"))
    doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w='
           '"http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>%s</w:body></w:document>' % paras)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        z.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        z.writestr("word/document.xml", doc)


def render_gray(text, width=1080):
    """Render Persian text to 8-bit grayscale (white bg, black text). Returns (w,h,bytes)."""
    lines = [fa(l) for l in text.split("\n")]
    cl = CoreLabel(text="\n".join(lines), font_name=FONT or "Roboto", font_size=34, halign="right",
                   text_size=(width - 80, None), color=(0, 0, 0, 1))
    cl.refresh()
    tex = cl.texture
    w, h = tex.size
    alpha = tex.pixels[3::4]
    gray = alpha.translate(bytes(range(255, -1, -1)))
    rows = [gray[i * w:(i + 1) * w] for i in range(h)][::-1]  # GL pixels are bottom-up
    return w, h, b"".join(rows)


def save_png(text, path):
    w, h, g = render_gray(text)
    raw = b"".join(b"\x00" + g[i * w:(i + 1) * w] for i in range(h))
    def chunk(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0)) + \
        chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)


def save_pdf(text, path):
    w, h, g = render_gray(text)
    data = zlib.compress(g)
    pw, ph = w * 0.5, h * 0.5
    content = ("q %f 0 0 %f 0 0 cm /Im0 Do Q" % (pw, ph)).encode()
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            ("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %f %f] /Resources << /XObject << /Im0 5 0 R >> >> /Contents 4 0 R >>" % (pw, ph)).encode(),
            b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
            ("<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace /DeviceGray /BitsPerComponent 8 /Filter /FlateDecode /Length %d >>\nstream\n" % (w, h, len(data))).encode() + data + b"\nendstream"]
    out, offs = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offs.append(len(out)); out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    x = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for o in offs:
        out += b"%010d 00000 n \n" % o
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF" % (len(objs) + 1, x)
    with open(path, "wb") as f:
        f.write(out)


EXPORTERS = {"TXT": ("txt", save_txt), "Word": ("docx", save_docx), "PDF": ("pdf", save_pdf), "عکس PNG": ("png", save_png)}


# ---------------- live recognition (Android) ----------------
class Live:
    def __init__(self, on_text, on_state):
        self.on_text, self.on_state, self.active, self.sr, self.lang = on_text, on_state, False, None, "fa-AF"

    def start(self, lang):
        if platform != "android":
            self.on_state("زنده فقط روی اندروید کار می‌کند"); return
        self.lang, self.active = lang, True
        self._listen()

    def stop(self):
        self.active = False
        if self.sr is not None:
            try:
                from android.runnable import run_on_ui_thread
                @run_on_ui_thread
                def _s():
                    try: self.sr.stopListening(); self.sr.destroy()
                    except Exception: pass
                    self.sr = None
                _s()
            except Exception:
                pass
        self.on_state("متوقف شد")

    def _listen(self):
        from jnius import autoclass, PythonJavaClass, java_method
        from android.runnable import run_on_ui_thread
        outer = self

        class L(PythonJavaClass):
            __javainterfaces__ = ["android/speech/RecognitionListener"]
            __javacontext__ = "app"
            @java_method("(Landroid/os/Bundle;)V")
            def onReadyForSpeech(self, b): outer.on_state("در حال گوش دادن...")
            @java_method("()V")
            def onBeginningOfSpeech(self): pass
            @java_method("(F)V")
            def onRmsChanged(self, f): pass
            @java_method("([B)V")
            def onBufferReceived(self, b): pass
            @java_method("()V")
            def onEndOfSpeech(self): pass
            @java_method("(ILandroid/os/Bundle;)V")
            def onEvent(self, i, b): pass
            @java_method("(I)V")
            def onError(self, e):
                if outer.active: Clock.schedule_once(lambda dt: outer._listen(), 0.3)
            @java_method("(Landroid/os/Bundle;)V")
            def onPartialResults(self, b):
                r = b.getStringArrayList("results_recognition")
                if r is not None and r.size() > 0: outer.on_text(r.get(0), False)
            @java_method("(Landroid/os/Bundle;)V")
            def onResults(self, b):
                r = b.getStringArrayList("results_recognition")
                if r is not None and r.size() > 0: outer.on_text(r.get(0), True)
                if outer.active: Clock.schedule_once(lambda dt: outer._listen(), 0.2)

        @run_on_ui_thread
        def go():
            Intent = autoclass("android.content.Intent")
            RI = autoclass("android.speech.RecognizerIntent")
            SR = autoclass("android.speech.SpeechRecognizer")
            act = autoclass("org.kivy.android.PythonActivity").mActivity
            if self.sr is not None:
                try: self.sr.destroy()
                except Exception: pass
            self.sr = SR.createSpeechRecognizer(act)
            self.listener = L()
            self.sr.setRecognitionListener(self.listener)
            i = Intent(RI.ACTION_RECOGNIZE_SPEECH)
            i.putExtra(RI.EXTRA_LANGUAGE_MODEL, RI.LANGUAGE_MODEL_FREE_FORM)
            i.putExtra(RI.EXTRA_LANGUAGE, self.lang)
            i.putExtra(RI.EXTRA_PARTIAL_RESULTS, True)
            self.sr.startListening(i)
        go()


# ---------------- UI ----------------
def btn(text, cb, color=ACCENT, h=48):
    b = Button(text=fa(text), font_name=FONT or "Roboto", size_hint_y=None, height=dp(h),
               background_normal="", background_color=color, color=(1, 1, 1, 1), font_size=dp(15))
    b.bind(on_release=lambda *_: cb())
    return b


class Root(BoxLayout):
    def __init__(self, app, **kw):
        super().__init__(orientation="vertical", padding=dp(12), spacing=dp(8), **kw)
        self.app, self.text, self.partial = app, "", ""
        self.store = JsonStore(os.path.join(app.user_data_dir, "cfg.json"))
        self.live = Live(self.on_live_text, self.set_status)
        self.add_widget(Label(text=fa("Ali STT | تبدیل صدا به متن"), font_name=FONT or "Roboto", font_size=dp(22),
                              size_hint_y=None, height=dp(40), color=(1, 1, 1, 1)))
        self.dialect = Spinner(text=fa("فارسی دری (افغانستان)"), values=[fa(k) for k in DIALECTS], font_name=FONT or "Roboto",
                               option_cls=FaOption, size_hint_y=None, height=dp(44), background_normal="", background_color=(0.14, 0.16, 0.22, 1))
        self.add_widget(self.dialect)
        self.status = Label(text="", font_name=FONT or "Roboto", size_hint_y=None, height=dp(24), color=(0.6, 0.75, 1, 1))
        self.add_widget(self.status)
        self.out = Label(text="", font_name=FONT or "Roboto", font_size=dp(17), halign="right", valign="top",
                         size_hint_y=None, color=(1, 1, 1, 1))
        self.out.bind(width=lambda *_: setattr(self.out, "text_size", (self.out.width, None)),
                      texture_size=lambda *_: setattr(self.out, "height", max(self.out.texture_size[1], dp(200))))
        sv = ScrollView(); sv.add_widget(self.out); self.add_widget(sv)
        row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        row.add_widget(btn("● زنده", self.start_live, (0.85, 0.2, 0.25, 1)))
        row.add_widget(btn("■ توقف", self.live.stop, (0.3, 0.3, 0.38, 1)))
        row.add_widget(btn("فایل", self.pick_file))
        self.add_widget(row)
        row2 = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        row2.add_widget(btn("ذخیره", self.export_popup, (0.2, 0.65, 0.4, 1)))
        row2.add_widget(btn("کلید API", self.key_popup, (0.3, 0.3, 0.38, 1)))
        row2.add_widget(btn("پاک", self.clear, (0.3, 0.3, 0.38, 1)))
        self.add_widget(row2)
        if platform == "android":
            from android.permissions import request_permissions, Permission
            request_permissions([Permission.RECORD_AUDIO, Permission.READ_EXTERNAL_STORAGE, Permission.WRITE_EXTERNAL_STORAGE])

    def dialect_key(self):
        for k in DIALECTS:
            if fa(k) == self.dialect.text: return k
        return "فارسی دری (افغانستان)"

    @mainthread
    def set_status(self, s): self.status.text = fa(s)

    @mainthread
    def refresh(self): self.out.text = fa_block(self.text + ("\n" + self.partial if self.partial else ""))

    def on_live_text(self, t, final):
        if final: self.text += ("\n" if self.text else "") + t; self.partial = ""
        else: self.partial = t
        self.refresh()

    def start_live(self): self.live.start(DIALECTS[self.dialect_key()][0])

    def clear(self): self.text = self.partial = ""; self.refresh()

    # ---- file transcription (Whisper API, supports Persian) ----
    def pick_file(self):
        try:
            from plyer import filechooser
            filechooser.open_file(on_selection=self.on_file, filters=[["Audio/Video"] + ["*." + e for e in AUDIO_EXT]])
        except Exception as e:
            self.set_status("انتخاب فایل ممکن نشد: %s" % e)

    def on_file(self, sel):
        if sel: threading.Thread(target=self.transcribe, args=(sel[0],), daemon=True).start()

    def transcribe(self, path):
        key = self.store.get("k")["v"] if self.store.exists("k") else ""
        if not key: self.set_status("اول کلید API را وارد کنید"); return
        if os.path.getsize(path) > 25 * 1024 * 1024: self.set_status("فایل بزرگتر از ۲۵ مگابایت است"); return
        self.set_status("در حال تبدیل... لطفاً صبر کنید")
        try:
            with open(path, "rb") as f:
                r = requests.post("https://api.openai.com/v1/audio/transcriptions",
                                  headers={"Authorization": "Bearer " + key},
                                  files={"file": (os.path.basename(path), f)},
                                  data={"model": "whisper-1", "language": "fa", "response_format": "verbose_json",
                                        "temperature": 0, "prompt": DIALECTS[self.dialect_key()][1]}, timeout=600)
            r.raise_for_status()
            segs = r.json().get("segments", [])
            lines = []
            for s in segs:  # تشخیص موسیقی/سکوت از صدای گفتار
                t = s["text"].strip()
                lines.append("[موسیقی یا بدون گفتار]" if s.get("no_speech_prob", 0) > 0.6 else t)
            self.text += ("\n" if self.text else "") + "\n".join(lines)
            self.refresh(); self.set_status("تمام شد ✓")
        except Exception as e:
            self.set_status("خطا: %s" % str(e)[:80])

    # ---- popups ----
    def key_popup(self):
        ti = TextInput(text=self.store.get("k")["v"] if self.store.exists("k") else "", multiline=False, password=True)
        b = btn("ذخیره", lambda: (self.store.put("k", v=ti.text.strip()), p.dismiss()))
        box = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(8)); box.add_widget(ti); box.add_widget(b)
        p = Popup(title="API Key", content=box, size_hint=(.9, .3)); p.open()

    def export_popup(self):
        if not self.text.strip(): self.set_status("متنی برای ذخیره نیست"); return
        box = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(8))
        for name, (ext, fn) in EXPORTERS.items():
            box.add_widget(btn(name, lambda e=ext, f=fn: (self.do_export(e, f), p.dismiss())))
        p = Popup(title="Save", content=box, size_hint=(.8, .5)); p.open()

    def do_export(self, ext, fn):
        try:
            path = os.path.join(out_dir(), "stt_%s.%s" % (time.strftime("%Y%m%d_%H%M%S"), ext))
            fn(self.text, path); self.set_status("ذخیره شد: " + path)
        except Exception as e:
            self.set_status("خطا در ذخیره: %s" % str(e)[:60])


def fa_block(t): return "\n".join(fa(l) for l in t.split("\n"))


class AliSTT(App):
    title = "Ali STT"
    def build(self): return Root(self)


if __name__ == "__main__":
    AliSTT().run()
