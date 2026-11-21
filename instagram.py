"""인스타그램 릴스 업로드 (Instagram API with Instagram Login)

- Secrets의 INSTAGRAM_TOKEN(메타 개발자 대시보드에서 만든 토큰)으로 동작한다. 토큰은 서버에만 있다.
- 인스타는 영상 파일을 직접 받지 않고, 메타 서버가 '공개 주소'에서 영상을 가져간다.
  그래서 Streamlit이 화면에 영상을 띄울 때 쓰는 주소(/media/….mp4)를 넘긴다.
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

IG_API = "https://graph.instagram.com"      # Instagram 로그인 토큰 (IGAA…)
FB_API = "https://graph.facebook.com/v23.0" # 통합(비즈니스용 Facebook) 로그인 토큰 (EAA…)
DEFAULT_APP_URL = "https://shorts-marketing-ai.streamlit.app/~/+"  # Streamlit Cloud에서 앱 내부 주소


class IGError(Exception):
    pass


def _secret(name):
    try:
        import streamlit as st
        return str(st.secrets.get(name, "") or "").strip()
    except Exception:
        import os
        return os.environ.get(name, "").strip()


def configured():
    return bool(_secret("INSTAGRAM_TOKEN"))


def _api():
    """토큰 종류에 따라 호출할 서버를 고른다"""
    return FB_API if _secret("INSTAGRAM_TOKEN").startswith("EA") else IG_API


def _call(method, path, **params):
    params["access_token"] = _secret("INSTAGRAM_TOKEN")
    data = urllib.parse.urlencode(params).encode()
    url = f"{_api()}/{path}"
    if method == "GET":
        req = urllib.request.Request(f"{url}?{data.decode()}")
    else:
        req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read().decode("utf-8")).get("error", {})
        except Exception:
            err = {}
        code, msg = err.get("code"), err.get("error_user_msg") or err.get("message", "")
        if code == 190:
            raise IGError("인스타 로그인 토큰이 만료됐거나 올바르지 않아요. 메타 대시보드에서 토큰을 새로 만들어 Secrets를 바꿔 주세요.")
        if code in (4, 9, 17, 32, 613):
            raise IGError("인스타 업로드 한도에 걸렸어요. 잠시 뒤에 다시 시도해 주세요.")
        if code == 10 or code == 200:
            raise IGError("인스타 계정에 게시 권한이 없어요. 프로페셔널 계정인지, 토큰에 게시 권한이 있는지 확인해 주세요.")
        raise IGError(f"인스타 요청이 실패했어요. ({e.code} {str(msg)[:120]})")
    except urllib.error.URLError as e:
        raise IGError(f"인스타 서버에 연결하지 못했어요. ({type(e.reason).__name__})")


def account():
    """올릴 인스타 계정 (id, 사용자 이름)"""
    fixed = _secret("INSTAGRAM_USER_ID")
    if _api() == IG_API:
        me = _call("GET", "me", fields="user_id,username")
        return {"id": fixed or str(me.get("user_id") or me.get("id")), "username": me.get("username", "")}
    # 페이스북 계열 토큰: 연결된 인스타 비즈니스 계정을 찾는다
    if fixed:
        info = _call("GET", fixed, fields="username")
        return {"id": fixed, "username": info.get("username", "")}
    for path, field in (("me/accounts", "instagram_business_account{id,username}"),
                        ("me/instagram_accounts", "id,username")):
        try:
            res = _call("GET", path, fields=field)
        except IGError:
            continue
        for item in res.get("data", []):
            ig = item.get("instagram_business_account") or (item if path.endswith("instagram_accounts") else None)
            if ig and ig.get("id"):
                return {"id": str(ig["id"]), "username": ig.get("username", "")}
    raise IGError("토큰에 연결된 인스타 계정을 찾지 못했어요. (관리자: Secrets에 INSTAGRAM_USER_ID 추가)")


def public_video_url(mp4_bytes):
    """화면에 띄운 영상과 같은 파일의 공개 주소를 만든다 (Streamlit 미디어 저장소)."""
    from streamlit import runtime
    if not runtime.exists():
        raise IGError("공개 주소를 만들 수 없어요. (Streamlit 서버에서만 가능)")
    path = runtime.get_instance().media_file_mgr.add(mp4_bytes, "video/mp4", "instagram_upload")
    base = (_secret("APP_PUBLIC_URL") or DEFAULT_APP_URL).rstrip("/")
    return f"{base}{path}"


def publish_reel(mp4_bytes, caption, progress=None, wait_sec=240):
    """릴스로 올리고 (게시물 id, 링크)를 돌려준다."""
    say = progress or (lambda m: None)
    acct = account()
    url = public_video_url(mp4_bytes)
    say("인스타에 영상을 넘기는 중...")
    box = _call("POST", f"{acct['id']}/media", media_type="REELS", video_url=url,
                caption=caption[:2200], share_to_feed="true")
    cid = box.get("id")
    if not cid:
        raise IGError("인스타가 업로드를 받지 않았어요.")
    start = time.time()
    while True:  # 인스타가 영상을 가져가 변환할 때까지 기다린다
        st_ = _call("GET", cid, fields="status_code,status")
        code = st_.get("status_code")
        if code == "FINISHED":
            break
        if code in ("ERROR", "EXPIRED"):
            raise IGError(f"인스타가 영상을 처리하지 못했어요. ({str(st_.get('status', code))[:120]})")
        if time.time() - start > wait_sec:
            raise IGError("인스타 처리 시간이 너무 길어요. 잠시 뒤 인스타 앱에서 게시됐는지 확인해 주세요.")
        say(f"인스타가 영상을 처리하는 중... ({int(time.time() - start)}초)")
        time.sleep(5)
    pub = _call("POST", f"{acct['id']}/media_publish", creation_id=cid)
    mid = pub.get("id")
    link = ""
    try:
        link = _call("GET", mid, fields="permalink").get("permalink", "")
    except IGError:
        pass
    return mid, link or f"https://www.instagram.com/{acct['username']}/"
