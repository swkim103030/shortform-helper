"""인스타 릴스 업로드 흐름 시험 (메타 서버 대신 가짜 응답) — 실행: python tests/test_instagram.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import instagram

CALLS = []
def run(statuses, publish_ok=True):
    seq = iter(statuses)
    def fake_call(method, path, **p):
        CALLS.append((method, path, {k: v for k, v in p.items() if k != "caption"}))
        if path == "me": return {"user_id": "17841", "username": "demo_cafe"}
        if path.endswith("/media"): return {"id": "C1"}
        if path == "C1": return {"status_code": next(seq), "status": "x"}
        if path.endswith("/media_publish"): return {"id": "M1"} if publish_ok else {}
        if path == "M1": return {"permalink": "https://www.instagram.com/reel/ABC/"}
    instagram._call = fake_call
    instagram.public_video_url = lambda b: "https://example.app/~/+/media/abc.mp4"
    instagram.time.sleep = lambda s: None
    return instagram.publish_reel(b"mp4", "캡션", wait_sec=999)

print("== 정상:", run(["IN_PROGRESS", "IN_PROGRESS", "FINISHED"]))
media = [c for c in CALLS if c[1].endswith("/media")][0][2]
print("   컨테이너 인자:", media["media_type"], media["video_url"], media["share_to_feed"])
for bad in ("ERROR", "EXPIRED"):
    try:
        run([bad]); print("== 실패해야 함", bad)
    except instagram.IGError as e:
        print(f"== 처리 실패({bad}):", e)
# 시간 초과
import itertools
instagram.time.time = iter(itertools.count(0, 100)).__next__
try:
    run(["IN_PROGRESS"] * 10)
except instagram.IGError as e:
    print("== 시간 초과:", e)
