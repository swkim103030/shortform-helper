"""유튜브 연동: 업로드, 채널 댓글 불러오기, 답글 게시 (팀 비밀번호를 아는 사람만 쓸 수 있다)

Secrets에 PC의 token.json 내용을 YOUTUBE_TOKEN으로 넣어 두면 그 채널로 동작한다.
토큰은 서버에만 있고 화면·코드·저장소에는 나오지 않는다.
"""
import io
import json

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
]


class YTError(Exception):
    pass


def _secret(name):
    try:
        import streamlit as st
        return str(st.secrets.get(name, "") or "")
    except Exception:
        import os
        return os.environ.get(name, "")


def configured():
    return bool(_secret("YOUTUBE_TOKEN").strip())


def client():
    from google.auth.exceptions import RefreshError
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    raw = _secret("YOUTUBE_TOKEN").strip()
    if not raw:
        raise YTError("유튜브 계정이 연결되지 않았어요. (Secrets에 YOUTUBE_TOKEN 필요)")
    try:
        creds = Credentials.from_authorized_user_info(json.loads(raw), SCOPES)
    except (ValueError, KeyError) as e:
        raise YTError(f"YOUTUBE_TOKEN 형식이 올바르지 않아요. token.json 내용을 그대로 넣어 주세요. ({type(e).__name__})")
    if not creds.valid:
        try:
            creds.refresh(Request())
        except RefreshError:
            raise YTError("유튜브 로그인이 만료됐어요. PC에서 token.json을 새로 만든 뒤 Secrets를 바꿔 주세요.")
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def _http_error(e):
    try:
        reason = json.loads(e.content)["error"]["errors"][0].get("reason", "")
    except Exception:
        reason = ""
    msg = {"quotaExceeded": "오늘 유튜브 API 사용 한도를 다 썼어요. 내일 다시 시도해 주세요.",
           "uploadLimitExceeded": "채널의 하루 업로드 한도를 넘었어요.",
           "youtubeSignupRequired": "이 계정에 유튜브 채널이 없어요.",
           "forbidden": "이 채널에 권한이 없어요.",
           "commentsDisabled": "이 영상은 댓글이 꺼져 있어요."}.get(reason)
    return YTError(msg or f"유튜브 요청이 실패했어요. ({getattr(e, 'status_code', '')} {reason})")


def channel(yt):
    from googleapiclient.errors import HttpError
    try:
        items = yt.channels().list(part="snippet,contentDetails", mine=True).execute().get("items", [])
    except HttpError as e:
        raise _http_error(e)
    if not items:
        raise YTError("이 계정에 유튜브 채널이 없어요.")
    c = items[0]
    return {"id": c["id"], "title": c["snippet"]["title"],
            "uploads": c["contentDetails"]["relatedPlaylists"]["uploads"]}


def upload(yt, mp4_bytes, title, description, tags, privacy="unlisted", synthetic=False):
    """영상을 올리고 video id를 돌려준다."""
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaIoBaseUpload

    body = {
        "snippet": {"title": title[:100], "description": description[:4900],
                    "tags": [t.lstrip("#") for t in tags][:15], "categoryId": "22"},
        "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False,
                   "containsSyntheticMedia": bool(synthetic)},
    }
    media = MediaIoBaseUpload(io.BytesIO(mp4_bytes), mimetype="video/mp4", resumable=True)
    try:
        req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
        resp = None
        while resp is None:
            _, resp = req.next_chunk()
    except HttpError as e:
        raise _http_error(e)
    return resp["id"], resp.get("status", {}).get("privacyStatus", privacy)


def recent_comments(yt, ch, limit=15):
    """채널 영상에 달린 최근 댓글 중 아직 채널이 답하지 않은 것"""
    from googleapiclient.errors import HttpError
    try:
        resp = yt.commentThreads().list(part="snippet,replies", allThreadsRelatedToChannelId=ch["id"],
                                        maxResults=50, order="time", textFormat="plainText").execute()
    except HttpError as e:
        raise _http_error(e)
    out = []
    for th in resp.get("items", []):
        top = th["snippet"]["topLevelComment"]["snippet"]
        if top.get("authorChannelId", {}).get("value") == ch["id"]:
            continue  # 채널 주인이 쓴 댓글
        replies = th.get("replies", {}).get("comments", [])
        if any(r["snippet"].get("authorChannelId", {}).get("value") == ch["id"] for r in replies):
            continue  # 이미 답함
        out.append({"thread_id": th["id"], "video_id": th["snippet"].get("videoId", ""),
                    "author": top.get("authorDisplayName", ""), "text": top.get("textDisplay", "").strip()})
        if len(out) >= limit:
            break
    return out


def reply(yt, thread_id, text):
    from googleapiclient.errors import HttpError
    try:
        yt.comments().insert(part="snippet", body={"snippet": {"parentId": thread_id, "textOriginal": text}}).execute()
    except HttpError as e:
        raise _http_error(e)


def recent_stats(yt, ch, limit=5):
    """채널에 최근 올린 영상의 조회수·좋아요·댓글 수"""
    from googleapiclient.errors import HttpError
    try:
        pl = yt.playlistItems().list(part="contentDetails", playlistId=ch["uploads"], maxResults=limit).execute()
        ids = [i["contentDetails"]["videoId"] for i in pl.get("items", [])]
        if not ids:
            return []
        vids = yt.videos().list(part="snippet,statistics", id=",".join(ids)).execute().get("items", [])
    except HttpError as e:
        raise _http_error(e)
    out = []
    for v in vids:
        st_ = v.get("statistics", {})
        out.append({"title": v["snippet"]["title"], "date": v["snippet"].get("publishedAt", "")[:10],
                    "views": int(st_.get("viewCount", 0)), "likes": int(st_.get("likeCount", 0)),
                    "comments": int(st_.get("commentCount", 0)), "url": f"https://youtu.be/{v['id']}"})
    return out
