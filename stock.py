"""무료 스톡 영상 검색·다운로드 (장면 배경용)

Pixabay(PIXABAY_API_KEY) 또는 Pexels(PEXELS_API_KEY) 중 키가 있는 쪽을 쓴다. Pixabay를 먼저 쓴다.
두 곳 모두 무료이며 상업적으로 써도 된다. 출처·촬영자는 의무는 아니지만 설명란에 적어 준다.
키는 Secrets에만 둔다.
"""
import concurrent.futures as cf
import json
import urllib.parse
import urllib.request
from pathlib import Path

APIS = ["https://api.pexels.com/v1/videos/search", "https://api.pexels.com/videos/search"]  # 새 주소 → 예전 주소
MAX_BYTES = 45 * 1024 * 1024   # 장면 하나 배경 영상 최대 크기
TIMEOUT = 25


def _secret(name):
    try:
        import streamlit as st
        return str(st.secrets.get(name, "") or "").strip()
    except Exception:
        import os
        return os.environ.get(name, "").strip()


def provider():
    if _secret("PIXABAY_API_KEY"):
        return "Pixabay"
    if _secret("PEXELS_API_KEY"):
        return "Pexels"
    return ""


def configured():
    return bool(provider())


PIXABAY_API = "https://pixabay.com/api/videos/"


def search_pixabay(query, key, used=(), per_page=10):
    """Pixabay는 세로 검색 옵션이 없어서 세로 영상을 먼저 고르고, 없으면 가로 영상(가운데를 세로로 잘라 씀)"""
    q = urllib.parse.urlencode({"key": key, "q": query[:100], "per_page": per_page, "safesearch": "true",
                                "video_type": "film"})
    hits = _get_json(f"{PIXABAY_API}?{q}", None).get("hits", [])
    best = []
    for h in hits:
        if h.get("id") in used or not (3 <= h.get("duration", 0) <= 60):
            continue
        files = [f for f in (h.get("videos") or {}).values() if f.get("url") and f.get("width") and f.get("height")
                 and (f.get("size") or 0) <= MAX_BYTES]
        if not files:
            continue
        portrait = files[0]["height"] > files[0]["width"]
        files.sort(key=lambda f: -f["height"])  # 큰 해상도부터 (크기 제한 안에서)
        f = files[0]
        best.append((not portrait, f["height"] < 1080, {
            "id": h["id"], "url": f["url"], "width": f["width"], "height": f["height"],
            "author": h.get("user", ""), "page": h.get("pageURL", ""), "source": "Pixabay"}))
    if not best:
        return None
    best.sort(key=lambda b: (b[0], b[1]))  # 세로 우선, 1080 이상 우선 (그 안에서는 검색 순위 유지)
    return best[0][2]


def _get_json(url, key):
    headers = {"User-Agent": "shortform-helper/1.0"}
    if key:
        headers["Authorization"] = key
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode("utf-8"))


def _best_file(video):
    """세로 영상 파일 중 1080 너비에 가장 가까운 것 (너무 큰 4K는 피함)"""
    files = [f for f in video.get("video_files", [])
             if f.get("link") and f.get("width") and f.get("height") and f["height"] > f["width"]]
    if not files:
        return None
    files.sort(key=lambda f: (f["width"] > 1440, abs(f["width"] - 1080)))
    return files[0]


def search_pexels(query, key, used=(), per_page=8):
    """검색어로 세로 영상 하나를 고른다. 이미 쓴 영상은 피한다. 반환: dict 또는 None"""
    q = urllib.parse.urlencode({"query": query, "orientation": "portrait", "per_page": per_page, "size": "medium"})
    import urllib.error
    data = {}
    for api in APIS:
        try:
            data = _get_json(f"{api}?{q}", key)
            break
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
    for v in data.get("videos", []):
        if v.get("id") in used or not (3 <= v.get("duration", 0) <= 60):
            continue
        f = _best_file(v)
        if f:
            return {"id": v["id"], "url": f["link"], "width": f["width"], "height": f["height"],
                    "author": (v.get("user") or {}).get("name", ""), "page": v.get("url", ""), "source": "Pexels"}
    return None


def search(query, key, used=()):
    if provider() == "Pixabay":
        return search_pixabay(query, key, used)
    return search_pexels(query, key, used)


def download(url, path):
    req = urllib.request.Request(url, headers={"User-Agent": "shortform-helper/1.0"})
    size = 0
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r, open(path, "wb") as out:
        while True:
            chunk = r.read(1 << 16)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_BYTES:
                raise ValueError("영상 파일이 너무 커요")
            out.write(chunk)
    return path


def fetch_backgrounds(queries, folder, fallback="", progress=None):
    """장면별 검색어 → 장면별 배경 영상 경로(없으면 None)와 출처 목록"""
    key = _secret("PIXABAY_API_KEY") or _secret("PEXELS_API_KEY")
    folder = Path(folder)
    picks, used = [], set()
    for i, q in enumerate(queries):
        if progress:
            progress(i, len(queries))
        hit = None
        for query in [q, fallback]:  # 결과가 없으면 제품 종류 같은 넓은 검색어로 한 번 더
            if not query or hit:
                continue
            try:
                hit = search(query, key, used)
            except Exception:
                hit = None
        if hit:
            used.add(hit["id"])
        picks.append(hit)

    def _dl(args):
        i, hit = args
        if not hit:
            return i, None
        try:
            return i, download(hit["url"], folder / f"bg_{i:02d}.mp4")
        except Exception:
            return i, None

    paths = [None] * len(picks)
    with cf.ThreadPoolExecutor(max_workers=3) as ex:
        for i, p in ex.map(_dl, list(enumerate(picks))):
            paths[i] = p
    credits = [{"author": h["author"], "page": h["page"], "source": h.get("source", "")}
               for h, p in zip(picks, paths) if h and p]
    return paths, credits
