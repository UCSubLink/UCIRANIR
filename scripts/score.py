import datetime as dt
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
TMP = pathlib.Path("/tmp/ucsub")
STATE = ROOT / "state" / "health.json"
TOP = 200
KEEP_DAYS = 7
HISTORY = 10


def main():
    parsed = json.loads((TMP / "parsed.json").read_text(encoding="utf-8"))
    dead_ids = json.loads((TMP / "precheck.json").read_text(encoding="utf-8"))["dead_ids"]
    results = {r["id"]: r for r in json.loads((TMP / "results.json").read_text(encoding="utf-8"))}
    by_id = {r["id"]: r for r in parsed}

    state = json.loads(STATE.read_text(encoding="utf-8") or "{}")
    now = dt.datetime.now(dt.timezone.utc)
    now_s = now.isoformat()

    def push(rid, ok, latency):
        h = state.setdefault(rid, {"runs": [], "latency": None, "last_seen": None})
        h["runs"] = (h["runs"] + [bool(ok)])[-HISTORY:]
        if latency is not None:
            h["latency"] = latency
        h["last_seen"] = now_s

    for rid in dead_ids:
        push(rid, False, None)
    for rid, r in results.items():
        push(rid, r["ok"], r["latency"])

    cutoff = now - dt.timedelta(days=KEEP_DAYS)
    for rid in list(state):
        seen = dt.datetime.fromisoformat(state[rid]["last_seen"])
        if seen < cutoff:
            del state[rid]

    candidates = []
    for rid, r in results.items():
        if not r["ok"] or rid not in by_id:
            continue
        runs = state[rid]["runs"]
        stability = sum(runs) / len(runs)
        score = stability * 1000 - r["latency"]
        candidates.append((score, rid))
    candidates.sort(reverse=True)

    selected = [by_id[rid] for _, rid in candidates[:TOP]]
    (TMP / "selected.json").write_text(json.dumps(selected, ensure_ascii=False), encoding="utf-8")
    STATE.write_text(json.dumps(state, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"[score] selected: {len(selected)} (healthy candidates: {len(candidates)})")


if __name__ == "__main__":
    main()
