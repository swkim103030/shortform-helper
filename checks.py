"""AI 결과 검사기 (사람이 최종 확인하기 전 1차 필터)

- 브랜드 금지 표현, 식품 광고에서 문제 될 수 있는 효능·과장 표현
- 입력에 없는 숫자(AI가 지어낸 수치일 가능성)
- 쇼츠 대본 형식(지시문, 길이, 화면 문구 길이)
- 입력 속 개인정보(전화번호·이메일 등) 감지
형식 검사기이므로 사실관계를 보장하지는 않는다.
"""
import re

SEC_PER_CHAR = 0.17   # 한국어 나레이션 대략 속도(공백 제외 글자당 초)
CAPTION_MAX = 16

# 광고에서 문제 되기 쉬운 표현 (최상급·단정·효능·전문가 보증)
RISKY = {
    "최상급·단정 표현": ["최고", "1등", "1위", "넘버원", "무조건", "100%", "완벽", "유일", "최초", "절대"],
    "효능·건강 주장": ["치료", "예방", "완치", "면역", "다이어트", "살 빠", "체지방", "혈당", "해독", "디톡스",
                   "피로 회복", "숙취 해소", "항암", "노화 방지"],
    "전문가 보증처럼 보이는 표현": ["의사 추천", "약사 추천", "전문의", "의사가", "영양사 추천", "임상"],
    "근거 없는 추천·후기처럼 보이는 표현": ["가 추천하는", "이 추천하는", "가 추천한", "이 추천한", "강력 추천", "극찬",
                                   "후기", "리뷰", "인생템", "입소문"],
}
DIRECTIVE = re.compile(r"[\[\]()（）{}<>]|\*\*|#|(장면|BGM|효과음|컷|자막|화면|나레이션)\s*[:：]")
PERSONAL = {
    "전화번호": re.compile(r"01[016789][-\s.]?\d{3,4}[-\s.]?\d{4}"),
    "이메일": re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"),
    "주민등록번호": re.compile(r"\d{6}[-\s]?[1-4]\d{6}"),
    "카드·계좌번호": re.compile(r"\d{4}[-\s]\d{4}[-\s]\d{4}[-\s]\d{2,4}"),
}


def numbers(text):
    """'12,900원' → '12900', '2주' → '2' 처럼 숫자만 뽑는다."""
    return {n.replace(",", "") for n in re.findall(r"\d[\d,]*", text or "")}


UNIT_RE = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(퍼센트|%|초|분|시간|일|주|개월|달|년|배|명|잔|개|병|회|ml|mL|L|g|kg|원|만원)")


def quantities(text):
    """'10초', '1분', '10퍼센트' → {('10','초'), ('1','분'), ('10','%')} 숫자와 단위 쌍"""
    out = set()
    for num, unit in UNIT_RE.findall(text or ""):
        unit = {"퍼센트": "%", "mL": "ml", "달": "개월"}.get(unit, unit)
        out.add((num.replace(",", ""), unit))
    return out


def find_personal(text):
    return [name for name, rx in PERSONAL.items() if rx.search(text or "")]


def mask_personal(text):
    for rx in PERSONAL.values():
        text = rx.sub("[개인정보 가림]", text)
    return text


def risky_terms(text, banned=()):
    found = []
    for w in banned:
        w = w.strip()
        if w and w in text:
            found.append(("브랜드 금지 표현", w))
    for group, words in RISKY.items():
        for w in words:
            if w in text and ("브랜드 금지 표현", w) not in found:
                found.append((group, w))
    return found


