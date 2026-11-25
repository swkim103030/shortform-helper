"""영상 만들기 · 팀 잠금 · 유튜브 업로드 · 채널 댓글 게시 흐름 시험 (유튜브는 가짜, 실제 호출 없음)
실행: python tests/test_team.py
"""
import sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(HERE))
import ai, fake, youtube
from streamlit.testing.v1 import AppTest
ai._client = lambda: fake.Client()
fake.install_pexels()

LOG = []
youtube.configured = lambda: True
youtube.client = lambda: "YT"
youtube.channel = lambda yt: {"id": "UC1", "title": "하루빈 테스트", "uploads": "UU1"}
def _upload(yt, mp4, title, desc, tags, privacy="unlisted", synthetic=False):
    LOG.append(("upload", title, privacy, len(mp4), "AI로 만들었고" in desc, "Pixabay" in desc, tags[:2])); return "VID123", privacy
youtube.upload = _upload
THREADS = [{"thread_id": "T1", "video_id": "v", "author": "a", "text": "우유랑 몇 대 몇으로 섞어요?"},
           {"thread_id": "T2", "video_id": "v", "author": "b", "text": "아침에 한 잔씩 마시는데 진짜 편해요!"},
           {"thread_id": "T3", "video_id": "v", "author": "c", "text": "주문한 지 일주일 넘었는데 아직 안 와요. 환불해 주세요"},
           {"thread_id": "T4", "video_id": "v", "author": "d", "text": "구독하고 우리 채널도 놀러오세요 http://spam.example"}]
youtube.recent_comments = lambda yt, ch, limit=15: THREADS
youtube.reply = lambda yt, tid, text: LOG.append(("reply", tid, text[:15]))
import instagram
instagram.configured = lambda: True
def _ig(mp4, caption, progress=None):
    LOG.append(("ig", len(mp4), "AI로 만들었고" in caption)); return "IG1", "https://www.instagram.com/reel/TEST/"
instagram.publish_reel = _ig
IG_THREADS = [{"thread_id": "C1", "author": "coffee_lover", "text": "원액 하나로 몇 잔 나와요?", "permalink": ""},
              {"thread_id": "C2", "author": "spam_bot", "text": "팔로우하면 선물 드려요 http://spam.example", "permalink": ""}]
instagram.recent_comments = lambda limit=15: (IG_THREADS, {"id": "1", "username": "jongbbu"})
instagram.reply = lambda cid, text: LOG.append(("ig_reply", cid, text[:15]))

def new(pw=True):
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120)
    if pw: at.secrets["TEAM_PASSWORD"] = "team1234"
    at.run(); assert not at.exception, at.exception; return at
def click(at, label):
    [b for b in at.button if label in b.label][0].click().run(); assert not at.exception, at.exception
def submit(at, label):  # form submit buttons
    click(at, label)
def texts(at):
    return {"err": [e.value[:90] for e in at.error], "ok": [s.value[:90] for s in at.success],
            "warn": [w.value[:70] for w in at.warning]}

# 1) 대본 → 영상 (잠금 상태)
at = new(); click(at, "예시 제품으로 채우기"); click(at, "AI로 대본 만들기"); click(at, "영상 만들기")
print("== 배경 옵션:", [r.options for r in at.radio if r.label == "배경"],
      "| 스톡 배경 장면", at.session_state["video"]["info"].get("stock_scenes"),
      "| 출처 표시", any("Pixabay" in c.value for c in at.caption))
print("   표에 배경 검색어 열:", "배경 검색어" in str(at.session_state["script"]["data"]["scenes"][0]) or "broll" in at.session_state["script"]["data"]["scenes"][0])
print("== 영상 만들기:", "video" in at.session_state, "| 영상 요소", len(at.get("video")),
      "| 받기 버튼", any("mp4" in d.label for d in at.get("download_button")) if at.get("download_button") else "?")
print("   잠금 안내:", any("팀원만" in c.value for c in at.caption))
print("   업로드 폼 보임?", any("유튜브에 올리기" in b.label for b in at.button))

# 2) 틀린 비밀번호 / 맞는 비밀번호
at.text_input[[t.label for t in at.text_input].index("팀 비밀번호")].set_value("wrong").run()
print("== 틀린 비번:", texts(at)["err"])
at.text_input[[t.label for t in at.text_input].index("팀 비밀번호")].set_value("team1234").run()
print("== 맞는 비번:", at.session_state["team_ok"])

