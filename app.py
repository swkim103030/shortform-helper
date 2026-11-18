"""숏폼 마케팅 도우미 — 제품 정보를 넣으면 생성형 AI가 쇼츠 대본·제목·SNS 문구·댓글 답글 초안을 만든다.

실행: streamlit run app.py
필요한 비밀 설정 (.streamlit/secrets.toml 또는 Streamlit Cloud의 Secrets):
    GEMINI_API_KEY = "..."
    GEMINI_MODEL = "gemini-flash-latest"   # 선택
"""
import json
import time

import streamlit as st

import ai
import checks
import prompts

st.set_page_config(page_title="숏폼 마케팅 도우미", page_icon="🎬", layout="centered")

MAX_CALLS = 15            # 한 사람(세션)이 10분 동안 쓸 수 있는 AI 호출 수 (무료 한도 보호)
WINDOW_SEC = 600
MAX_COMMENTS = 15
SAMPLE = {
    "brand": "하루빈 커피", "name": "콜드브루 원액 500ml", "category": "커피", "price": "12,900원",
    "features": "18시간 저온 추출\n물이나 우유에 타기만 하면 완성\n냉장 2주 보관",
    "target": "아침마다 바쁜 직장인", "event": "첫 구매 10% 할인",
}
SAMPLE_COMMENTS = """우유랑 몇 대 몇으로 섞어요?
아침에 한 잔씩 마시는데 진짜 편해요!
주문한 지 일주일 넘었는데 아직 안 와요. 환불해 주세요
구독하고 우리 채널도 놀러오세요 http://spam.example"""

ss = st.session_state
ss.setdefault("calls", [])
for k, v in SAMPLE.items():
    ss.setdefault(f"in_{k}", "")


def allow_call():
    now = time.time()
    ss.calls = [t for t in ss.calls if now - t < WINDOW_SEC]
    if len(ss.calls) >= MAX_CALLS:
        wait = int(WINDOW_SEC - (now - ss.calls[0])) // 60 + 1
        st.warning(f"잠시만요! 짧은 시간에 요청이 많아요. 약 {wait}분 뒤에 다시 시도해 주세요.")
        return False
    ss.calls.append(now)
    return True


def fill_sample():
    for k, v in SAMPLE.items():
        ss[f"in_{k}"] = v


# ───────── 사이드바: 브랜드 설정 ─────────
with st.sidebar:
    st.header("⚙️ 브랜드 설정")
    tone = st.selectbox("말투", list(prompts.TONES), key="tone")
    cta = st.text_input("행동 유도 문구", "프로필 링크에서 확인하세요!", max_chars=40)
    banned_raw = st.text_input("금지 표현 (쉼표로 구분)", "최고, 1등, 무조건, 완벽", max_chars=200)
    banned = [w.strip() for w in banned_raw.split(",") if w.strip()]
    st.divider()
    st.caption("🔒 개인정보(전화번호, 이메일, 주소 등)는 입력하지 마세요. 입력된 내용은 AI 처리를 위해 Google Gemini API로 전송됩니다.")
    st.caption("⚠️ AI 결과는 초안입니다. 게시 전에 사실과 표현을 꼭 확인하세요.")

st.title("🎬 숏폼 마케팅 도우미")
st.write("제품 정보를 넣으면 AI가 **쇼츠 대본, 제목, 해시태그, 인스타 글**을 만들고, **댓글 답글 초안**까지 써 드려요. "
         "광고에 쓰면 위험한 표현은 자동으로 찾아 알려 드려요.")

tab1, tab2, tab3 = st.tabs(["📝 쇼츠 대본 만들기", "💬 댓글 응대", "ℹ️ 사용 안내"])

