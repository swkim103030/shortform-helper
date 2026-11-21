"""숏폼 마케팅 도우미 — 제품 정보를 넣으면 생성형 AI가 쇼츠 대본·제목·SNS 문구·댓글 답글 초안을 만든다.

실행: streamlit run app.py
필요한 비밀 설정 (.streamlit/secrets.toml 또는 Streamlit Cloud의 Secrets):
    GEMINI_API_KEY = "..."
    GEMINI_MODEL = "gemini-3.8-flash"      # 선택
    TEAM_PASSWORD = "..."                   # 팀 기능(유튜브 업로드·댓글 게시) 잠금 비밀번호
    YOUTUBE_TOKEN = '''{ token.json 내용 }'''  # 업로드할 채널의 로그인 정보
"""
import hashlib
import hmac
import json
import time

import streamlit as st

import ai
import checks
import stock
import prompts
import bgm
import instagram
import video
import youtube

st.set_page_config(page_title="숏폼 마케팅 도우미", page_icon="🎬", layout="centered")

MAX_CALLS = 15            # 한 사람(세션)이 10분 동안 쓸 수 있는 AI 호출 수 (무료 한도 보호)
WINDOW_SEC = 600
MAX_COMMENTS = 15
MAX_PHOTOS = 8            # 영상에 넣을 내 사진·영상 최대 개수
PHOTO_MB = 40             # 파일 하나 최대 크기(MB)
MAX_VIDEOS = 4            # 한 사람이 10분 동안 만들 수 있는 영상 수 (무료 서버 보호)
PRIVACY = {"일부 공개 (링크 있는 사람만)": "unlisted", "비공개": "private", "공개": "public"}
AI_NOTICE = "※ 이 영상의 대본과 음성은 AI로 만들었고, 담당자가 확인한 뒤 올렸습니다."
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
ss.setdefault("video_times", [])
ss.setdefault("uploaded", {})
ss.setdefault("ig_posted", {})
ss.setdefault("music_seed", 0)
ss.setdefault("posted", set())
ss.setdefault("team_ok", False)
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


def _secret_value(name):
    try:
        return str(st.secrets.get(name, "") or "")
    except Exception:
        return ""


def allow_video():
    now = time.time()
    ss.video_times = [t for t in ss.video_times if now - t < WINDOW_SEC]
    if len(ss.video_times) >= MAX_VIDEOS:
        st.warning("영상은 10분에 4개까지 만들 수 있어요. 잠시 뒤에 다시 시도해 주세요.")
        return False
    ss.video_times.append(now)
    return True


def show_ai_error(e):
    st.error(f"😥 {e}")
    if getattr(e, "detail", ""):
        with st.expander("자세한 원인 (관리자용)"):
            st.code(e.detail, language=None)


def human_notice(it):
    """사람이 처리할 댓글에 맞는 안내 문구"""
    reason = (it.get("reason") or "").lower()
    if any(k in reason for k in ("주입", "injection", "조작", "무관", "장난", "탈옥")):
        return "브랜드와 무관하거나 AI를 조작하려는 댓글로 보여요. 답하지 않는 걸 권장해요."
    if it["category"] == "불만":
        return "불만 댓글이에요. 사과·환불·교환 같은 약속은 AI가 대신하지 않아요. 담당자가 판단해서 직접 답해 주세요."
    return "개인정보·법률·건강·논란과 관련될 수 있는 댓글이에요. 답할지부터 담당자가 판단해 주세요."


