"""4단계: 대본 + 음성 → 움직이는 쇼츠 영상 (1080x1920, 30fps)

- 장면 종류(도입/제품/특징/이벤트/가격)마다 다른 화면 구성과 등장 애니메이션
- 말하는 속도에 맞춰 단어가 강조되는 자막
- 장면 전환 효과, 실시간 진행 바
- 배경: assets/<제품 id>/ 또는 assets/common/ 폴더에 영상·사진을 넣으면 배경으로 쓰고,
        없으면 움직이는 그라데이션 배경을 그린다
- 배경음악: assets/bgm.mp3 (또는 .m4a/.wav)가 있으면 작게 깔아 준다

프레임은 Pillow로 그리고 ffmpeg에 바로 흘려보내 인코딩한다.
"""
import re
import math
import os
import random
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from tts import ffmpeg_exe

RENDER_VERSION = 3
W, H = 1080, 1920
FPS = 30
PAD = 0.35           # 장면 사이 여백(초). qc.py와 같은 값
XFADE = 0.28         # 장면 전환 길이(초)
VIDEO_EXT = {".mp4", ".mov", ".webm", ".mkv", ".m4v"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}
AUDIO_EXT = {".mp3", ".m4a", ".wav", ".aac", ".ogg"}

FONT_CANDIDATES = [
    os.environ.get("KOREAN_FONT", ""),
    "C:/Windows/Fonts/malgunbd.ttf",                       # Windows
    "C:/Windows/Fonts/malgun.ttf",
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",          # macOS
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",  # Linux
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
]
_fonts = {}


def font(size):
    if size not in _fonts:
        for path in FONT_CANDIDATES:
            if path and Path(path).exists():
                _fonts[size] = ImageFont.truetype(path, size)
                break
        else:
            raise FileNotFoundError("한글 폰트를 찾지 못했습니다. KOREAN_FONT 환경변수에 폰트 경로를 넣어 주세요.")
    return _fonts[size]


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def mix(a, b, t):
    return tuple(int(a[i] * (1 - t) + b[i] * t) for i in range(3))


_measure = ImageDraw.Draw(Image.new("RGB", (8, 8)))


def wrap(text, fnt, max_w):
    """단어 단위로 줄바꿈하고, 한 단어가 너무 길면 글자 단위로 자른다."""
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if _measure.textlength(trial, font=fnt) <= max_w:
            line = trial
            continue
        if line:
            lines.append(line)
        line = ""
        for ch in word:
            if _measure.textlength(line + ch, font=fnt) > max_w:
                lines.append(line)
                line = ""
            line += ch
    if line:
        lines.append(line)
    return lines or [""]


def fit_lines(text, size, max_w, max_lines, min_size=56):
    """글자가 max_lines 줄 안에 들어올 때까지 크기를 줄인다."""
    while True:
        fnt = font(size)
        lines = wrap(text, fnt, max_w)
        if len(lines) <= max_lines or size <= min_size:
            return lines, fnt, size
        size -= 8


# ───────── 움직임 곡선 ─────────
def clamp(x):
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def out_cubic(p):
    return 1 - (1 - p) ** 3


def out_back(p, s=1.6):
    p -= 1
    return 1 + (s + 1) * p ** 3 + s * p ** 2