# ───────── 탭 1: 쇼츠 대본 ─────────
with tab1:
    st.button("예시 제품으로 채우기", on_click=fill_sample)
    with st.form("script_form"):
        c1, c2 = st.columns(2)
        brand = c1.text_input("브랜드 이름 *", key="in_brand", max_chars=30)
        name = c2.text_input("제품 이름 *", key="in_name", max_chars=40)
        c3, c4 = st.columns(2)
        category = c3.text_input("종류", key="in_category", max_chars=20, placeholder="예: 커피, 화장품, 카페 메뉴")
        price = c4.text_input("가격", key="in_price", max_chars=20, placeholder="예: 12,900원")
        features = st.text_area("특징 * (한 줄에 하나씩, 사실만)", key="in_features", max_chars=400, height=110)
        target = st.text_input("추천 대상", key="in_target", max_chars=40, placeholder="예: 아침마다 바쁜 직장인")
        event = st.text_input("이벤트 (없으면 비워 두세요)", key="in_event", max_chars=40)
        c5, c6 = st.columns(2)
        style = c5.radio("구성 방식", list(prompts.STYLES), horizontal=True)
        seconds = c6.select_slider("목표 길이(초)", [15, 30, 45, 60], value=30)
        submitted = st.form_submit_button("✨ AI로 대본 만들기", type="primary", width="stretch")

    if submitted:
        feats = [f.strip() for f in features.splitlines() if f.strip()]
        user_text = " ".join([brand, name, category, price, *feats, target, event])
        if not brand.strip() or not name.strip() or not feats:
            st.error("브랜드 이름, 제품 이름, 특징(1개 이상)은 꼭 입력해 주세요.")
        elif checks.find_personal(user_text):
            st.error("입력에 개인정보로 보이는 내용(" + ", ".join(checks.find_personal(user_text)) +
                     ")이 있어요. 지우고 다시 시도해 주세요.")
        elif allow_call():
            req = dict(brand=brand.strip(), name=name.strip(), category=category.strip() or "제품",
                       price=price.strip() or "미정", features=feats, target=target.strip() or "누구나",
                       event=event.strip(), seconds=seconds, scenes_hint=max(4, seconds // 5),
                       tone=tone, style=style, banned=banned, cta=cta.strip())
            with st.spinner("AI가 대본을 쓰고 있어요... (10~20초)"):
                try:
                    data, model = ai.generate_json(prompts.SCRIPT_SYSTEM, prompts.script_prompt(req),
                                                   ["titles", "scenes", "description", "hashtags", "instagram"])
                    ss.script = {"data": data, "model": model, "req": req,
                                 "check": checks.check_script(data, f"{user_text} {seconds}", banned, seconds)}
                except ai.AIError as e:
                    ss.pop("script", None)
                    st.error(f"😥 {e}")

    if "script" in ss:
        res, chk, req = ss.script["data"], ss.script["check"], ss.script["req"]
        st.divider()
        st.subheader(f"결과: {req['name']}")
        if chk["errors"]:
            st.error("**게시 전에 꼭 고쳐야 할 점**\n\n" + "\n".join(f"- {e}" for e in chk["errors"]))
        if chk["warnings"]:
            st.warning("**확인해 보면 좋은 점**\n\n" + "\n".join(f"- {w}" for w in chk["warnings"]))
        if not chk["errors"] and not chk["warnings"]:
            st.success("자동 검사에서 문제를 찾지 못했어요. 그래도 사실 여부는 직접 확인해 주세요.")

        st.markdown("**📌 제목 후보**")
        for t in res.get("titles", [])[:3]:
            st.code(t, language=None)

        st.markdown(f"**🎬 장면별 대본** · 예상 약 {chk['estimated_sec']:.0f}초")
        rows = [{"장면": i + 1, "화면 문구": s.get("caption", ""), "나레이션": s.get("narration", "")}
                for i, s in enumerate(res.get("scenes", []))]
        st.dataframe(rows, hide_index=True, width="stretch")
        if res.get("thumbnail_text"):
            st.markdown(f"**🖼️ 썸네일 문구:** {res['thumbnail_text']}")

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**📄 유튜브 설명란**")
            st.text_area("설명", res.get("description", "") + "\n\n" + " ".join(res.get("hashtags", [])),
                         height=180, label_visibility="collapsed")
        with c2:
            st.markdown("**📷 인스타그램 글**")
            st.text_area("인스타", res.get("instagram", ""), height=180, label_visibility="collapsed")

        txt = "\n".join([f"[제목 후보]", *res.get("titles", []), "", "[대본]",
                         *[f"{r['장면']}. ({r['화면 문구']}) {r['나레이션']}" for r in rows], "",
                         "[설명]", res.get("description", ""), " ".join(res.get("hashtags", [])), "",
                         "[인스타그램]", res.get("instagram", "")])
        d1, d2 = st.columns(2)
        d1.download_button("⬇️ 텍스트로 받기", txt, file_name=f"{req['name']}_쇼츠대본.txt", width="stretch")
        d2.download_button("⬇️ JSON으로 받기 (자동화 연동용)", json.dumps(res, ensure_ascii=False, indent=2),
                           file_name=f"{req['name']}_script.json", width="stretch")
        st.caption(f"생성 모델: {ss.script['model']} · 같은 입력도 다시 누르면 다른 결과가 나와요.")

# ───────── 탭 2: 댓글 응대 ─────────
with tab2:
    st.write("영상에 달린 댓글을 **한 줄에 하나씩** 붙여 넣으세요. AI가 분류하고 답글 초안을 써요. "
             "**불만·민감 댓글은 AI가 답하지 않고 담당자에게 넘겨요.**")
    if st.button("예시 댓글로 채우기"):
        ss.comments_in = SAMPLE_COMMENTS
        ss.c_brand = ss.get("in_brand") or SAMPLE["brand"]
    ss.setdefault("c_brand", ss.get("in_brand") or "")
    with st.form("comment_form"):
        cbrand = st.text_input("브랜드 이름 *", key="c_brand", max_chars=30)
        cinfo = st.text_input("답글에 참고할 제품 정보 (선택)", max_chars=200,
                              placeholder="예: 원액 1 : 우유 3 비율 추천, 배송은 평일 기준 2~3일")
        raw = st.text_area("댓글 목록 *", key="comments_in", height=160, max_chars=3000)
        go = st.form_submit_button("🤖 AI로 분류하고 답글 쓰기", type="primary", width="stretch")

    if go:
        comments = [c.strip() for c in raw.splitlines() if c.strip()][:MAX_COMMENTS]
        if not cbrand.strip() or not comments:
            st.error("브랜드 이름과 댓글을 1개 이상 입력해 주세요.")
        elif allow_call():
            masked = [checks.mask_personal(c) for c in comments]  # 개인정보는 가리고 AI에 보냄
            if masked != comments:
                st.info("댓글 속 전화번호·이메일 등은 가린 뒤 AI에 보냈어요.")
            with st.spinner("AI가 댓글을 읽고 있어요..."):
                try:
                    data, model = ai.generate_json(prompts.COMMENT_SYSTEM,
                                                   prompts.comment_prompt(cbrand, tone, cinfo, banned, masked),
                                                   ["items"], temperature=0.4)
                    ss.replies = {"items": checks.enforce_comment_rules(data.get("items", []), masked, banned),
                                  "model": model}
                except ai.AIError as e:
                    ss.pop("replies", None)
                    st.error(f"😥 {e}")

    if "replies" in ss:
        items = ss.replies["items"]
        icon = {"문의": "❓", "칭찬": "😊", "불만": "⚠️", "민감": "🚫", "스팸": "🗑️"}
        counts = {c: sum(1 for it in items if it["category"] == c) for c in checks.CATEGORIES}
        st.divider()
        cols = st.columns(5)
        for col, c in zip(cols, checks.CATEGORIES):
            col.metric(f"{icon[c]} {c}", counts[c])
        for n, it in enumerate(items, 1):
            with st.container(border=True):
                st.markdown(f"**{icon[it['category']]} {it['category']}** · {it['comment']}")
                if it["reason"]:
                    st.caption(f"분류 이유: {it['reason']}")
                if it["category"] in checks.NEED_HUMAN:
                    st.warning("담당자가 직접 확인하고 답해야 하는 댓글이에요. 환불·보상·건강 관련 약속을 AI가 대신하지 않아요.")
                elif it["category"] == "스팸":
                    st.caption("답글을 달지 않아요. 플랫폼에서 숨김·신고를 권장해요.")
                else:
                    st.text_area("답글 초안", it["reply"], key=f"reply_{n}", height=80)
                for note in it["notes"]:
                    st.caption(f"⚠️ {note}")
        st.caption(f"생성 모델: {ss.replies['model']} · 답글은 꼭 확인한 뒤 게시하세요.")

# ───────── 탭 3: 안내 ─────────
with tab3:
    st.markdown("""
### 이런 분께 필요해요
마케팅 담당자가 따로 없는 **소상공인·작은 브랜드**. 쇼츠를 꾸준히 올려야 하는데 기획, 대본, 제목, 댓글 응대에 시간이 많이 드는 문제를 줄여요.

### 무엇을 해 주나요
- **쇼츠 대본:** 장면별 화면 문구와 나레이션, 제목 후보, 설명란, 해시태그, 인스타 글
- **댓글 응대:** 문의·칭찬·불만·민감·스팸 분류와 답글 초안
- **자동 검사:** 금지 표현, 효능·과장 표현, 입력에 없는 숫자(AI가 지어낸 수치일 가능성)

### 안전장치
- 불만·민감 댓글에는 AI가 답글을 쓰지 않아요. AI가 규칙을 어겨도 화면에서 한 번 더 걸러요.
- 입력에 전화번호·이메일이 있으면 대본은 생성을 막고, 댓글은 가린 뒤 AI에 보내요.
- AI 키는 서버에만 보관되고 화면이나 코드에 나오지 않아요.
- 짧은 시간에 너무 많이 요청하면 잠시 쉬게 해요.

### 한계
- AI는 사실과 다른 내용을 만들 수 있어요. 검사기는 형식과 표현만 보고 **사실 여부는 보장하지 않아요.**
- 광고 규정은 업종과 시기에 따라 달라요. 법률 판단이 필요하면 전문가에게 확인하세요.
- 실제처럼 보이는 AI 영상·이미지를 함께 쓴다면 플랫폼의 AI 생성 표시를 켜야 해요.
""")
    st.caption("입력한 내용은 저장하지 않으며, AI 처리를 위해 Google Gemini API로 전송됩니다.")
