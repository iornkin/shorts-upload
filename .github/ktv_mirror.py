"""KTV 거울 (사용자가 GitHub 저장소 iornkin/shorts-upload에 직접 설치해 돌리는 것, 2026-10-10).

KTV(국민방송) 영상은 공공저작물(저작권법 24조의2, 2025-07 전면 개방). KTV 영상 서버는 8443 포트라
쇼츠 제작 환경에서 못 받으므로, 이 작업이 1시간마다 KTV 새 영상 중 정치·정부 영상을 받아
이 저장소의 릴리스(ktv-YYYYMMDD)에 올리고 목록(ktv-index 릴리스의 index.json)을 갱신한다.
쇼츠 제작 환경은 공개된 이 파일만 내려받아 쓴다. 7일 지난 릴리스는 지운다.
"""
import datetime as dt, json, os, re, subprocess, sys, urllib.parse, urllib.request
from pathlib import Path

UA = {"User-Agent": "Mozilla/5.0"}
PROXY = "https://www.ktv.go.kr/content/playerProxy?http://hdvod.ktv.go.kr:8080"
STREAM = "https://hdvod.ktv.go.kr:8443/streams/_definst_"
WORDS = ["대통령", "영부인", "국무회의", "국무총리", "총리", "장관", "차관", "브리핑", "청와대", "대통령실", "국회", "정부", "회견",
         "정상회담", "회담", "대담", "간담회", "연설", "현안", "정책", "국정", "외교", "안보", "국방", "북한", "통일",
         "이재명", "김민석", "한성숙", "정청래", "장동혁", "조희대", "한동훈", "조국", "오세훈", "윤석열", "김건희",
         "이준석", "홍준표", "안철수", "추미애", "나경원", "김병주", "주진우", "정동영", "강훈식", "위성락"]
MAX_SEC = 20 * 60
KEEP_DAYS = 7
OUT = Path("ktv_out")


def get(url, ref="https://www.ktv.go.kr/"):
    req = urllib.request.Request(url, headers={**UA, "Referer": ref})
    return urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace")


def candidates():
    ids = set(re.findall(r"content_id=(\d+)", get("https://www.ktv.go.kr/")))
    for w in ["이재명 대통령", "국무회의", "브리핑", "국회", "청와대"]:
        try:
            ids |= set(re.findall(r"content_id=(\d+)", get("https://www.ktv.go.kr/totalSearch?keyword=" + urllib.parse.quote(w))))
        except Exception as e:
            print("search fail", w, e)
    return sorted(ids, reverse=True)


def info(cid):
    page = get(f"https://www.ktv.go.kr/content/player?content_id={cid}")
    fid = re.search(r'fileId\s*:\s*"([0-9a-f-]{36})"', page).group(1)
    xml = get(f"{PROXY}/rest/file/view/{fid}", f"https://www.ktv.go.kr/content/player?content_id={cid}")
    streams = {re.search(r"<settName>([^<]*)", b).group(1): f"{STREAM}{re.search(r'<url>([^<]*)', b).group(1)}/playlist.m3u8"
               for b in re.findall(r"<stream>(.*?)</stream>", xml, re.S)}
    view = get(f"https://www.ktv.go.kr/content/view?content_id={cid}")
    meta = lambda p: (re.search(rf"""<meta property=["']og:{p}["'] content=["']([^"']*)["']""", view) or [None, ""])[1]  # noqa: E731
    created = (re.search(r"<createDate>([^<]*)", xml) or [None, ""])[1]
    return {"content_id": cid, "title": meta("title"), "description": meta("description")[:500],
            "duration": int(re.search(r"<playTime>(\d+)", xml).group(1)), "created": created,
            "page": f"https://www.ktv.go.kr/content/view?content_id={cid}", "streams": streams}


def gh(*a, check=True):
    return subprocess.run(["gh", *a], capture_output=True, text=True, check=check).stdout


def main():
    OUT.mkdir(exist_ok=True)
    try:
        gh("release", "download", "ktv-index", "-p", "index.json", "-D", str(OUT), "--clobber")
        index = json.loads((OUT / "index.json").read_text("utf-8"))
    except Exception:
        index = []
    index = [e for e in index if not (e.get("skipped") and not e.get("title"))]  # 제목을 못 읽어 건너뛴 것은 다시 봄
    have = {e["content_id"] for e in index}
    today = dt.datetime.utcnow().strftime("%Y%m%d")
    tag = f"ktv-{today}"
    if gh("release", "view", tag, check=False) == "":
        gh("release", "create", tag, "-t", tag, "-n", "KTV 공공저작물 영상 (저작권법 24조의2)", check=False)
    added = 0
    for cid in candidates():
        if cid in have or added >= 25:
            continue
        try:
            m = info(cid)
        except Exception as e:
            print("info fail", cid, e)
            continue
        text = m["title"] + " " + m["description"]
        if m["duration"] > MAX_SEC or not any(w in text for w in WORDS):
            index.append({"content_id": cid, "skipped": True, "title": m["title"]})
            continue
        src = next((m["streams"][k] for k in ("720P", "1080P", "480P", "360P") if k in m["streams"]), None)
        if not src:
            continue
        f = OUT / f"ktv_{cid}.mp4"
        r = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-c", "copy", "-movflags", "+faststart", str(f)])
        if r.returncode or not f.exists():
            print("download fail", cid)
            continue
        gh("release", "upload", tag, str(f), "--clobber")
        m.pop("streams")
        m.update(asset=f"https://github.com/{os.environ['GITHUB_REPOSITORY']}/releases/download/{tag}/{f.name}",
                 license="KTV 공공저작물 (저작권법 제24조의2) — 출처: KTV 국민방송")
        index.append(m)
        added += 1
        f.unlink()
        print("added", cid, m["title"])
    cut = (dt.datetime.utcnow() - dt.timedelta(days=KEEP_DAYS)).strftime("%Y%m%d")
    for line in gh("release", "list", "-L", "100").splitlines():
        t = line.split("\t")[2] if line.count("\t") >= 2 else ""
        if t.startswith("ktv-2") and t[4:] < cut:
            gh("release", "delete", t, "-y", "--cleanup-tag", check=False)
    index = [e for e in index if e.get("skipped") or e.get("asset", "").split("/download/ktv-")[-1][:8] >= cut][-3000:]
    (OUT / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1), "utf-8")
    if gh("release", "view", "ktv-index", check=False) == "":
        gh("release", "create", "ktv-index", "-t", "ktv-index", "-n", "KTV 거울 목록", check=False)
    gh("release", "upload", "ktv-index", str(OUT / "index.json"), "--clobber")
    print("done, added", added)


if __name__ == "__main__":
    sys.exit(main())