# 3) 확인 체크 없이 업로드 → 막힘
submit(at, "유튜브에 올리기"); print("== 체크 없이 업로드:", texts(at)["err"], "| 업로드 호출", len(LOG))
# 4) 체크 후 업로드
[c for c in at.checkbox if "직접 확인" in c.label][0].check()
submit(at, "유튜브에 올리기"); print("== 체크 후 업로드(무음 장면 있음 → 막혀야 함):", texts(at)["err"], "| 호출", len(LOG))
# 음성 생성이 성공한 것처럼 바꿔서 다시
at.session_state["video"]["info"]["silent_scenes"] = 0
[c for c in at.checkbox if "직접 확인" in c.label][0].check()
submit(at, "유튜브에 올리기"); print("== 체크 후 업로드:", [o for o in texts(at)["ok"] if "업로드" in o], LOG[-1] if LOG else None)

# 4-1) 인스타: 체크 없이 → 막힘, 체크 후 → 게시
[b for b in at.button if "인스타에 올리기" in b.label][0].click().run()
print("== 인스타 체크 없이:", [e for e in texts(at)["err"] if "체크" in e][:1], "| 호출", sum(1 for l in LOG if l[0] == "ig"))
[c for c in at.checkbox if "인스타에 공개로" in c.label][0].check()
[b for b in at.button if "인스타에 올리기" in b.label][0].click().run()
print("== 인스타 체크 후:", [o for o in texts(at)["ok"] if "릴스" in o], [l for l in LOG if l[0] == "ig"])
# 5) 대본 수정 후 → 영상이 달라졌다는 안내
# (data_editor 직접 편집은 AppTest가 지원하지 않아 설정 변경으로 대신 확인)
at.color_picker[0].set_value("#123456").run()
print("== 설정 바꾼 뒤:", [i.value[:50] for i in at.info])

# 6) 비밀번호 미설정 서버
at2 = new(pw=False); print("== 비번 미설정:", any("관리자가 팀 비밀번호" in c.value for c in at2.caption))

# 7) 채널 댓글 불러오기 → AI 분류 → 게시
LOG.clear()
at = new(); at.text_input[[t.label for t in at.text_input].index("팀 비밀번호")].set_value("team1234").run()
click(at, "내 채널 새 댓글 불러오기")
print("== 불러온 댓글:", at.session_state["yt_comments_in"].count("\n") + 1, "| 브랜드칸:", repr(at.session_state["yt_brand"]))
at.text_input(key="yt_brand").set_value("하루빈 커피")
click(at, "분류하고")
posts = [b.label for b in at.button if "게시" in b.label]
print("   게시 버튼 수:", len(posts), "(문의·칭찬 2개 + 불만 직접 쓰기 1개)")
click(at, "이 답글 게시"); print("   게시 결과:", LOG, "| 성공 표시", texts(at)["ok"][:1])
# 7-1) 불만 댓글: AI 초안 없이 직접 쓴 답글 게시
print("   불만 안내:", [w for w in texts(at)["warn"] if "불만" in w][:1])
at.text_area(key="yt_human_3").set_value("불편을 드려 죄송합니다. 고객센터로 주문번호를 알려 주시면 확인해 드릴게요.").run()
[b for b in at.button if b.key == "yt_post_3"][0].click().run()
print("== 직접 쓴 답글 게시:", LOG[-1])
# 8) 위험 표현 답글 게시 막기
at.text_area(key="yt_reply_2").set_value("업계 최고의 커피예요!").run()
[b for b in at.button if b.key == "yt_post_2"][0].click().run()
print("== 위험 답글 게시:", texts(at)["err"], "| 게시 기록", len(LOG))

# 9) 인스타 댓글 불러오기 → AI 분류 → 인스타 답글 게시
LOG.clear()
at = new(); at.text_input[[t.label for t in at.text_input].index("팀 비밀번호")].set_value("team1234").run()
click(at, "내 인스타 새 댓글 불러오기")
print("== 인스타 댓글:", at.session_state["ig_comments_in"].split("\n"), "| 유튜브칸 영향 없음:",
      at.session_state.get("yt_comments_in", "") == "")
at.text_input(key="ig_brand").set_value("하루빈 커피")
[b for b in at.button if "분류하고" in b.label][1].click().run(); assert not at.exception, at.exception
ig_posts = [b.key for b in at.button if b.key and b.key.startswith("ig_post_")]
print("   인스타 게시 버튼:", ig_posts, "| 작성자 표시:", any("@coffee_lover" in m.value for m in at.markdown))
if ig_posts:
    [b for b in at.button if b.key == ig_posts[0]][0].click().run()
print("== 인스타 답글 게시:", LOG, "| 성공:", [o for o in texts(at)["ok"] if "인스타" in o])
