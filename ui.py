"""화면 꾸미기: 글꼴·색·첫 화면(히어로)·단계 표시

디자인 방향: '시장 전단지 × 세로 화면'
- 색: 바탕 #F5F6FA, 글자 #1D2140, 코발트 #2E4BFF, 가격 스티커 노랑 #FFE14D, 완료 초록 #14A06B
- 글꼴: 제목 G마켓 산스(전단지 느낌), 본문 Pretendard
"""
import html

INK, COBALT, YELLOW, GREEN, LINE = "#1D2140", "#2E4BFF", "#FFE14D", "#14A06B", "#DDE1EE"

CSS = f"""
<style>
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css');
@font-face {{ font-family: 'GmarketSans'; font-weight: 700; font-display: swap;
  src: url('https://cdn.jsdelivr.net/gh/projectnoonnu/noonfonts_2001@1.1/GmarketSansBold.woff') format('woff'); }}
@font-face {{ font-family: 'GmarketSans'; font-weight: 500; font-display: swap;
  src: url('https://cdn.jsdelivr.net/gh/projectnoonnu/noonfonts_2001@1.1/GmarketSansMedium.woff') format('woff'); }}

html, body, .stMarkdown, .stMarkdown p, label, input, textarea, select, button p,
[data-testid="stWidgetLabel"], [data-baseweb="tab"], [data-testid="stCaptionContainer"] {{
  font-family: 'Pretendard', -apple-system, 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif; }}
/* 아이콘 글꼴은 그대로 둔다 (본문 글꼴이 덮어쓰면 아이콘 대신 영어 이름이 보인다) */
[data-testid="stIconMaterial"], [data-testid="stExpandSidebarButton"] span,
[data-testid="stSidebarCollapseButton"] span, span[translate="no"] {{
  font-family: 'Material Symbols Rounded' !important; }}
h1, h2, h3, h4 {{ font-family: 'GmarketSans', 'Pretendard', sans-serif !important; letter-spacing: -0.01em;
  color: {INK}; word-break: keep-all; }}
h2 {{ font-size: 1.45rem !important; }}  h3 {{ font-size: 1.2rem !important; }}
.block-container {{ max-width: 1080px; padding-top: 2.2rem; }}

/* 버튼: 주 버튼은 코발트 단색, 보조 버튼은 흰 바탕 + 남색 테두리 */
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button {{
  border-radius: 10px; font-weight: 600; border: 1.5px solid {INK}; color: {INK}; background: #fff; }}
.stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"] {{
  background: {COBALT}; border-color: {COBALT}; color: #fff; }}
.stButton > button:hover, .stDownloadButton > button:hover {{ border-color: {COBALT}; color: {COBALT}; }}
.stButton > button[kind="primary"]:hover, .stFormSubmitButton > button[kind="primary"]:hover {{
  background: #1F38D6; color: #fff; }}
button:focus-visible {{ outline: 3px solid {YELLOW} !important; outline-offset: 2px; }}

/* 입력 묶음은 흰 종이처럼 */
[data-testid="stForm"] {{ background: #fff; border: 1px solid {LINE}; border-radius: 14px; padding: 1.2rem 1.3rem; }}

/* 탭: 코발트 밑줄 */
.stTabs [data-baseweb="tab-list"] {{ gap: 1.4rem; border-bottom: 1px solid {LINE}; }}
.stTabs [data-baseweb="tab"] {{ font-weight: 600; padding: 0.6rem 0.1rem; }}
.stTabs [aria-selected="true"] {{ color: {COBALT}; }}
.stTabs [data-baseweb="tab-highlight"] {{ background-color: {COBALT}; height: 3px; }}

/* 첫 화면: 그림 없이 글자와 진행 막대만 */
.hero {{ position: relative; margin: 0.6rem 0 2rem; padding: 2.4rem 0 0.4rem; }}
.hero::before {{ content: ""; position: absolute; inset: 0 -2rem; z-index: -1;
  background-image: radial-gradient({LINE} 1.2px, transparent 1.2px); background-size: 18px 18px;
  -webkit-mask-image: linear-gradient(180deg, #000 0%, transparent 85%); mask-image: linear-gradient(180deg, #000 0%, transparent 85%); }}
.hero .chip {{ display: inline-flex; align-items: center; gap: .45rem; padding: .32rem .75rem; border-radius: 999px;
  background: #fff; border: 1px solid {LINE}; font-size: .82rem; font-weight: 600; color: #4A5072; margin-bottom: 1.1rem; }}
.hero .chip i {{ width: 7px; height: 7px; border-radius: 50%; background: {GREEN}; box-shadow: 0 0 0 3px #D3F0E3; }}
.hero h1 {{ font-size: clamp(2rem, 4.4vw, 3.2rem) !important; line-height: 1.14 !important; letter-spacing: -0.035em;
  margin: 0 0 1rem; padding: 0; word-break: keep-all; }}
.hero p.lead {{ font-size: 1.04rem; line-height: 1.7; color: #4A5072; margin: 0 0 1.8rem; max-width: 33em; word-break: keep-all; }}
.track {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: .5rem; list-style: none; padding: 0 !important; margin: 0 !important; max-width: 54rem; }}
.track > div {{ margin: 0 !important; padding: 0 !important; }}
.track > div {{ font-size: .86rem; font-weight: 600; color: #8A8FAB; }}
.track > div::before {{ content: ""; display: block; height: 5px; border-radius: 999px; background: {LINE}; margin-bottom: .55rem; }}
.track > div b {{ font-family: 'GmarketSans', sans-serif; font-weight: 500; margin-right: .3rem; }}
.track > div.done {{ color: {GREEN}; }}  .track > div.done::before {{ background: {GREEN}; }}
.track > div.now {{ color: {INK}; }}    .track > div.now::before {{ background: {COBALT}; }}

@media (max-width: 640px) {{
  .block-container {{ padding-top: 1.4rem; }}
  .hero {{ padding-top: 1.6rem; }}
  .hero::before {{ inset: 0 -1rem; }}
  .hero p.lead {{ font-size: .95rem; }}
  .track > div {{ font-size: .76rem; }}
}}

/* 복사용 제목 상자: 고정폭 글꼴 대신 본문 글꼴 */
[data-testid="stCode"] code, [data-testid="stCode"] pre {{ font-family: 'Pretendard', sans-serif !important;
  font-size: 1rem !important; font-weight: 600; color: {INK} !important; }}
[data-testid="stCode"] pre {{ background: #fff !important; border: 1px solid {LINE}; border-left: 4px solid {YELLOW}; }}

/* 진행 막대 아래 기능 태그 */
.track .feats {{ display: flex; flex-wrap: wrap; gap: .3rem; margin-top: .55rem; }}
.tag {{ display: inline-block; padding: .18rem .5rem; border-radius: 6px; font-size: .74rem; font-weight: 600;
  background: #fff; border: 1px solid {LINE}; color: #4A5072; white-space: nowrap; }}
.track > div.done .tag {{ border-color: #BFE6D5; }}
.track > div.now .tag {{ border-color: #C9D2FF; color: {INK}; }}

/* 본문 단계 제목 */
.sec {{ display: flex; gap: 1rem; align-items: flex-start; margin: 2.6rem 0 1.1rem; padding-top: 1.6rem; border-top: 1px solid {LINE}; }}
.sec.first {{ border-top: 0; padding-top: 0; margin-top: 1rem; }}
.sec .num {{ flex: 0 0 auto; width: 2.6rem; height: 2.6rem; border-radius: 12px; display: grid; place-items: center;
  background: {INK}; color: #fff; font-family: 'GmarketSans', sans-serif; font-size: 1.25rem; }}
.sec h2 {{ margin: 0 0 .25rem !important; padding: 0 !important; font-size: 1.55rem !important; letter-spacing: -0.02em; }}
.sec p {{ margin: 0 0 .55rem; color: #5B6080; font-size: .93rem; line-height: 1.6; word-break: keep-all; }}
.sec .tags {{ display: flex; flex-wrap: wrap; gap: .35rem; }}
.sec .tag.on {{ background: #EEF1FF; border-color: #C9D2FF; color: {COBALT}; }}
.sec .tag.off {{ color: #9AA0BA; text-decoration: line-through; }}
.sub {{ display: flex; align-items: center; gap: .55rem; margin: 1.6rem 0 .6rem; }}
.sub h3 {{ margin: 0 !important; padding: 0 !important; font-size: 1.15rem !important; }}
.sub .lock {{ font-size: .72rem; font-weight: 700; padding: .15rem .5rem; border-radius: 999px; background: {YELLOW}; color: {INK}; }}

/* 설정 메뉴 묶음 제목 */
[data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {{ font-size: 1.02rem !important; padding: .2rem 0 .2rem .65rem !important;
  border-left: 4px solid {COBALT}; margin: 1.2rem 0 .6rem !important; }}

@media (max-width: 640px) {{
  .track .feats {{ display: none; }}
  .sec {{ gap: .7rem; margin-top: 2rem; }}
  .sec .num {{ width: 2.1rem; height: 2.1rem; font-size: 1rem; border-radius: 10px; }}
  .sec h2 {{ font-size: 1.25rem !important; }}
}}
@media (prefers-reduced-motion: reduce) {{ * {{ transition: none !important; animation: none !important; }} }}
</style>
"""


