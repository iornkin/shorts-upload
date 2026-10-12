"""tts/request.json의 줄들을 Microsoft Edge 음성(InJoon 등)으로 합성 → tts/out/<id>/<key>.mp3
(클라우드 작업 서버에서는 Edge가 403으로 막혀서 GitHub Actions에서 대신 만듦, 사용자 허락 10-12)"""
import asyncio, json, pathlib, edge_tts

req = json.load(open("tts/request.json"))
out = pathlib.Path("tts/out") / req["id"]
out.mkdir(parents=True, exist_ok=True)


async def one(r):
    for i in range(4):
        try:
            c = edge_tts.Communicate(r["text"], r["voice"], rate=r["rate"], pitch=r["pitch"])
            await c.save(str(out / f"{r['key']}.mp3"))
            return
        except Exception as e:
            print("retry", r["key"], e)
            await asyncio.sleep(2)
    raise SystemExit("failed " + r["key"])


async def main():
    for r in req["lines"]:
        await one(r)

asyncio.run(main())
print("done", len(req["lines"]))
