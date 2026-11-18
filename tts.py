"""나레이션 → 음성 파일 (edge-tts 무료 음성, 실패하면 무음 자리표시)"""
import asyncio
import shutil
import subprocess

from mutagen.mp3 import MP3


def ffmpeg_exe():
    path = shutil.which("ffmpeg")
    if path:
        return path
    import imageio_ffmpeg  # pip로 설치되는 ffmpeg (Windows에서 편함)

    return imageio_ffmpeg.get_ffmpeg_exe()


async def _edge_tts(text, voice, out_path):
    import edge_tts

    await edge_tts.Communicate(text, voice, rate="+8%").save(out_path)


def silence(seconds, out_path):
    subprocess.run(
        [ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi", "-i",
         "anullsrc=r=24000:cl=mono", "-t", f"{seconds:.2f}", "-q:a", "9", str(out_path)],
        check=True,
    )


def synthesize(text, voice, out_path, try_tts=True):
    """음성을 만들고 (길이, 성공 여부, 오류)를 돌려준다. 실패하면 무음으로 자리를 채운다."""
    err = ""
    if try_tts:
        try:
            asyncio.run(_edge_tts(text, voice, str(out_path)))
            return MP3(out_path).info.length, True, ""
        except Exception as e:
            err = type(e).__name__
    silence(max(2.0, len(text) * 0.13), out_path)
    return MP3(out_path).info.length, False, err or "skipped"
