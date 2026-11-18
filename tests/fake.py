"""테스트용 가짜 Gemini 클라이언트. 실제 서비스에서는 쓰지 않는다."""
import json
from google.genai import errors
MODE = {"script": "normal", "comment": "normal", "fail": None}
CALLS = []
GOOD_SCRIPT = {
  "titles": ["바쁜 아침, 콜드브루 한 잔이면 끝", "18시간 우린 콜드브루 원액", "출근 전 30초 커피 루틴"],
  "scenes": [
    {"caption": "아침이 바쁘다면?", "narration": "아침마다 커피 내릴 시간도 없으신가요?"},
    {"caption": "콜드브루 원액 500ml", "narration": "하루빈 커피 콜드브루 원액을 소개할게요."},
    {"caption": "18시간 저온 추출", "narration": "18시간 동안 천천히 우려 깊은 맛을 담았어요."},
    {"caption": "타기만 하면 완성", "narration": "물이나 우유에 타기만 하면 바로 완성이에요."},
    {"caption": "냉장 2주 보관", "narration": "냉장고에 두고 2주 동안 편하게 드세요."},
    {"caption": "첫 구매 10% 할인", "narration": "지금 첫 구매 10퍼센트 할인 중이고, 가격은 12,900원. 프로필 링크에서 확인하세요!"}],
  "description": "18시간 저온 추출한 하루빈 커피 콜드브루 원액.\n물이나 우유에 타기만 하면 완성.",
  "hashtags": ["#콜드브루", "#홈카페", "#하루빈커피", "#출근커피", "#쇼츠"],
  "instagram": "바쁜 아침에도 커피는 포기 못 하죠 ☕\n하루빈 커피 콜드브루 원액 500ml\n✔ 18시간 저온 추출\n✔ 타기만 하면 완성\n첫 구매 10% 할인 중!",
  "thumbnail_text": "30초 커피 루틴"}
BAD_SCRIPT = json.loads(json.dumps(GOOD_SCRIPT))
BAD_SCRIPT["scenes"][2]["narration"] = "(BGM) 면역력에 좋은 업계 최고의 커피, 48시간 숙성!"
BAD_SCRIPT["titles"][0] = "1등 콜드브루"
class R:
    def __init__(s, t): s.text = t
class M:
    def generate_content(self, model, contents, config):
        CALLS.append(model)
        if MODE["fail"] == 429: raise errors.ClientError(429, {"error": {"message": "quota"}})
        if MODE["fail"] == 401: raise errors.ClientError(403, {"error": {"message": "API key not valid"}})
        if MODE["fail"] == 404 and model != "gemini-2.5-flash": raise errors.ClientError(404, {"error": {"message": "not found"}})
        if MODE["fail"] == "garbage": return R("죄송합니다, JSON을 만들 수 없어요")
        if "댓글 목록" in contents:
            n = contents.split("[댓글 목록]")[1].count("\n") - 3
            items = [{"category": "문의", "reason": "비율 질문", "reply": "원액 1에 우유 3 비율을 추천드려요! 자세한 건 상세페이지를 확인해 주세요."},
                     {"category": "칭찬", "reason": "긍정 후기", "reply": "편하게 즐겨 주셔서 감사해요! 내일 아침도 함께할게요 :)"},
                     {"category": "불만", "reason": "배송 지연·환불 요구", "reply": "바로 환불해 드릴게요!"},
                     {"category": "스팸", "reason": "홍보 링크", "reply": ""},
                     {"category": "민감", "reason": "개인정보 포함", "reply": "확인해 볼게요"}]
            return R(json.dumps({"items": items}, ensure_ascii=False))
        return R(json.dumps(BAD_SCRIPT if MODE["script"] == "bad" else GOOD_SCRIPT, ensure_ascii=False))
class Client:
    models = M()