def post_reply(n, th, text, banned):
    """확인 버튼을 눌러야만 유튜브에 답글을 게시한다"""
    if th["thread_id"] in ss.posted:
        st.success("유튜브에 답글을 달았어요.")
        return
    if st.button("✅ 확인했어요, 이 답글 게시", key=f"post_{n}"):
        if not text.strip():
            st.error("답글이 비어 있어요.")
        elif checks.risky_terms(text, banned) or checks.find_personal(text):
            st.error("답글에 주의 표현이나 개인정보가 있어서 게시하지 않았어요. 고친 뒤 다시 눌러 주세요.")
        else:
            try:
                youtube.reply(youtube.client(), th["thread_id"], text.strip())
                ss.posted.add(th["thread_id"])
                st.rerun()
            except youtube.YTError as e:
                st.error(f"😥 {e}")


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
    st.subheader("🎥 영상 설정")
    k1, k2 = st.columns(2)
    color_main = k1.color_picker("배경색", "#6B3E26")
    color_accent = k2.color_picker("강조색", "#F2B05E")
    voice_name = st.selectbox("목소리", list(video.VOICES))
    bg_options = ([f"스톡 영상 ({stock.provider()})"] if stock.configured() else []) + ["애니메이션 배경"]
    bg_mode = st.radio("배경", bg_options, help="스톡 영상: 장면마다 AI가 만든 검색어로 무료 실사 영상을 찾아 깔아요.")
    use_stock = bg_mode.startswith("스톡")
    music_name = st.selectbox("배경음악", list(bgm.MOODS) + ["없음"],
                              help="코드로 직접 만든 음악이라 저작권 걱정이 없어요. 목소리가 나올 땐 자동으로 작아져요.")
    music_up = st.file_uploader("또는 내 음악 파일", type=["mp3", "m4a", "wav"],
                                help="저작권이 해결된 음악만 올려 주세요. 15MB까지, 서버에 저장하지 않아요.")
    music_file = None
    if music_up is not None:
        if music_up.size > 15 * 1024 * 1024:
            st.warning("음악 파일은 15MB까지만 쓸 수 있어요.")
        else:
            music_file = (music_up.name, music_up.getvalue())
    if music_name != "없음" and not music_file:
        st.caption("영상마다 조·빠르기·화음이 달라져서 매번 다른 곡이 나와요.")
        m1, m2 = st.columns(2)
        if m1.button("🎵 분위기 듣기", width="stretch"):
            import tempfile
            try:
                with st.spinner("음악 만드는 중..."):
                    st.audio(str(bgm.get(music_name, tempfile.gettempdir(), ss.music_seed)))
            except Exception as e:
                st.error(f"음악을 만들지 못했어요. ({type(e).__name__})")
        if m2.button("🎲 다른 곡", width="stretch", help="같은 대본이라도 다른 곡으로 다시 만들어요."):
            ss.music_seed += 1
    ai_label = st.checkbox("화면에 'AI 생성 영상' 표시", value=True)
    st.divider()
    st.subheader("🔑 팀 기능")
    team_pw = _secret_value("TEAM_PASSWORD")
    if not team_pw:
        st.caption("유튜브 업로드·댓글 게시는 관리자가 팀 비밀번호를 설정해야 쓸 수 있어요.")
    elif ss.team_ok:
        st.success("팀 기능 사용 중 (유튜브 업로드·댓글 게시)")
        if st.button("잠그기"):
            ss.team_ok = False
            st.rerun()
    else:
        pw = st.text_input("팀 비밀번호", type="password", help="유튜브 업로드와 댓글 게시는 팀원만 쓸 수 있어요.")
        if pw:
            if hmac.compare_digest(pw.encode(), team_pw.encode()):
                ss.team_ok = True
                st.rerun()
            else:
                st.error("비밀번호가 달라요.")
    st.divider()
    st.caption("🔒 개인정보(전화번호, 이메일, 주소 등)는 입력하지 마세요. 입력된 내용은 AI 처리를 위해 Google Gemini API로 전송됩니다.")
    st.caption("⚠️ AI 결과는 초안입니다. 게시 전에 사실과 표현을 꼭 확인하세요.")

