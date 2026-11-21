"""AI 대본 → 음성(edge-tts) → 움직이는 쇼츠 영상(mp4)

render.py / tts.py는 PC용 자동화(sns-auto)에서 쓰던 코드를 그대로 가져왔다.
"""
import hashlib
import json
import re
import tempfile
import time
from pathlib import Path

import render
import tts

VOICES = {"여성 (선희)": "ko-KR-SunHiNeural", "남성 (인준)": "ko-KR-InJoonNeural"}


def _digits(s):
    return "".join(ch for ch in s if ch.isdigit())


def plan_scenes(scenes, req):
    """장면마다 화면 구성을 정한다. 마지막 장면은 가격과 숫자가 같거나 숫자가 없을 때만 '가격' 화면."""
    out, n = [], len(scenes)
    price_digits = _digits(req.get("price", ""))
    event = req.get("event", "").strip()
    for i, s in enumerate(scenes):
        cap = (s.get("caption") or "").strip() or (s.get("narration") or "")[:16]
        nar = (s.get("narration") or "").strip() or cap
        if i == 0:
            kind = "hook"
        elif i == n - 1:
            d = _digits(cap)
            if not d and price_digits:  # 마지막 장면엔 가격을 크게 보여 준다 (나레이션은 그대로)
                cap, d = req["price"].strip(), price_digits
            kind = "price" if (not d or d == price_digits) else "event"
        elif i == 1:
            kind = "intro"
        elif event and (event in cap or cap in event or re.search(r"할인|이벤트|증정|쿠폰", cap)):
            kind = "event"
        else:
            kind = "feature"
        out.append({"caption": cap, "narration": nar, "type": kind, "broll": (s.get("broll") or "").strip()})
    return out


CATEGORY_EN = {"커피": "coffee", "카페": "cafe", "음료": "drink", "디저트": "dessert", "빵": "bakery bread",
               "화장품": "skincare cosmetics", "옷": "fashion clothes", "의류": "fashion clothes", "음식": "food",
               "식품": "food", "꽃": "flowers", "운동": "fitness", "반려": "pet", "책": "books", "향수": "perfume"}


def fallback_query(req):
    cat = req.get("category", "")
    for k, v in CATEGORY_EN.items():
        if k in cat:
            return v
    return "lifestyle product"


def photo_order(n):
    """내 사진을 넣을 장면 순서: 제품 소개 → 마지막(가격) → 특징들 → 첫 장면"""
    order = [1, n - 1] + list(range(2, n - 1)) + [0]
    seen = []
    for i in order:
        if 0 <= i < n and i not in seen:
            seen.append(i)
    return seen


def assign_photos(n, photos):
    """장면 수 n, 사진 경로 목록 → 장면별 사진(없으면 None)"""
    slots = [None] * n
    for i, p in zip(photo_order(n), photos):
        slots[i] = p
    return slots


def make_video(script, req, colors, voice, ai_label=True, progress=None, stock=False, photos=None,
               music=None, music_file=None, music_seed=0, music_level=6):
    """music: bgm.MOODS의 분위기 이름(없으면 None), music_file: (파일명, bytes) 사용자가 올린 음악"""
    """mp4 바이트와 정보(dict)를 돌려준다. progress(비율 0~1, 문구)로 진행 상황을 알린다."""
    scenes = plan_scenes(script.get("scenes", []), req)
    if not scenes:
        raise ValueError("대본에 장면이 없어요.")
    say = progress or (lambda p, m: None)
    started = time.time()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        voices, durations, failed = [], [], 0
        for i, s in enumerate(scenes):
            say(0.05 + 0.25 * i / len(scenes), f"음성 만드는 중 ({i + 1}/{len(scenes)})")
            path = tmp / f"voice_{i:02d}.mp3"
            sec, ok, _ = tts.synthesize(s["narration"], voice, path)
            failed += not ok
            voices.append(path)
            durations.append(sec)
        scene_media, credits = None, []
        mine = []
        for k, (name, data) in enumerate(photos or []):  # 사용자가 올린 사진·영상 (임시 폴더에만 저장)
            path = tmp / f"mine_{k:02d}{Path(name).suffix.lower()}"
            path.write_bytes(data)
            mine.append(path)
        mine_slots = assign_photos(len(scenes), mine) if mine else [None] * len(scenes)
        need = [i for i, m in enumerate(mine_slots) if m is None]
        stock_slots = [None] * len(scenes)
        if stock and need:
            import stock as stock_mod
            say(0.3, "배경 영상 찾는 중...")
            got, credits = stock_mod.fetch_backgrounds(
                [scenes[i]["broll"] or fallback_query(req) for i in need], tmp, fallback_query(req),
                progress=lambda k, m: say(0.3 + 0.15 * k / m, f"배경 영상 찾는 중 ({k + 1}/{m})"))
            for i, g in zip(need, got):
                stock_slots[i] = g
        if mine or stock:
            scene_media = [m or s_ for m, s_ in zip(mine_slots, stock_slots)]
        bgm_path = None
        music_error = ""
        if music_file:
            name, data = music_file
            bgm_path = tmp / f"user_music{Path(name).suffix.lower() or '.mp3'}"
            bgm_path.write_bytes(data)
        elif music:
            import bgm as bgm_mod
            say(0.45, "배경음악 만드는 중...")
            seed = int.from_bytes(hashlib.sha1(json.dumps(script, ensure_ascii=False, sort_keys=True)
                                               .encode()).digest()[:4], "big") + music_seed
            try:
                bgm_path = bgm_mod.get(music, tempfile.gettempdir(), seed)
            except Exception as e:  # 음악을 못 만들어도 영상은 만든다
                bgm_path = None
                music_error = f"{type(e).__name__}: {e}"[:200]
        brand = {"name": req["brand"], "cta": req.get("cta", ""), "tagline": "",
                 "colors": {"primary": colors["primary"], "accent": colors["accent"]},
                 "ai_label": "AI 생성 영상" if ai_label else ""}
        product = {"id": "web", "name": req["name"], "event": req.get("event", "")}
        out = tmp / "short.mp4"
        n = len(scenes)

        def log(msg):  # "장면 k/n 렌더링"
            m = re.search(r"(\d+)/(\d+)", msg)
            if m:
                say(0.45 + 0.53 * int(m.group(1)) / n, f"영상 만드는 중 (장면 {m.group(1)}/{n})")

        info = render.render_video({"scenes": scenes}, product, brand, voices, durations, out, tmp,
                                   assets=None, log=log, always_label=ai_label,
                                   scene_media=scene_media, bgm_path=bgm_path,
                                   bgm_volume=0.1 * music_level)
        data = out.read_bytes()
        thumb = (tmp / "scene_00.png").read_bytes() if (tmp / "scene_00.png").exists() else None
    info.update(silent_scenes=failed, scenes=n, elapsed=time.time() - started, thumbnail=thumb, credits=credits,
                stock_scenes=sum(1 for m in stock_slots if m), photo_scenes=sum(1 for m in mine_slots if m),
                music_error=music_error)
    say(1.0, "완성!")
    return data, info
