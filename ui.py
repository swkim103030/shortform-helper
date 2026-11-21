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
.track {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: .5rem; list-style: none; padding: 0 !important; margin: 0 !important; max-width: 40rem; }}
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
@media (prefers-reduced-motion: reduce) {{ * {{ transition: none !important; animation: none !important; }} }}
</style>
"""


def hero(step_done):
    """step_done: 끝난 단계 수(0~4). 다음 단계를 '지금'으로 표시한다."""
    names = ["제품 입력", "대본", "영상", "올리기"]
    items = []
    for i, name in enumerate(names):
        cls = "done" if i < step_done else ("now" if i == step_done else "")
        mark = "✓" if i < step_done else str(i + 1)
        items.append(f'<div role="listitem" class="{cls}"><b>{mark}</b>{name}</div>')
    return f"""
<div class="hero">
  <span class="chip"><i></i>유튜브 쇼츠와 인스타 릴스까지 한 번에</span>
  <h1>제품 정보만 넣으면,<br>오늘 올릴 쇼츠가 나와요</h1>
  <p class="lead">AI가 대본을 쓰고, 음성·자막·배경음악을 입혀 세로 영상으로 만들어요.
  확인한 영상은 바로 올리고, 댓글엔 답글 초안까지 써 드려요.</p>
  <div class="track" role="list" aria-label="진행 단계">{''.join(items)}</div>
</div>
"""