# ───────── 그림 조각(스프라이트) ─────────
def text_sprite(lines, fnt, fill, line_gap=1.22, shadow=True, stroke=0):
    size = fnt.size
    lh = int(size * line_gap)
    pad = 36
    w = int(max(_measure.textlength(l, font=fnt) for l in lines)) + pad * 2
    h = lh * len(lines) + pad * 2
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    if shadow:
        sh = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(sh)
        for i, l in enumerate(lines):
            d.text((w // 2, pad + lh * i + lh // 2 + 6), l, font=fnt, fill=(0, 0, 0, 170), anchor="mm")
        img = sh.filter(ImageFilter.GaussianBlur(10))
    d = ImageDraw.Draw(img)
    for i, l in enumerate(lines):
        d.text((w // 2, pad + lh * i + lh // 2), l, font=fnt, fill=fill, anchor="mm",
               stroke_width=stroke, stroke_fill=(0, 0, 0, 255))
    return img


def pill_sprite(text, fnt, bg, fg, pad_x=44, pad_y=20):
    tw = int(_measure.textlength(text, font=fnt))
    w, h = tw + pad_x * 2, fnt.size + pad_y * 2
    img = Image.new("RGBA", (w + 8, h + 8), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([4, 4, w + 4, h + 4], h // 2, fill=bg)
    d.text((4 + w // 2, 4 + h // 2), text, font=fnt, fill=fg, anchor="mm")
    return img


def bar_sprite(w, h, color):
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle([0, 0, w - 1, h - 1], h // 2, fill=color)
    return img


def card_sprite(lines, fnt, bg, fg, pad_x=70, pad_y=56, line_gap=1.2):
    lh = int(fnt.size * line_gap)
    tw = int(max(_measure.textlength(l, font=fnt) for l in lines))
    w, h = tw + pad_x * 2, lh * len(lines) + pad_y * 2
    m = 30
    img = Image.new("RGBA", (w + m * 2, h + m * 2), (0, 0, 0, 0))
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).rounded_rectangle([m, m + 12, m + w, m + h + 12], 44, fill=(0, 0, 0, 150))
    img = sh.filter(ImageFilter.GaussianBlur(14))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([m, m, m + w, m + h], 44, fill=bg)
    for i, l in enumerate(lines):
        d.text((m + w // 2, m + pad_y + lh * i + lh // 2), l, font=fnt, fill=fg, anchor="mm")
    return img


def fade(img, a):
    if a >= 0.999:
        return img
    out = img.copy()
    out.putalpha(img.getchannel("A").point(lambda v: int(v * a)))
    return out


class El:
    """화면 요소 하나: 그림 조각, 중심 위치, 등장 시각, 등장 방식"""

    def __init__(self, sprite, cx, cy, start=0.0, kind="up", dur=0.45, pulse=False):
        self.sprite, self.cx, self.cy = sprite, cx, cy
        self.start, self.kind, self.dur, self.pulse = start, kind, dur, pulse

    def done_at(self):
        return math.inf if self.pulse or callable(self.sprite) else self.start + self.dur

    def draw(self, canvas, t):
        p = clamp((t - self.start) / self.dur)
        if p <= 0:
            return
        img = self.sprite(t - self.start) if callable(self.sprite) else self.sprite
        x, y = self.cx, self.cy
        if self.kind == "pop":
            s = 0.6 + 0.4 * out_back(p)
            if self.pulse and p >= 1:
                s = 1 + 0.035 * math.sin((t - self.start - self.dur) * 5.0)
            if abs(s - 1) > 0.004:
                img = img.resize((max(1, int(img.width * s)), max(1, int(img.height * s))), Image.BILINEAR)
            img = fade(img, clamp(p * 2.2))
        elif self.kind == "up":
            y += int((1 - out_cubic(p)) * 80)
            img = fade(img, clamp(p * 1.6))
        elif self.kind == "fade":
            img = fade(img, p)
        elif self.kind == "wipe":
            img = img.crop((0, 0, max(1, int(img.width * out_cubic(p))), img.height))
            canvas.alpha_composite(img, (x - self.sprite.width // 2, y - self.sprite.height // 2))
            return
        canvas.alpha_composite(img, (max(0, x - img.width // 2), max(0, y - img.height // 2)))


# ───────── 장면 구성 ─────────
def scene_kind(scene, i, n, product):
    if scene.get("type") in {"hook", "intro", "feature", "event", "price"}:
        return scene["type"]
    if i == 0:
        return "hook"
    if i == n - 1:
        return "price"
    if i == 1:
        return "intro"
    if product.get("event") and scene["caption"].strip() == product["event"].strip():
        return "event"
    return "feature"


def build_scene(kind, scene, feat_no, product, brand, col):
    cap = scene["caption"].strip()
    CX, els = W // 2, []
    if kind == "hook":
        lines, fnt, size = fit_lines(cap, 128, W - 150, 3)
        lh = int(size * 1.25)
        y0 = 820 - lh * (len(lines) - 1) // 2
        if cap.endswith("?"):
            q = text_sprite(["?"], font(760), col["accent"] + (46,), shadow=False)
            els.append(El(q, CX + 250, 620, 0.0, "fade", 0.6))
        for k, l in enumerate(lines):
            els.append(El(text_sprite([l], fnt, (255, 255, 255, 255)), CX, y0 + lh * k, 0.10 + 0.16 * k, "pop", 0.42))
        els.append(El(bar_sprite(260, 16, col["accent"] + (255,)), CX, y0 + lh * len(lines) - 6,
                      0.25 + 0.16 * len(lines), "wipe", 0.4))
    elif kind == "intro":
        lines, fnt, size = fit_lines(cap, 116, W - 160, 3)
        lh = int(size * 1.22)
        y0 = 800 - lh * (len(lines) - 1) // 2
        els.append(El(pill_sprite(brand["name"], font(50), col["accent"] + (255,), col["dark"] + (255,)),
                      CX, y0 - lh // 2 - 90, 0.05, "pop", 0.4))
        els.append(El(text_sprite(lines, fnt, (255, 255, 255, 255)), CX, y0 + lh * (len(lines) - 1) // 2, 0.22, "up", 0.5))
        yb = y0 + lh * len(lines) - lh // 2 + 50
        els.append(El(bar_sprite(160, 10, col["accent"] + (255,)), CX, yb, 0.5, "wipe", 0.35))
        if brand.get("tagline"):
            els.append(El(text_sprite([brand["tagline"]], font(52), (255, 255, 255, 215)), CX, yb + 90, 0.65, "up", 0.45))
    elif kind == "feature":
        lines, fnt, size = fit_lines(cap, 112, W - 170, 3)
        lh = int(size * 1.24)
        y0 = 860 - lh * (len(lines) - 1) // 2
        els.append(El(text_sprite([f"{feat_no:02d}"], font(430), col["accent"] + (60,), shadow=False),
                      CX, y0 - lh // 2 - 250, 0.0, "fade", 0.5))
        els.append(El(pill_sprite(f"POINT {feat_no}", font(48), col["accent"] + (255,), col["dark"] + (255,)),
                      CX, y0 - lh // 2 - 80, 0.08, "pop", 0.4))
        els.append(El(text_sprite(lines, fnt, (255, 255, 255, 255)), CX, y0 + lh * (len(lines) - 1) // 2, 0.24, "up", 0.5))
        els.append(El(bar_sprite(200, 12, col["accent"] + (255,)), CX, y0 + lh * len(lines) - lh // 2 + 46, 0.55, "wipe", 0.35))
    elif kind == "event":
        lines, fnt, size = fit_lines(cap, 104, W - 300, 3)
        card = card_sprite(lines, fnt, col["accent"] + (255,), col["dark"] + (255,))
        els.append(El(pill_sprite("EVENT", font(50), (255, 255, 255, 255), col["dark"] + (255,)),
                      CX, 820 - card.height // 2 - 40, 0.05, "up", 0.4))
        els.append(El(card, CX, 840, 0.2, "pop", 0.5, pulse=True))
    else:  # price
        digits = "".join(ch for ch in cap if ch.isdigit())
        els.append(El(text_sprite(wrap(product["name"], font(60), W - 200), font(60), (255, 255, 255, 230)),
                      CX, 590, 0.05, "up", 0.45))
        if digits:
            target, suffix = int(digits), cap[cap.rfind(digits[-1]) + 1:].strip() or "원"
            fnt = font(210 if target < 100000 else 170)

            def price(t, target=target, suffix=suffix, fnt=fnt, cache={}):
                v = int(target * out_cubic(clamp((t - 0.1) / 0.8)))
                if v not in cache:
                    cache[v] = text_sprite([f"{v:,}{suffix}"], fnt, col["accent"] + (255,))
                return cache[v]
            els.append(El(price, CX, 820, 0.15, "pop", 0.45))
        else:
            lines, fnt, _ = fit_lines(cap, 150, W - 160, 2)
            els.append(El(text_sprite(lines, fnt, col["accent"] + (255,)), CX, 820, 0.15, "pop", 0.45))
        cta = brand.get("cta", "").rstrip("!").strip()
        if cta and not same_text(cap, cta):  # 큰 글씨와 같은 말이면 버튼은 생략
            lines, fnt, _ = fit_lines(cta, 56, W - 260, 2, min_size=44)
            els.append(El(card_sprite(lines, fnt, (255, 255, 255, 255), col["dark"] + (255,), 60, 36),
                          CX, 1080, 1.2, "pop", 0.45, pulse=True))
    return els


# ───────── 자막 (말하는 단어 강조) ─────────
def caption_plan(narration, speech_sec):
    """단어별 시작 시각을 글자 수 비례로 추정하고, 화면에 한 번에 띄울 묶음으로 나눈다."""
    words = narration.split()
    if not words:
        return []
    weights = [len(w) + (2.0 if w[-1] in ",.?!" else 0.0) for w in words]
    t0, t1 = 0.06, max(0.5, speech_sec - 0.12)
    total, acc, starts = sum(weights), 0.0, []
    for wgt in weights:
        starts.append(t0 + (t1 - t0) * acc / total)
        acc += wgt
    chunks, cur, count = [], [], 0
    for i, w in enumerate(words):
        if cur and count + len(w) > 11:
            chunks.append(cur)
            cur, count = [], 0
        cur.append(i)
        count += len(w)
    if cur:
        chunks.append(cur)
    return [{"words": [words[i] for i in c], "starts": [starts[i] for i in c]} for c in chunks]


class Captions:
    def __init__(self, narration, speech_sec, accent):
        self.plan = caption_plan(narration, speech_sec)
        self.accent, self.fnt, self.cache = accent, font(70), {}

    def sprite(self, ci, hi):
        key = (ci, hi)
        if key not in self.cache:
            words = self.plan[ci]["words"]
            space = _measure.textlength(" ", font=self.fnt)
            widths = [_measure.textlength(w, font=self.fnt) for w in words]
            total = int(sum(widths) + space * (len(words) - 1))
            pad_x, pad_y = 44, 26
            img = Image.new("RGBA", (total + pad_x * 2, self.fnt.size + pad_y * 2 + 10), (0, 0, 0, 0))
            d = ImageDraw.Draw(img)
            d.rounded_rectangle([0, 0, img.width - 1, img.height - 1], 30, fill=(0, 0, 0, 150))
            x = pad_x
            for k, w in enumerate(words):
                fill = self.accent + (255,) if k == hi else (255, 255, 255, 255) if k < hi else (255, 255, 255, 150)
                d.text((x, img.height // 2), w, font=self.fnt, fill=fill, anchor="lm")
                x += widths[k] + space
            self.cache[key] = img
        return self.cache[key]

    def draw(self, canvas, t):
        ci = None
        for i, c in enumerate(self.plan):
            if t >= c["starts"][0] - 0.05:
                ci = i
        if ci is None:
            return
        starts = self.plan[ci]["starts"]
        hi = max(k for k, s in enumerate(starts) if t >= s - 0.05)
        img = self.sprite(ci, hi)
        p = clamp((t - (starts[0] - 0.05)) / 0.14)
        y = 1400 + int((1 - out_cubic(p)) * 26)
        canvas.alpha_composite(fade(img, p), ((W - img.width) // 2, y - img.height // 2))


# ───────── 배경 ─────────
class GradientBG:
    """자료가 없을 때 쓰는 움직이는 배경: 그라데이션 위에 부드러운 빛망울이 천천히 떠다닌다."""
    SW, SH = W // 6, H // 6

    def __init__(self, col, seed, tint):
        top, bottom = mix(col["primary"], (255, 255, 255), 0.06 + tint), mix(col["primary"], (0, 0, 0), 0.72)
        g = Image.new("RGB", (1, self.SH))
        for y in range(self.SH):
            g.putpixel((0, y), mix(top, bottom, (y / self.SH) ** 0.85))
        self.base = g.resize((self.SW, self.SH))
        rnd = random.Random(seed)
        self.orbs = [(rnd.random(), rnd.random(), rnd.uniform(14, 44), rnd.uniform(0.02, 0.06) * rnd.choice([-1, 1]),
                      rnd.uniform(0.015, 0.04), rnd.uniform(0, 6.28), rnd.choice([col["accent"], col["accent"], (255, 255, 255)]),
                      rnd.randint(28, 70)) for _ in range(11)]

    def frame(self, t):
        layer = Image.new("RGBA", (self.SW, self.SH), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        for x, y, r, vx, vy, ph, c, a in self.orbs:
            cx = ((x + vx * t + 0.03 * math.sin(t * 0.6 + ph)) % 1.2 - 0.1) * self.SW
            cy = ((y - vy * t) % 1.2 - 0.1) * self.SH
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=c + (a,))
        layer = layer.filter(ImageFilter.GaussianBlur(9))
        img = self.base.copy()
        img.paste(layer, (0, 0), layer)
        return img.resize((W, H), Image.BILINEAR)

    def close(self):
        pass


def same_text(a, b):
    """두 문구가 사실상 같은 말인지 (띄어쓰기·문장부호 무시, 짧은 쪽 글자의 70% 이상이 겹치면)"""
    a, b = (re.sub(r"[^0-9A-Za-z가-힣]", "", x) for x in (a, b))
    if not a or not b:
        return False
    if a in b or b in a:
        return True
    short, long_ = sorted((a, b), key=len)
    return sum(1 for ch in short if ch in long_) / len(short) >= 0.7


class ImageBG:
    """사진 배경: 천천히 확대되는 효과"""

    def __init__(self, path, shade):
        from PIL import ImageOps
        im = ImageOps.exif_transpose(Image.open(path)).convert("RGB")  # 휴대폰 사진 회전 정보 반영
        s = max(W / im.width, H / im.height) * 1.14
        im = im.resize((int(im.width * s) + 1, int(im.height * s) + 1), Image.LANCZOS)
        self.im, self.shade = im, shade

    def frame(self, t, dur=6.0):
        z = 1.14 - 0.12 * clamp(t / max(dur, 0.1))
        cw, ch = W * z, H * z
        x0, y0 = (self.im.width - cw) / 2, (self.im.height - ch) / 2
        img = self.im.resize((W, H), Image.BILINEAR, box=(x0, y0, x0 + cw, y0 + ch))
        img.paste(self.shade, (0, 0), self.shade)
        return img

    def close(self):
        pass


class VideoBG:
    """영상 배경: ffmpeg으로 세로 화면에 맞게 잘라 한 프레임씩 읽는다 (짧으면 반복 재생)."""

    def __init__(self, path, shade):
        self.shade, self.last = shade, None
        self.proc = subprocess.Popen(
            [ffmpeg_exe(), "-loglevel", "error", "-stream_loop", "-1", "-i", str(path), "-an",
             "-vf", f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS}",
             "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    def frame(self, t):
        buf = self.proc.stdout.read(W * H * 3)
        if len(buf) == W * H * 3:
            img = Image.frombytes("RGB", (W, H), buf)
            img.paste(self.shade, (0, 0), self.shade)
            self.last = img
        elif self.last is None:
            raise RuntimeError("배경 영상을 읽지 못했습니다")
        return self.last.copy()

    def close(self):
        self.proc.kill()
        self.proc.stdout.close()
        self.proc.wait()


def make_shade():
    """배경 위 글자가 잘 보이도록 덮는 어두운 막 (위아래가 더 어둡다)"""
    col = Image.new("L", (1, H))
    for y in range(H):
        v = y / H
        col.putpixel((0, y), int(255 * (0.50 + 0.28 * abs(v - 0.42) ** 1.2 / 0.58 ** 1.2)))
    shade = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    shade.putalpha(col.resize((W, H)))
    return shade


def find_media(assets, product_id):
    """배경으로 쓸 파일 목록: 제품 폴더가 우선, 없으면 common 폴더"""
    if not assets:
        return []
    for folder in (Path(assets) / product_id, Path(assets) / "common"):
        if folder.is_dir():
            files = sorted(p for p in folder.iterdir() if p.suffix.lower() in VIDEO_EXT | IMAGE_EXT)
            if files:
                return files
    return []


def find_bgm(assets):
    if not assets:
        return None
    for p in sorted(Path(assets).glob("bgm.*")):
        if p.suffix.lower() in AUDIO_EXT:
            return p
    return None


def assets_fingerprint(assets, product_id):
    """배경·음악 파일이 바뀌면 다시 렌더링하도록 파이프라인이 쓰는 값"""
    files = find_media(assets, product_id) + ([find_bgm(assets)] if find_bgm(assets) else [])
    return [RENDER_VERSION] + [[p.name, p.stat().st_size, int(p.stat().st_mtime)] for p in files]


# ───────── 영상 만들기 ─────────
def draw_topbar(canvas, chip, i, n, p, col, label=None):
    d = ImageDraw.Draw(canvas)
    seg = (W - 120) / n
    for k in range(n):
        x0, x1 = 60 + k * seg + 5, 60 + (k + 1) * seg - 5
        d.rounded_rectangle([x0, 84, x1, 96], 6, fill=(255, 255, 255, 70))
        fill = 1.0 if k < i else p if k == i else 0.0
        if fill > 0.02:
            d.rounded_rectangle([x0, 84, x0 + max(12, (x1 - x0) * fill), 96], 6, fill=col["accent"] + (255,))
    canvas.alpha_composite(chip, (56, 124))
    if label is not None:  # "AI 생성 영상" 같은 고지 문구 (brand.json의 ai_label)
        canvas.alpha_composite(label, (W - 56 - label.width, 124))


def render_video(script, product, brand, voices, durations, out_path, workdir, assets=None, log=None,
                 always_label=False, scene_media=None, bgm_path=None, bgm_volume=0.3):
    """voices: 장면별 음성 파일, durations: 장면별 음성 길이(초). 장면 길이는 음성 길이 + PAD."""
    workdir = Path(workdir)
    scenes = script["scenes"]
    n = len(scenes)
    primary = hex_rgb(product.get("color") or brand["colors"]["primary"])
    col = {"primary": primary, "accent": hex_rgb(brand["colors"]["accent"]), "dark": mix(primary, (0, 0, 0), 0.55)}
    chip = pill_sprite(brand["name"], font(40), (0, 0, 0, 120), (255, 255, 255, 255), 30, 16)
    media, bgm = find_media(assets, product["id"]), (bgm_path or find_bgm(assets))
    if scene_media is not None:  # 장면별 배경을 직접 지정 (None인 장면은 그라데이션)
        media = [Path(m) if m else None for m in scene_media]
    label = None
    has_media = any(media)
    if brand.get("ai_label") and (has_media or always_label):  # 배경 자료를 쓸 때(또는 요청 시) 고지 문구 표시
        label = pill_sprite(brand["ai_label"], font(34), (0, 0, 0, 150), (255, 255, 255, 235), 26, 14)
    shade = make_shade() if has_media else None

    # 장면별 프레임 수 (누적 시각을 반올림해 음성과 어긋나지 않게)
    edges, acc = [0], 0.0
    for d in durations:
        acc += d + PAD
        edges.append(round(acc * FPS))
    total_sec = edges[-1] / FPS

    cmd = [ffmpeg_exe(), "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-"]
    for v in voices:
        cmd += ["-i", str(v)]
    filt = [f"[{k + 1}:a]aresample=44100,aformat=channel_layouts=stereo,apad=whole_dur={d + PAD:.3f},"
            f"atrim=0:{(edges[k + 1] - edges[k]) / FPS:.4f},asetpts=PTS-STARTPTS[a{k}]" for k, d in enumerate(durations)]
    filt.append("".join(f"[a{k}]" for k in range(n)) + f"concat=n={n}:v=0:a=1[voice]")
    amap = "[voice]"
    if bgm:
        cmd += ["-stream_loop", "-1", "-i", str(bgm)]
        fo = max(0.0, total_sec - 1.2)
        filt.append(f"[{n + 1}:a]aresample=44100,aformat=channel_layouts=stereo,volume={bgm_volume:.3f},"
                    f"atrim=0:{total_sec:.3f},afade=t=in:d=0.6,afade=t=out:st={fo:.3f}:d=1.2[bgm]")
        # 목소리가 나오는 동안 음악을 자동으로 줄인다 (사이드체인 덕킹)
        filt.append("[voice]asplit=2[vmain][vkey]")
        filt.append("[bgm][vkey]sidechaincompress=threshold=0.015:ratio=8:attack=15:release=450:makeup=1[bgmd]")
        filt.append("[vmain][bgmd]amix=inputs=2:duration=first:normalize=0[mix]")
        amap = "[mix]"
    cmd += ["-filter_complex", ";".join(filt), "-map", "0:v", "-map", amap,
            "-c:v", "libx264", "-preset", os.environ.get("X264_PRESET", "veryfast"), "-crf", "20", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "160k", "-t", f"{total_sec:.3f}", "-movflags", "+faststart", str(out_path)]

    errlog = tempfile.TemporaryFile()
    enc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=errlog)
    prev_last, feat_no, bg = None, 0, None
    try:
        for i, scene in enumerate(scenes):
            kind = scene_kind(scene, i, n, product)
            if kind == "feature":
                feat_no += 1
            els = build_scene(kind, scene, feat_no, product, brand, col)
            caps = Captions(scene["narration"], durations[i], col["accent"])
            frames = edges[i + 1] - edges[i]
            dur = frames / FPS
            src = (media[i] if i < len(media) else None) if scene_media is not None else \
                (media[i % len(media)] if media else None)
            if src:
                bg = VideoBG(src, shade) if src.suffix.lower() in VIDEO_EXT else ImageBG(src, shade)
            else:
                bg = GradientBG(col, f"{product['id']}-{i}", 0.05 * (i % 3))
            static_at = max([e.done_at() for e in els if e.done_at() != math.inf] or [0])
            dynamic = [e for e in els if e.done_at() == math.inf]
            static_layer, still_saved = None, False
            for f in range(frames):
                t = f / FPS
                frame = (bg.frame(t, dur) if isinstance(bg, ImageBG) else bg.frame(t)).convert("RGBA")
                if static_layer is not None:
                    frame.alpha_composite(static_layer)
                    for e in dynamic:
                        e.draw(frame, t)
                else:
                    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                    for e in els:
                        if e.done_at() != math.inf:
                            e.draw(layer, t)
                    if t >= static_at:
                        static_layer = layer
                    frame.alpha_composite(layer)
                    for e in dynamic:
                        e.draw(frame, t)
                caps.draw(frame, t)
                draw_topbar(frame, chip, i, n, (f + 1) / frames, col, label)
                rgb = frame.convert("RGB")
                if prev_last is not None and t < XFADE:
                    rgb = Image.blend(prev_last, rgb, out_cubic(t / XFADE))
                if not still_saved and (t >= min(dur - 0.4, max(static_at, 1.6)) or f == frames - 1):
                    rgb.save(workdir / f"scene_{i:02d}.png")  # 품질 검사·썸네일용 정지 화면
                    still_saved = True
                enc.stdin.write(rgb.tobytes())
            prev_last = rgb
            bg.close()
            bg = None
            if log:
                log(f"장면 {i + 1}/{n} 렌더링")
        enc.stdin.close()
        code = enc.wait()
    except BaseException:
        enc.kill()
        enc.wait()
        raise
    finally:
        if bg is not None:
            bg.close()
    if code != 0:
        errlog.seek(0)
        raise RuntimeError("ffmpeg 인코딩 실패: " + errlog.read().decode("utf-8", "replace")[-400:])
    return {"seconds": total_sec, "background": "media" if has_media else "gradient", "bgm": bool(bgm)}
