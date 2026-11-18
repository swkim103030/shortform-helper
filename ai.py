"""생성형 AI 호출 (Google Gemini API)

- API 키는 코드에 넣지 않는다. Streamlit Cloud의 Secrets(서버 측)나 환경변수에서만 읽는다.
- AI 결과는 JSON으로 받아 형식을 검사하고, 실패하면 사용자에게 보여 줄 한국어 안내 메시지로 바꾼다.
- 실패하면 원인(모델, 종료 사유 등)을 detail에 담아 화면의 '자세한 원인'에 보여 준다. 키는 절대 담지 않는다.
"""
import json
import os
import re
import time

# 앞의 모델이 없으면(404) 다음 모델로 넘어간다
DEFAULT_MODELS = ["gemini-flash-latest", "gemini-2.5-flash", "gemini-flash-lite-latest"]
MAX_OUTPUT_TOKENS = 16384  # 최신 모델은 '생각하는 분량'도 여기에 포함되므로 넉넉하게


class AIError(Exception):
    """사용자에게 그대로 보여 줄 수 있는 안내 메시지를 담는 오류"""

    def __init__(self, message, detail=""):
        super().__init__(message)
        self.detail = detail


def _get_secret(name):
    try:
        import streamlit as st
        if name in st.secrets:
            return str(st.secrets[name])
    except Exception:  # secrets 파일이 없을 때 (로컬 실행)
        pass
    return os.environ.get(name, "")


def _models():
    chosen = _get_secret("GEMINI_MODEL").strip()
    return ([chosen] if chosen else []) + [m for m in DEFAULT_MODELS if m != chosen]


def _client():
    key = _get_secret("GEMINI_API_KEY").strip().strip('"').strip("'")
    if not key:
        raise AIError("AI 키가 설정되지 않았습니다. 관리자에게 문의해 주세요. (Secrets에 GEMINI_API_KEY 필요)")
    from google import genai
    return genai.Client(api_key=key)


def _parse_json(text):
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)  # 코드 블록으로 감싸 온 경우
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("JSON 없음")
    return json.loads(m.group(0))


def _finish_reason(resp):
    try:
        fr = resp.candidates[0].finish_reason
        return getattr(fr, "name", str(fr))
    except Exception:
        try:
            return f"차단됨({resp.prompt_feedback.block_reason})"
        except Exception:
            return "알 수 없음"


def _text(resp):
    try:
        return resp.text or ""
    except Exception:
        return ""


def generate_json(system, prompt, required_keys, temperature=0.9, _client_factory=None):
    """Gemini에 JSON 형식 결과를 요청한다. 반환: (dict, 사용한 모델 이름)"""
    from google.genai import errors, types

    client = (_client_factory or _client)()
    config = types.GenerateContentConfig(
        system_instruction=system,
        response_mime_type="application/json",
        temperature=temperature,
        max_output_tokens=MAX_OUTPUT_TOKENS,
    )
    log = []  # 시도 기록 (화면의 '자세한 원인'에 표시)
    for model in _models():
        for attempt in range(2):  # 형식이 깨졌거나 일시 오류면 한 번 더
            try:
                resp = client.models.generate_content(model=model, contents=prompt, config=config)
            except errors.APIError as e:
                code = getattr(e, "code", None)
                msg = str(getattr(e, "message", "") or e)[:150]
                log.append(f"{model}: API 오류 {code} {msg}")
                if code == 404:  # 모델 이름이 없으면 다음 모델로
                    break
                if code in (401, 403) or (code == 400 and "key" in msg.lower()):
                    raise AIError("AI 키가 올바르지 않습니다. 관리자에게 문의해 주세요.", "\n".join(log)) from None
                if code == 429:
                    raise AIError("지금 요청이 많아 AI가 잠시 쉬는 중이에요. 1분쯤 뒤에 다시 시도해 주세요.",
                                  "\n".join(log)) from None
                if code and code >= 500 and attempt == 0:
                    time.sleep(1.5)
                    continue
                raise AIError(f"AI 호출에 실패했습니다. 잠시 후 다시 시도해 주세요. (오류 코드 {code})",
                              "\n".join(log)) from None
            except AIError:
                raise
            except Exception as e:  # 네트워크 문제 등
                log.append(f"{model}: 연결 오류 {type(e).__name__}")
                raise AIError("AI 서버에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.", "\n".join(log)) from e

            text, reason = _text(resp), _finish_reason(resp)
            try:
                data = _parse_json(text)
                missing = [k for k in required_keys if k not in data]
                if missing:
                    raise ValueError(f"항목 누락 {missing}")
                return data, model
            except (ValueError, json.JSONDecodeError) as e:
                log.append(f"{model}: 결과 해석 실패 ({type(e).__name__}: {str(e)[:60]}) · 종료 사유 {reason} · "
                           f"받은 글자 수 {len(text)}")
                continue
    raise AIError("AI 결과를 정리하지 못했습니다. 입력을 조금 바꿔 다시 시도해 주세요.", "\n".join(log))