FEATURES = [
    ("제품 입력", ["금지 표현 설정", "예시로 채우기"]),
    ("대본", ["장면별 대본", "제목 3개", "인스타 글", "과장 표현 검사"]),
    ("영상", ["AI 음성", "자막", "배경음악", "스톡 영상", "내 사진"]),
    ("올리기", ["유튜브", "인스타 릴스", "댓글 답글", "성과 확인"]),
]


def hero(step_done):
    """step_done: 끝난 단계 수(0~4). 다음 단계를 '지금'으로 표시한다."""
    items = []
    for i, (name, feats) in enumerate(FEATURES):
        cls = "done" if i < step_done else ("now" if i == step_done else "")
        mark = "✓" if i < step_done else str(i + 1)
        tags = "".join(f'<span class="tag">{html.escape(f)}</span>' for f in feats)
        items.append(f'<div role="listitem" class="{cls}"><b>{mark}</b>{name}<div class="feats">{tags}</div></div>')
    return f"""
<div class="hero">
  <span class="chip"><i></i>유튜브 쇼츠와 인스타 릴스까지 한 번에</span>
  <h1>제품 정보만 넣으면,<br>오늘 올릴 쇼츠가 나와요</h1>
  <p class="lead">AI가 대본을 쓰고, 음성·자막·배경음악을 입혀 세로 영상으로 만들어요.
  확인한 영상은 바로 올리고, 댓글엔 답글 초안까지 써 드려요.</p>
  <div class="track" role="list" aria-label="진행 단계">{''.join(items)}</div>
</div>
"""


def section(num, title, desc="", tags=None, first=False):
    """본문 단계 제목. tags: [(글, 켜짐 여부)] — 이 단계에 들어가는 기능을 한눈에 보여 준다."""
    e = html.escape
    t = ""
    if tags:
        t = '<div class="tags">' + "".join(
            f'<span class="tag {"on" if on else "off"}">{e(x)}</span>' for x, on in tags) + "</div>"
    d = f"<p>{e(desc)}</p>" if desc else ""
    return f'<div class="sec{" first" if first else ""}"><div class="num">{e(str(num))}</div><div><h2>{e(title)}</h2>{d}{t}</div></div>'


def sub(title, locked=False):
    lock = '<span class="lock">팀 전용</span>' if locked else ""
    return f'<div class="sub"><h3>{html.escape(title)}</h3>{lock}</div>'