st.markdown("""<style>
@media (max-width: 640px) {
  h1 { font-size: 1.8rem !important; word-break: keep-all; }
  h2, h3 { font-size: 1.3rem !important; }
}
</style>""", unsafe_allow_html=True)
st.title("🎬 숏폼 마케팅 도우미")
st.write("제품 정보를 넣으면 AI가 **쇼츠 대본**을 쓰고, 그 대본으로 **음성·자막이 들어간 쇼츠 영상**을 만들어요. "
         "팀원은 확인한 영상을 **유튜브에 바로 올리고**, 채널 댓글에 **AI 답글**을 달 수 있어요. "
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
                    ss.script = {"data": data, "model": model, "req": req, "id": int(time.time() * 1000),
                                 "user_text": f"{user_text} {seconds}초",
                                 "check": checks.check_script(data, f"{user_text} {seconds}초", banned, seconds)}
                except ai.AIError as e:
                    ss.pop("script", None)
                    show_ai_error(e)

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

        st.markdown(f"**🎬 장면별 대본** · 예상 약 {chk['estimated_sec']:.0f}초 · 칸을 눌러 직접 고칠 수 있어요 (휴대폰은 표를 옆으로 밀어 보세요)")
        rows = [{"장면": i + 1, "화면 문구": s.get("caption", ""), "나레이션": s.get("narration", ""),
                 "배경 검색어": s.get("broll", "")} for i, s in enumerate(res.get("scenes", []))]
        edited = st.data_editor(
            rows, hide_index=True, width="stretch", disabled=["장면"], key=f"scenes_{ss.script['id']}",
            column_config={"장면": st.column_config.NumberColumn(width="small"),
                           "화면 문구": st.column_config.TextColumn(width="medium", max_chars=30),
                           "나레이션": st.column_config.TextColumn(width="large", max_chars=200),
                           "배경 검색어": st.column_config.TextColumn(width="medium", max_chars=60)})
        rows = [{"장면": i + 1, "화면 문구": str(r.get("화면 문구") or "").strip(),
                 "나레이션": str(r.get("나레이션") or "").strip(),
                 "배경 검색어": str(r.get("배경 검색어") or "").strip()} for i, r in enumerate(edited)]
        final = dict(res, scenes=[{"caption": r["화면 문구"], "narration": r["나레이션"], "broll": r["배경 검색어"]}
                                  for r in rows])
        changed = [(a["caption"], a["narration"]) for a in final["scenes"]] != \
            [(b.get("caption", ""), b.get("narration", "")) for b in res.get("scenes", [])]
        if changed:  # 사람이 고친 대본은 다시 검사
            chk = checks.check_script(final, ss.script["user_text"], banned, req["seconds"])
            st.caption("✏️ 고친 대본으로 다시 검사했어요." + (" 아래 문제를 확인해 주세요." if chk["errors"] else ""))
            for e_ in chk["errors"]:
                st.error(e_)
        if res.get("thumbnail_text"):
            st.markdown(f"**🖼️ 썸네일 문구:** {res['thumbnail_text']}")

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**📄 유튜브 설명란**")
            desc = st.text_area("설명", res.get("description", "") + "\n\n" + " ".join(res.get("hashtags", [])),
                                height=180, label_visibility="collapsed", key=f"desc_{ss.script['id']}")
        with c2:
            st.markdown("**📷 인스타그램 글**")
            st.text_area("인스타", res.get("instagram", ""), height=180, label_visibility="collapsed")

        txt = "\n".join([f"[제목 후보]", *res.get("titles", []), "", "[대본]",
                         *[f"{r['장면']}. ({r['화면 문구']}) {r['나레이션']}" for r in rows], "",
                         "[설명]", res.get("description", ""), " ".join(res.get("hashtags", [])), "",
                         "[인스타그램]", res.get("instagram", "")])
        d1, d2 = st.columns(2)
        d1.download_button("⬇️ 텍스트로 받기", txt, file_name=f"{req['name']}_쇼츠대본.txt", width="stretch")
        d2.download_button("⬇️ JSON으로 받기 (자동화 연동용)", json.dumps(final, ensure_ascii=False, indent=2),
                           file_name=f"{req['name']}_script.json", width="stretch")
        st.caption(f"생성 모델: {ss.script['model']} · 같은 입력도 다시 누르면 다른 결과가 나와요.")

        # ───── 영상 만들기 ─────
        st.divider()
        st.subheader("🎥 이 대본으로 영상 만들기")
        st.caption("장면마다 AI 음성과 움직이는 자막을 입혀 세로 쇼츠(1080×1920) 영상을 만들어요. 1분 안팎 걸려요. "
                   "색·목소리·배경은 설정 메뉴(휴대폰은 왼쪽 위 »)에서 바꿀 수 있어요."
                   + (" 배경은 표의 '배경 검색어'로 무료 스톡 영상을 찾아요." if use_stock else ""))
        ups = st.file_uploader(
            "📷 내 제품 사진·영상 넣기 (선택)", type=["jpg", "jpeg", "png", "webp", "mp4", "mov"],
            accept_multiple_files=True, key=f"photos_{ss.script['id']}",
            help=f"올린 순서대로 제품 소개 → 가격 → 특징 → 첫 장면에 들어가요. 최대 {MAX_PHOTOS}개, 파일당 {PHOTO_MB}MB. "
                 "영상을 만들 때만 쓰고 서버에 저장하지 않아요.")
        photos = []
        for f in (ups or [])[:MAX_PHOTOS]:
            if f.size > PHOTO_MB * 1024 * 1024:
                st.warning(f"'{f.name}'은(는) {PHOTO_MB}MB가 넘어서 빼고 만들어요.")
                continue
            photos.append((f.name, f.getvalue()))
        if ups and len(ups) > MAX_PHOTOS:
            st.warning(f"사진·영상은 {MAX_PHOTOS}개까지만 써요. 앞의 {MAX_PHOTOS}개만 넣을게요.")
        if photos:
            slots = video.assign_photos(len(final["scenes"]), [n for n, _ in photos])
            plan = " · ".join(f"장면 {i + 1}: {name}" for i, name in enumerate(slots) if name)
            st.caption(f"📷 {plan}" + (" (나머지 장면은 스톡 영상)" if use_stock and len(photos) < len(slots) else ""))
        photo_sig = [hashlib.sha1(d).hexdigest()[:8] for _, d in photos]
        vkey = hashlib.sha1(json.dumps([final["scenes"], color_main, color_accent, voice_name, ai_label, use_stock,
                                        photo_sig, music_name, ss.music_seed,
                                        hashlib.sha1(music_file[1]).hexdigest()[:8] if music_file else "",
                                        req["brand"], req["name"]], ensure_ascii=False).encode()).hexdigest()[:12]
        if st.button("🎬 영상 만들기", type="primary", width="stretch"):
            if any(not sc["caption"] or not sc["narration"] for sc in final["scenes"]):
                st.error("비어 있는 화면 문구나 나레이션이 있어요. 채운 뒤 다시 눌러 주세요.")
            elif allow_video():
                bar = st.progress(0.0, "준비 중...")
                try:
                    mp4, info = video.make_video(final, dict(req, cta=cta.strip()),
                                                 {"primary": color_main, "accent": color_accent},
                                                 video.VOICES[voice_name], ai_label,
                                                 progress=lambda p, m: bar.progress(min(1.0, p), m),
                                                 stock=use_stock, photos=photos,
                                                 music=None if music_name == "없음" else music_name,
                                                 music_file=music_file, music_seed=ss.music_seed)
                    ss.video = {"key": vkey, "mp4": mp4, "info": info, "script_id": ss.script["id"]}
                except Exception as e:
                    ss.pop("video", None)
                    st.error(f"😥 영상을 만들지 못했어요. 잠시 후 다시 시도해 주세요. ({type(e).__name__})")
                    with st.expander("자세한 원인 (관리자용)"):
                        st.code(str(e)[:800], language=None)
                bar.empty()

        vid = ss.get("video")
        if vid and vid["script_id"] == ss.script["id"]:
            info = vid["info"]
            if vid["key"] != vkey:
                st.info("대본이나 설정을 바꿨어요. 바뀐 내용을 반영하려면 '영상 만들기'를 다시 눌러 주세요.")
            if use_stock and info.get("stock_scenes", 0) + info.get("photo_scenes", 0) < info["scenes"]:
                st.info(f"배경 영상을 {info.get('stock_scenes', 0)}/{info['scenes'] - info.get('photo_scenes', 0)}개 장면에서 찾았어요. "
                        "못 찾은 장면은 애니메이션 배경이에요. '배경 검색어'를 바꿔 다시 만들어 볼 수 있어요.")
            if info.get("music_error"):
                st.warning("배경음악을 만들지 못해서 음악 없이 만들었어요.")
            if info.get("silent_scenes"):
                st.warning(f"음성 서버 연결이 불안정해서 {info['silent_scenes']}개 장면이 무음으로 만들어졌어요. 다시 만들어 보세요.")
            left, right = st.columns([3, 2])
            with left:
                st.video(vid["mp4"])
            with right:
                st.metric("영상 길이", f"{info['seconds']:.0f}초")
                st.metric("장면 수", info["scenes"])
                if info.get("photo_scenes"):
                    st.caption(f"📷 내 사진·영상 {info['photo_scenes']}개 장면 사용")
                st.caption(f"만드는 데 {info['elapsed']:.0f}초 걸렸어요.")
                if info.get("credits"):
                    names = ", ".join(dict.fromkeys(c["author"] for c in info["credits"] if c["author"]))
                    src = ", ".join(dict.fromkeys(c.get("source", "") for c in info["credits"]))
                    st.caption(f"🎞️ 배경 영상: {src} 무료 영상 (촬영: {names})")
                st.download_button("⬇️ 영상(mp4) 받기", vid["mp4"], file_name=f"{req['name']}_shorts.mp4",
                                   mime="video/mp4", width="stretch")

            # ───── 유튜브 업로드 (팀 전용) ─────
            st.markdown("#### 📤 유튜브에 올리기")
            if not ss.team_ok:
                st.caption("🔒 유튜브 업로드는 팀원만 쓸 수 있어요. 설정 메뉴(휴대폰은 왼쪽 위 »)의 '팀 기능'에 비밀번호를 넣어 주세요. "
                           "영상은 위에서 받아 직접 올릴 수도 있어요.")
            elif not youtube.configured():
                st.warning("유튜브 계정이 아직 연결되지 않았어요. (관리자: Secrets에 YOUTUBE_TOKEN 추가)")
            elif vid["key"] in ss.uploaded:
                u = ss.uploaded[vid["key"]]
                st.success(f"업로드 완료! https://youtu.be/{u['id']} ({u['privacy']})")
            else:
                with st.form(f"upload_{vid['key']}"):
                    titles = res.get("titles", [])[:3] or [req["name"]]
                    title = st.selectbox("제목", titles)
                    credit = ""
                    if info.get("credits"):
                        names = ", ".join(dict.fromkeys(c["author"] for c in info["credits"] if c["author"]))
                        src = ", ".join(dict.fromkeys(c.get("source", "") for c in info["credits"]))
                        credit = f"\n배경 영상: {src} (촬영: {names})"
                    up_desc = st.text_area("설명란", (desc + "\n\n" + AI_NOTICE + credit).strip(), height=150,
                                           max_chars=4900)
                    privacy = st.radio("공개 범위", list(PRIVACY), horizontal=True)
                    agree = st.checkbox("영상과 문구를 직접 확인했고, 사실과 다르거나 과장된 내용이 없음을 확인했어요.")
                    send = st.form_submit_button("📤 유튜브에 올리기", type="primary", width="stretch")
                if send:
                    if not agree:
                        st.error("올리기 전에 내용을 확인했다는 칸에 체크해 주세요. (사람 확인 없이 자동으로 올리지 않아요)")
                    elif chk["errors"]:
                        st.error("대본에 '꼭 고쳐야 할 점'이 남아 있어서 올릴 수 없어요. 위 장면 표에서 고친 뒤 영상을 다시 만들어 주세요.")
                    elif info.get("silent_scenes"):
                        st.error("음성이 빠진 장면이 있는 영상은 올리지 않아요. 영상을 다시 만들어 주세요.")
                    elif vid["key"] != vkey:
                        st.error("지금 대본·설정과 영상이 달라요. '영상 만들기'를 다시 누른 뒤 올려 주세요.")
                    else:
                        with st.spinner("유튜브에 올리는 중... (1분 정도)"):
                            try:
                                yt = youtube.client()
                                tags = [h for h in res.get("hashtags", []) if isinstance(h, str)]
                                vid_id, real = youtube.upload(yt, vid["mp4"], title, up_desc + "\n\n#Shorts", tags,
                                                              PRIVACY[privacy])
                                ss.uploaded[vid["key"]] = {"id": vid_id, "privacy": real}
                                st.rerun()
                            except youtube.YTError as e:
                                st.error(f"😥 {e}")
                            except Exception as e:
                                st.error(f"😥 업로드에 실패했어요. ({type(e).__name__})")
                st.caption("ℹ️ 학생용(미검수) 구글 프로젝트라 유튜브가 영상을 '비공개'로 바꿀 수 있어요.")

            # ───── 인스타그램 릴스 (팀 전용) ─────
            st.markdown("#### 📸 인스타 릴스로 올리기")
            if not ss.team_ok:
                st.caption("🔒 인스타 업로드도 팀원만 쓸 수 있어요. 영상과 인스타 글은 위에서 받아 직접 올릴 수도 있어요.")
            elif not instagram.configured():
                st.caption("인스타 계정이 아직 연결되지 않았어요. (관리자: Secrets에 INSTAGRAM_TOKEN 추가)")
            elif vid["key"] in ss.ig_posted:
                st.success(f"릴스 게시 완료! {ss.ig_posted[vid['key']]}")
            else:
                with st.form(f"ig_{vid['key']}"):
                    tags = " ".join(h if h.startswith("#") else f"#{h}"
                                    for h in res.get("hashtags", []) if isinstance(h, str))
                    ig_caption = st.text_area("캡션", (res.get("instagram", "") + "\n\n" + tags + "\n\n" + AI_NOTICE).strip(),
                                              height=170, max_chars=2200)
                    ig_agree = st.checkbox("영상과 캡션을 직접 확인했고, 인스타에 공개로 올리는 데 동의해요.",
                                           key=f"ig_agree_{vid['key']}")
                    ig_send = st.form_submit_button("📸 인스타에 올리기", type="primary", width="stretch")
                if ig_send:
                    if not ig_agree:
                        st.error("올리기 전에 확인 칸에 체크해 주세요. (사람 확인 없이 자동으로 올리지 않아요)")
                    elif chk["errors"]:
                        st.error("대본에 '꼭 고쳐야 할 점'이 남아 있어서 올릴 수 없어요.")
                    elif info.get("silent_scenes"):
                        st.error("음성이 빠진 장면이 있는 영상은 올리지 않아요. 영상을 다시 만들어 주세요.")
                    elif vid["key"] != vkey:
                        st.error("지금 대본·설정과 영상이 달라요. '영상 만들기'를 다시 누른 뒤 올려 주세요.")
                    else:
                        note = st.empty()
                        try:
                            with st.spinner("인스타에 올리는 중... (1~3분)"):
                                _, link = instagram.publish_reel(vid["mp4"], ig_caption,
                                                                 progress=lambda m: note.caption(m))
                            ss.ig_posted[vid["key"]] = link
                            st.rerun()
                        except instagram.IGError as e:
                            note.empty()
                            st.error(f"😥 {e}")
                        except Exception as e:
                            note.empty()
                            st.error(f"😥 인스타 업로드에 실패했어요. ({type(e).__name__})")
                st.caption("ℹ️ 인스타는 일부 공개가 없어서 바로 공개로 올라가요. 시연용 계정에서만 쓰세요.")

# ───────── 탭 2: 댓글 응대 ─────────
with tab2:
    st.write("영상에 달린 댓글을 **한 줄에 하나씩** 붙여 넣으세요. AI가 분류하고 답글 초안을 써요. "
             "**불만·민감 댓글은 AI가 답하지 않고 담당자에게 넘겨요.**")
    b1, b2 = st.columns(2)
    if b1.button("예시 댓글로 채우기", width="stretch"):
        ss.comments_in = SAMPLE_COMMENTS
        ss.c_brand = ss.get("in_brand") or SAMPLE["brand"]
        ss.pop("yt_threads", None)
    if ss.team_ok and youtube.configured():
        if b2.button("📥 내 채널 새 댓글 불러오기", width="stretch"):
            try:
                with st.spinner("채널 댓글을 불러오는 중..."):
                    yt = youtube.client()
                    ch = youtube.channel(yt)
                    threads = youtube.recent_comments(yt, ch, MAX_COMMENTS)
                if not threads:
                    st.info(f"'{ch['title']}' 채널에 아직 답하지 않은 새 댓글이 없어요.")
                else:
                    lines = [" ".join(t["text"].split())[:300] for t in threads]
                    ss.comments_in = "\n".join(lines)
                    ss.yt_threads = {"lines": lines, "threads": threads, "channel": ch["title"]}
                    ss.c_brand = ss.get("c_brand") or ss.get("in_brand") or ch["title"]
                    ss.pop("replies", None)
                    st.rerun()
            except youtube.YTError as e:
                st.error(f"😥 {e}")
    else:
        b2.caption("🔒 팀원은 내 유튜브 채널 댓글을 바로 불러와 답글까지 게시할 수 있어요.")
    if ss.get("yt_threads"):
        st.caption(f"📺 '{ss.yt_threads['channel']}' 채널에서 불러온 댓글 {len(ss.yt_threads['lines'])}개")
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
            linked = bool(ss.get("yt_threads")) and comments == ss.yt_threads["lines"]
            with st.spinner("AI가 댓글을 읽고 있어요..."):
                try:
                    data, model = ai.generate_json(prompts.COMMENT_SYSTEM,
                                                   prompts.comment_prompt(cbrand, tone, cinfo, banned, masked),
                                                   ["items"], temperature=0.4)
                    ss.replies = {"items": checks.enforce_comment_rules(data.get("items", []), masked, banned),
                                  "model": model, "threads": ss.yt_threads["threads"] if linked else None}
                except ai.AIError as e:
                    ss.pop("replies", None)
                    show_ai_error(e)

    if "replies" in ss:
        items = ss.replies["items"]
        icon = {"문의": "❓", "칭찬": "😊", "불만": "⚠️", "민감": "🚫", "스팸": "🗑️"}
        counts = {c: sum(1 for it in items if it["category"] == c) for c in checks.CATEGORIES}
        st.divider()
        # 휴대폰에서도 한 줄로 보이도록 표 대신 배지로 표시
        st.markdown("  ".join(f"**{icon[c]} {c} {counts[c]}**" for c in checks.CATEGORIES))
        for n, it in enumerate(items, 1):
            with st.container(border=True):
                st.markdown(f"**{icon[it['category']]} {it['category']}** · {it['comment']}")
                if it["reason"]:
                    st.caption(f"분류 이유: {it['reason']}")
                threads = ss.replies.get("threads") or []
                th = threads[n - 1] if n - 1 < len(threads) else None
                if it["category"] in checks.NEED_HUMAN:
                    st.warning(human_notice(it))
                    if th and ss.team_ok:  # AI 초안 없이 사람이 직접 쓴 답만 게시
                        with st.expander("✍️ 직접 답글 쓰기 (AI 초안 없음)"):
                            text = st.text_area("답글", "", key=f"human_{n}", height=80,
                                                placeholder="담당자가 직접 판단해서 쓰는 답글이에요.")
                            post_reply(n, th, text, banned)
                elif it["category"] == "스팸":
                    st.caption("답글을 달지 않아요. 플랫폼에서 숨김·신고를 권장해요.")
                else:
                    text = st.text_area("답글 초안", it["reply"], key=f"reply_{n}", height=80)
                    if th and ss.team_ok:
                        post_reply(n, th, text, banned)
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
- **쇼츠 영상:** 고친 대본에 AI 음성과 움직이는 자막을 입혀 mp4로 만들어요. 배경은 무료 스톡 영상이나 **내 제품 사진·영상**을 쓰고, **직접 합성한 배경음악**을 깔아요
- **유튜브·인스타 업로드 (팀원):** 사람이 확인 칸에 체크해야만 올라가요. 설명란·캡션에 AI 제작 사실을 적어요
- **댓글 응대:** 문의·칭찬·불만·민감·스팸 분류와 답글 초안. 팀원은 채널 댓글을 불러와 확인 후 게시
- **자동 검사:** 금지 표현, 효능·과장 표현, 입력에 없는 숫자(AI가 지어낸 수치일 가능성)

### 안전장치
- 불만·민감 댓글에는 AI가 답글을 쓰지 않아요. AI가 규칙을 어겨도 화면에서 한 번 더 걸러요.
- 입력에 전화번호·이메일이 있으면 대본은 생성을 막고, 댓글은 가린 뒤 AI에 보내요.
- AI 키와 유튜브 로그인 정보는 서버에만 보관되고 화면이나 코드에 나오지 않아요.
- 유튜브 업로드·답글 게시는 팀 비밀번호가 있어야 하고, 매번 사람이 눌러야만 실행돼요.
- 영상 화면에 'AI 생성 영상' 표시를 기본으로 넣어요.
- 짧은 시간에 너무 많이 요청하면 잠시 쉬게 해요.

### 한계
- AI는 사실과 다른 내용을 만들 수 있어요. 검사기는 형식과 표현만 보고 **사실 여부는 보장하지 않아요.**
- 광고 규정은 업종과 시기에 따라 달라요. 법률 판단이 필요하면 전문가에게 확인하세요.
- 실제처럼 보이는 AI 영상·이미지를 함께 쓴다면 플랫폼의 AI 생성 표시를 켜야 해요.
""")
    st.caption("입력한 내용은 저장하지 않으며, AI 처리를 위해 Google Gemini API로 전송됩니다.")
