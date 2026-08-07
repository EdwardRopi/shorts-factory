"""Проверка режима витрины без поднятия сервера."""

from fastapi.testclient import TestClient

from app.web.api import app

with TestClient(app) as c:
    cfg = c.get("/api/config").json()
    print("demo:", cfg["demo"], "| голосов:", len(cfg["voices"]),
          "| шагов:", len(cfg["steps"]))

    lib = c.get("/api/library").json()["items"]
    print("роликов на витрине:", len(lib))
    for m in lib:
        print(f"   {m['title'][:44]:44} {m['seconds']} с  {m['video']}")

    r = c.post("/api/jobs", json={"topic": "проверка блокировки"})
    print("POST /api/jobs ->", r.status_code)
    print("  ", r.json().get("detail", "")[:110])

    if lib:
        v = c.get(f"/videos/{lib[0]['video']}")
        print("отдача видео ->", v.status_code, v.headers.get("content-type"))

    print("страница ->", c.get("/").status_code)
