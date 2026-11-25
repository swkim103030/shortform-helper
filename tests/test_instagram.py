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

# 댓글 불러오기: 내 댓글·이미 답한 댓글은 빼고, 댓글 없는 게시물은 건너뛴다
def fake_call2(method, path, **p):
    if path == "me": return {"user_id": "99", "username": "jongbbu"}
    if path == "99/media": return {"data": [{"id": "M1", "comments_count": 3, "permalink": "p1"}, {"id": "M2", "comments_count": 0}]}
    if path == "M1/comments": return {"data": [
        {"id": "c1", "text": "몇 잔 나와요?", "username": "a"},
        {"id": "c2", "text": "고마워요", "username": "jongbbu"},
        {"id": "c3", "text": "배송 빨라요", "username": "b", "replies": {"data": [{"username": "jongbbu"}]}}]}
    if path == "c1/replies": CALLS.append((path, p["message"])); return {"id": "r1"}
    raise AssertionError(path)
CALLS = []
instagram._call = fake_call2
instagram._api = lambda: instagram.IG_API
instagram._secret = lambda n: ""
got, acct = instagram.recent_comments()
print("== 인스타 댓글 불러오기:", [(c["thread_id"], c["author"]) for c in got], acct["username"])
instagram.reply("c1", "원액 1에 물 3이에요")
print("== 인스타 답글:", CALLS)