def check_script(result, user_input_text, banned=(), target_sec=30):
    """쇼츠 대본 결과 검사. 반환: {"errors": [...], "warnings": [...], "estimated_sec": float}"""
    errors, warnings = [], []
    scenes = result.get("scenes") or []
    if len(scenes) < 3:
        errors.append(f"장면이 {len(scenes)}개뿐이에요 (최소 3개).")

    for i, s in enumerate(scenes, 1):
        cap, nar = str(s.get("caption", "")).strip(), str(s.get("narration", "")).strip()
        if not cap or not nar:
            errors.append(f"장면 {i}: 화면 문구나 나레이션이 비어 있어요.")
        if DIRECTIVE.search(nar):
            errors.append(f"장면 {i}: 나레이션에 성우가 읽으면 안 되는 지시문·괄호가 있어요 → \"{nar[:30]}\"")
        if len(cap) > CAPTION_MAX:
            warnings.append(f"장면 {i}: 화면 문구가 {len(cap)}자예요 (권장 {CAPTION_MAX}자 이내).")
        if re.search(r"[%~/&@]", nar):
            warnings.append(f"장면 {i}: 읽기 어려운 기호가 있어요 (예: % → 퍼센트).")

    all_text = " ".join([
        " ".join(result.get("titles", [])), result.get("description", ""),
        " ".join(result.get("hashtags", [])), result.get("instagram", ""),
        " ".join(f"{s.get('caption', '')} {s.get('narration', '')}" for s in scenes),
    ])
    for group, w in risky_terms(all_text, banned):
        (errors if group in ("브랜드 금지 표현", "효능·건강 주장", "전문가 보증처럼 보이는 표현") else warnings).append(
            f"{group}: '{w}' — 광고 표현 규정에 걸릴 수 있어요.")

    known = numbers(user_input_text)
    # 한 자리 숫자(1~9)는 "3가지", "2잔"처럼 흔히 쓰이므로 제외하고, 나머지 새 숫자만 경고
    invented = sorted(n for n in numbers(all_text) - known if not (len(n) == 1 and n != "0"))
    if invented:
        warnings.append("입력에 없는 숫자가 있어요: " + ", ".join(invented[:6]) + " — AI가 지어낸 수치인지 확인하세요.")
    # '10초 만에', '1분 완성'처럼 숫자는 입력에 있어도 단위가 다르면 지어낸 주장일 수 있다
    known_q = quantities(user_input_text)
    new_q = sorted(f"{n}{u}" for n, u in quantities(all_text) - known_q
                   if f"{n}" not in invented)  # 위에서 이미 경고한 숫자는 중복 경고하지 않음
    if new_q:
        warnings.append("입력에 없는 수치 표현이 있어요: " + ", ".join(new_q[:6])
                        + " — '10초 만에', '1분 완성'처럼 근거 없는 주장인지 확인하세요.")

    sec = sum(len(re.sub(r"\s", "", str(s.get("narration", "")))) * SEC_PER_CHAR + 0.35 for s in scenes)
    if sec > target_sec * 1.4:
        warnings.append(f"예상 길이가 약 {sec:.0f}초로 목표({target_sec}초)보다 길어요.")
    elif sec < target_sec * 0.5:
        warnings.append(f"예상 길이가 약 {sec:.0f}초로 목표({target_sec}초)보다 짧아요.")
    return {"errors": errors, "warnings": warnings, "estimated_sec": round(sec, 1)}


NEED_HUMAN = {"불만", "민감"}
CATEGORIES = ["문의", "칭찬", "불만", "민감", "스팸"]


def enforce_comment_rules(items, comments, banned=()):
    """AI가 규칙을 어겨도 화면에는 안전한 결과만 나가도록 후처리한다.
    - 불만·민감 댓글에는 AI 답글을 지우고 담당자 확인으로 돌린다.
    - 스팸에는 답글을 쓰지 않는다.
    - 답글에 위험 표현이나 개인정보가 있으면 경고를 붙인다."""
    out = []
    for i, text in enumerate(comments):
        item = items[i] if i < len(items) and isinstance(items[i], dict) else {}
        cat = item.get("category") if item.get("category") in CATEGORIES else "민감"
        reply = str(item.get("reply", "")).strip()
        notes = []
        if cat in NEED_HUMAN:
            if reply:
                notes.append("AI가 답글을 썼지만 규칙에 따라 숨겼어요.")
            reply = ""
        elif cat == "스팸":
            reply = ""
        if reply:
            bad = risky_terms(reply, banned)
            if bad:
                notes.append("답글에 주의 표현: " + ", ".join(w for _, w in bad))
            if find_personal(reply):
                notes.append("답글에 개인정보처럼 보이는 내용이 있어요.")
        out.append({"comment": text, "category": cat, "reason": str(item.get("reason", "")).strip(),
                    "reply": reply, "notes": notes})
    return out
