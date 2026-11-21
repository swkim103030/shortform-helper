"""배경음악(BGM)을 코드로 직접 합성한다 — 외부 음원을 쓰지 않아 저작권 걱정이 없다.

분위기 3가지: 잔잔한 카페 / 경쾌한 / 감성적
화음 진행 + 베이스 + 건반·플럭 + 가벼운 드럼을 numpy로 만들고, 리버브와 저역 필터로 다듬는다.
"""
import subprocess
import wave
from pathlib import Path

import numpy as np

SR = 44100
MOODS = {"잔잔한 카페": "cafe", "경쾌한": "bright", "감성적": "warm"}


def _hz(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


def _env(n, attack, release, sustain_level=1.0):
    """attack/release(초) 를 가진 간단한 엔벨로프"""
    a = max(1, int(attack * SR))
    r = max(1, int(release * SR))
    e = np.full(n, sustain_level, dtype=np.float32)
    e[:min(a, n)] = np.linspace(0, sustain_level, min(a, n))
    if r < n:
        e[-r:] *= np.linspace(1, 0, r)
    return e


def _decay(n, tau):
    return np.exp(-np.arange(n) / (tau * SR)).astype(np.float32)


def epiano(f, dur, vel=0.5):
    """로즈 느낌 전자 피아노: 사인 + 배음, 부드러운 감쇠와 트레몰로"""
    n = int(dur * SR)
    t = np.arange(n) / SR
    tone = (np.sin(2 * np.pi * f * t) + 0.35 * np.sin(2 * np.pi * 2 * f * t) * _decay(n, 0.25)
            + 0.12 * np.sin(2 * np.pi * 3.01 * f * t) * _decay(n, 0.12)
            + 0.08 * np.sin(2 * np.pi * 4.02 * f * t) * _decay(n, 0.06))
    trem = 1 + 0.08 * np.sin(2 * np.pi * 4.5 * t)
    return (tone * trem * _decay(n, 1.6) * _env(n, 0.005, 0.15) * vel).astype(np.float32)


def pad(f, dur, vel=0.25):
    """부드러운 패드: 살짝 어긋난 톱니파 여러 개를 저역 통과"""
    n = int(dur * SR)
    t = np.arange(n) / SR
    s = np.zeros(n, dtype=np.float32)
    for d in (-0.08, 0.0, 0.07):
        ph = (f * (1 + d / 100) * t) % 1.0
        s += (2 * ph - 1)
    s = _lowpass(s / 3, 900)
    return (s * _env(n, 0.6, 0.8) * vel).astype(np.float32)


def pluck(f, dur, vel=0.4, bright=0.5):
    """Karplus-Strong 현 뜯는 소리"""
    n = int(dur * SR)
    p = max(2, int(SR / f))
    rng = np.random.default_rng(int(f * 100))
    buf = rng.uniform(-1, 1, p).astype(np.float32)
    out = np.zeros(n, dtype=np.float32)
    damp = 0.996 - (1 - bright) * 0.006
    for i in range(n):
        out[i] = buf[i % p]
        buf[i % p] = damp * 0.5 * (buf[i % p] + buf[(i + 1) % p])
    return out * vel * _env(n, 0.002, 0.05)


def bass(f, dur, vel=0.5):
    vel *= 0.6
    n = int(dur * SR)
    t = np.arange(n) / SR
    s = np.sin(2 * np.pi * f * t) + 0.25 * np.sin(2 * np.pi * 2 * f * t)
    return (s * _env(n, 0.01, 0.08) * _decay(n, 0.9) * vel).astype(np.float32)


def kick(vel=0.8):
    vel *= 0.45
    n = int(0.35 * SR)
    t = np.arange(n) / SR
    f = 110 * np.exp(-t * 18) + 45
    ph = 2 * np.pi * np.cumsum(f) / SR
    return (np.sin(ph) * _decay(n, 0.12) * vel).astype(np.float32)


def snare(vel=0.4, brush=False):
    n = int(0.25 * SR)
    rng = np.random.default_rng(7)
    noise = rng.uniform(-1, 1, n).astype(np.float32)
    noise = _highpass(noise, 1500 if not brush else 2500)
    t = np.arange(n) / SR
    body = np.sin(2 * np.pi * 190 * t) * _decay(n, 0.04)
    return ((noise * _decay(n, 0.09 if not brush else 0.06) + 0.4 * body) * vel).astype(np.float32)


def hat(vel=0.15):
    n = int(0.06 * SR)
    rng = np.random.default_rng(3)
    noise = _highpass(rng.uniform(-1, 1, n).astype(np.float32), 7000)
    return (noise * _decay(n, 0.015) * vel).astype(np.float32)


def _lowpass(x, fc):
    from scipy.signal import butter, sosfilt
    sos = butter(2, fc, btype="low", fs=SR, output="sos")
    return sosfilt(sos, x).astype(np.float32)


def _highpass(x, fc):
    from scipy.signal import butter, sosfilt
    sos = butter(2, fc, btype="high", fs=SR, output="sos")
    return sosfilt(sos, x).astype(np.float32)


def _master_eq(x):
    """40Hz 아래는 걷어 내고, 1.5kHz 위를 조금 올려 작은 스피커에서도 들리게"""
    x = _highpass(x, 45)
    return (x + 0.6 * _highpass(x, 1500)).astype(np.float32)


def _reverb(x, seconds=1.6, mix=0.25):
    """지수 감쇠 노이즈를 임펄스 응답으로 쓰는 간단한 리버브"""
    from scipy.signal import fftconvolve
    n = int(seconds * SR)
    rng = np.random.default_rng(11)
    ir = rng.standard_normal(n).astype(np.float32) * _decay(n, seconds / 5)
    ir = _lowpass(ir, 5000)
    ir /= np.sqrt(np.sum(ir ** 2)) + 1e-9
    wet = fftconvolve(x, ir)[:len(x)].astype(np.float32)
    return (1 - mix) * x + mix * wet


def _place(track, sound, start, gain=1.0):
    i = int(start * SR)
    if i >= len(track):
        return
    j = min(len(track), i + len(sound))
    track[i:j] += sound[:j - i] * gain


# 화음: (근음 midi, 화음 구성음 midi 목록)
PROGRESSION_SETS = {
    "cafe": [
        [(53, [57, 60, 64, 65]), (52, [55, 59, 62, 64]), (50, [53, 57, 60, 62]), (48, [52, 55, 59, 60])],  # Fmaj7 Em7 Dm7 Cmaj7
        [(50, [53, 57, 60, 64]), (55, [53, 57, 59, 62]), (48, [52, 55, 59, 62]), (45, [52, 55, 60, 64])],  # Dm9 G13 Cmaj9 Am7
        [(53, [57, 60, 64, 67]), (55, [57, 59, 62, 65]), (52, [55, 59, 62, 67]), (45, [55, 60, 64, 67])],  # Fmaj9 G6 Em7 Am9
    ],
    "bright": [
        [(50, [62, 66, 69]), (45, [61, 64, 69]), (47, [62, 66, 71]), (43, [62, 67, 71])],  # D A Bm G
        [(48, [60, 64, 67]), (43, [59, 62, 67]), (45, [60, 64, 69]), (41, [60, 65, 69])],  # C G Am F
        [(43, [62, 67, 71]), (50, [62, 66, 69]), (40, [64, 67, 71]), (48, [64, 67, 72])],  # G D Em C
    ],
    "warm": [
        [(45, [60, 64, 69]), (41, [60, 65, 69]), (48, [60, 64, 67]), (43, [59, 62, 67])],  # Am F C G
        [(41, [60, 65, 69]), (43, [59, 62, 67]), (40, [59, 64, 67]), (45, [60, 64, 69])],  # F G Em Am
        [(48, [60, 64, 67]), (40, [59, 64, 67]), (45, [60, 64, 69]), (41, [60, 65, 69])],  # C Em Am F
    ],
}
TEMPO = {"cafe": 80, "bright": 112, "warm": 70}


def compose(mood="cafe", bars=8, seed=0):
    """bars 마디(4/4) 길이의 스테레오 음악. seed가 다르면 조성·빠르기·화음 진행·리듬이 달라진다"""
    rng = np.random.default_rng(seed)
    sets = PROGRESSION_SETS[mood]
    shift = int(rng.integers(-3, 4))  # 조 옮기기 (반음 -3 ~ +3)
    prog = [(r + shift, [m + shift for m in c]) for r, c in sets[int(rng.integers(len(sets)))]]
    if rng.random() < 0.5:  # 진행 순서를 한 칸 돌려 시작 화음을 바꾼다
        prog = prog[1:] + prog[:1]
    bpm = TEMPO[mood] * float(rng.uniform(0.93, 1.07))
    swing = float(rng.uniform(0.0, 0.06)) if mood == "cafe" else 0.0
    arp_dir = 1 if rng.random() < 0.5 else -1
    beat = 60 / bpm
    bar = 4 * beat
    total = bars * bar
    n = int(total * SR) + SR
    L = np.zeros(n, dtype=np.float32)
    R = np.zeros(n, dtype=np.float32)

    for b in range(bars):
        root, chord = prog[b % len(prog)]
        t0 = b * bar
        if mood == "cafe":
            for k, m in enumerate(chord):  # 살짝 흩어 치는 로즈 화음, 2박마다
                for half in (0, 2):
                    _place(L, epiano(_hz(m), bar / 2 + 0.3, 0.16), t0 + half * beat + k * 0.012, 0.9 if k % 2 else 1.0)
                    _place(R, epiano(_hz(m), bar / 2 + 0.3, 0.16), t0 + half * beat + k * 0.015, 1.0 if k % 2 else 0.9)
            _place(L, bass(_hz(root - 12), beat * 1.8, 0.45), t0); _place(R, bass(_hz(root - 12), beat * 1.8, 0.45), t0)
            _place(L, bass(_hz(root - 5), beat * 1.5, 0.35), t0 + 2.5 * beat); _place(R, bass(_hz(root - 5), beat * 1.5, 0.35), t0 + 2.5 * beat)
            for k in range(4):  # 느슨한 붐뱁 비트
                tt = t0 + k * beat
                if k in (0, 2) or (k == 2 and b % 2):
                    _place(L, kick(0.55), tt + (0.5 * beat if k == 2 and b % 2 else 0)); _place(R, kick(0.55), tt + (0.5 * beat if k == 2 and b % 2 else 0))
                if k in (1, 3):
                    s = snare(0.22, brush=True); _place(L, s, tt + 0.02); _place(R, s, tt + 0.02)
                for h in (0, 0.5):
                    _place(L if h else R, hat(0.06), tt + h * beat + (swing * beat if h else 0))
        elif mood == "bright":
            arp = chord + [chord[0] + 12]
            for k in range(8):  # 8분음표 플럭 아르페지오
                m = arp[(arp_dir * k * 2 + b) % len(arp)]
                pl = _lowpass(pluck(_hz(m), beat, 0.55, 0.45), 5000)
                _place(L, pl, t0 + k * beat / 2, 1.0 if k % 2 else 0.6)
                _place(R, pl, t0 + k * beat / 2, 0.6 if k % 2 else 1.0)
            for m in chord:
                p_ = pad(_hz(m), bar + 0.4, 0.07); _place(L, p_, t0); _place(R, p_, t0)
            for k in range(4):
                tt = t0 + k * beat
                _place(L, bass(_hz(root - 12), beat * 0.9, 0.3), tt); _place(R, bass(_hz(root - 12), beat * 0.9, 0.3), tt)
                if k in (0, 2):
                    _place(L, kick(0.5), tt); _place(R, kick(0.5), tt)
                if k in (1, 3):
                    s = snare(0.16, brush=True); _place(L, s, tt); _place(R, s, tt)
                for h in (0.5,):
                    _place(L, hat(0.05), tt + h * beat); _place(R, hat(0.04), tt + h * beat)
        else:  # warm: 피아노 아르페지오 + 패드, 드럼 없음
            arp = [chord[0], chord[1], chord[2], chord[1] + 12, chord[2], chord[1]]
            if arp_dir < 0:
                arp = [chord[2], chord[1] + 12, chord[2], chord[1], chord[0], chord[1]]
            step = bar / 6
            for k, m in enumerate(arp):
                pn = epiano(_hz(m), step * 3, 0.2)
                _place(L, pn, t0 + k * step, 1.0 if k % 2 else 0.7)
                _place(R, pn, t0 + k * step, 0.7 if k % 2 else 1.0)
            for m in chord:
                p_ = pad(_hz(m - 12), bar + 0.6, 0.06); _place(L, p_, t0); _place(R, p_, t0)
            _place(L, bass(_hz(root - 12), bar, 0.35), t0); _place(R, bass(_hz(root - 12), bar, 0.35), t0)

    # 꼬리(리버브 잔향)를 앞쪽에 겹쳐 이음매 없이 반복되게 한다
    tail = n - int(total * SR)
    L[:tail] += L[int(total * SR):]
    R[:tail] += R[int(total * SR):]
    L, R = L[:int(total * SR)], R[:int(total * SR)]
    if mood == "cafe":  # 로파이 느낌: 고역을 조금 깎는다
        L, R = _lowpass(L, 6500), _lowpass(R, 6500)
    L, R = _reverb(L, 1.8, 0.22), _reverb(R, 1.9, 0.22)
    L, R = _master_eq(L), _master_eq(R)
    st = np.stack([L, R], axis=1)
    st /= (np.max(np.abs(st)) + 1e-9) / 0.85
    return st


def save(st, path):
    """wav로 쓰고, 확장자가 mp3면 ffmpeg로 변환한다"""
    path = Path(path)
    wav = path.with_suffix(".wav")
    pcm = (np.clip(st, -1, 1) * 32767).astype(np.int16)
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    if path.suffix.lower() == ".mp3":
        from tts import ffmpeg_exe
        subprocess.run([ffmpeg_exe(), "-y", "-loglevel", "error", "-i", str(wav), "-b:a", "160k", str(path)], check=True)
        wav.unlink()
    return path


_CACHE = {}


def get(mood, folder, seed=0):
    """분위기·seed별 BGM 파일 경로 (같은 영상은 같은 곡, 다른 영상은 다른 곡)"""
    key = MOODS.get(mood, mood)
    seed = int(seed) % 100000
    p = Path(folder) / f"bgm_{key}_{seed}.wav"
    if (key, seed) in _CACHE and Path(_CACHE[(key, seed)]).exists():
        return _CACHE[(key, seed)]
    save(compose(key, bars=8, seed=seed), p)
    _CACHE[(key, seed)] = p
    return p
