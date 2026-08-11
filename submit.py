"""Поставить задачу через веб-API (UTF-8 без сюрпризов PowerShell)."""

import sys
import time

import httpx

topic = sys.argv[1] if len(sys.argv) > 1 else "Почему коты мурлыкают"

with httpx.Client(trust_env=False, base_url="http://127.0.0.1:8420", timeout=60) as c:
    job = c.post("/api/jobs", json={
        "topic": topic, "duration": 30, "voice": "baya", "music": True, "fresh": False,
    }).json()
    print("job:", job["id"], "|", job["topic"])

    while True:
        job = c.get(f"/api/jobs/{job['id']}").json()
        print(f"  {job['status']:8} {job['step']:9} {job['detail'][:50]}")
        if job["status"] in ("done", "failed"):
            break
        time.sleep(6)

print("error:", job["error"]) if job["error"] else print("видео:", job["result"]["video"])
print("ссылка: http://127.0.0.1:8420/?job=" + job["id"])
