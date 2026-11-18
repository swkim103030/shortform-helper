"""AI를 가짜 응답으로 바꿔 화면 흐름과 예외 처리를 시험한다 (실제 API 호출 없음)
실행: python tests/test_app.py
"""
import sys, os
from pathlib import Path
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(HERE))
import ai, fake
from streamlit.testing.v1 import AppTest
ai._client = lambda: fake.Client()
APP = str(ROOT / 'app.py')
def new():
    at = AppTest.from_file(APP, default_timeout=30); at.run(); assert not at.exception, at.exception; return at
def btn(at, label):
    [b for b in at.button if label in b.label][0].click().run(); assert not at.exception, at.exception
def show(at, tag):
    print(f"== {tag}"); 
    for e in at.error: print("  ERROR:", e.value[:160].replace("\n"," | "))
    for c in at.code:
        if "종료 사유" in c.value or "API 오류" in c.value: print("  원인:", c.value.replace("\n"," || ")[:300])
    for w in at.warning: print("  WARN:", w.value[:200].replace("\n"," | "))
    for s in at.success: print("  OK:", s.value[:100])
    for i in at.info: print("  INFO:", i.value[:100])

# 1) 빈 입력
at = new(); btn(at, "AI로 대본 만들기"); show(at, "빈 입력"); print("  AI 호출", len(fake.CALLS))
# 2) 예시 + 정상
at = new(); btn(at, "예시 제품으로 채우기"); btn(at, "AI로 대본 만들기"); show(at, "정상 생성")
print("  제목:", [c.value for c in at.code][:3]); print("  장면표 있음:", "장면별 대본" in " ".join(m.value for m in at.markdown))
# 3) 입력을 바꾸면 프롬프트도 바뀌는지 (AI에 실제로 입력이 전달되는지)
import prompts
p1 = prompts.script_prompt(dict(brand="A", name="말차", category="음료", price="9,000원", features=["x"], target="t", event="", seconds=30, scenes_hint=6, tone="감성적", style="공감형", banned=[], cta="c"))
print("== 입력 반영:", "말차" in p1 and "따뜻하고 감성적" in p1 and "불편에서 시작" in p1)
# 4) 위험 표현·지어낸 숫자
fake.MODE["script"] = "bad"; at = new(); btn(at, "예시 제품으로 채우기"); btn(at, "AI로 대본 만들기"); show(at, "위험 표현 결과"); fake.MODE["script"] = "normal"
# 5) 개인정보 입력
at = new(); btn(at, "예시 제품으로 채우기"); at.text_input(key="in_event").set_value("문의 010-1234-5678"); btn(at, "AI로 대본 만들기"); show(at, "개인정보 입력")
# 6) API 오류들
for f in (429, 401, "garbage", "truncated", "empty", "fenced"):
    fake.MODE["fail"] = f; at = new(); btn(at, "예시 제품으로 채우기"); btn(at, "AI로 대본 만들기"); show(at, f"오류 {f}")
fake.MODE["fail"] = 404; fake.CALLS.clear(); at = new(); btn(at, "예시 제품으로 채우기"); btn(at, "AI로 대본 만들기"); show(at, "모델 404 → 대체 모델"); print("  호출한 모델:", fake.CALLS)
fake.MODE["fail"] = 503; fake.CALLS.clear(); at = new(); btn(at, "예시 제품으로 채우기"); btn(at, "AI로 대본 만들기"); show(at, "첫 모델 503 → 다른 모델"); print("  호출한 모델:", fake.CALLS)
fake.MODE["fail"] = "allgone"; fake.CALLS.clear(); at = new(); btn(at, "예시 제품으로 채우기"); btn(at, "AI로 대본 만들기"); show(at, "기본 모델 전부 없음 → 목록 조회"); print("  호출한 모델:", fake.CALLS)
fake.MODE["fail"] = None
# 7) 키 없음
import importlib
ai2 = importlib.reload(ai)  # 원래 _client 복원 (키 없음 상태)
at = new(); btn(at, "예시 제품으로 채우기"); btn(at, "AI로 대본 만들기"); show(at, "키 없음")
ai2._client = lambda: fake.Client()
# 8) 댓글
at = new(); btn(at, "예시 댓글로 채우기")
at.text_area(key="comments_in").set_value(at.session_state["comments_in"] + "\n제 번호 010-9999-8888로 연락 주세요")
[b for b in at.button if "분류하고" in b.label][0].click().run(); assert not at.exception, at.exception
show(at, "댓글"); print("  지표:", [(m.label, m.value) for m in at.metric])
print("  답글칸:", [t.value[:25] for t in at.text_area if t.key and t.key.startswith('reply_')])
print("  캡션:", [c.value[:50] for c in at.caption if '숨겼' in c.value or '가림' in c.value])
# 9) 호출 제한
at = new(); btn(at, "예시 제품으로 채우기")
for i in range(16): btn(at, "AI로 대본 만들기")
show(at, "16번째 호출")
