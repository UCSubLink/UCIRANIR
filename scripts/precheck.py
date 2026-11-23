import json
import pathlib
import socket
from concurrent.futures import ThreadPoolExecutor

TMP = pathlib.Path("/tmp/ucsub")


def endpoint(rec):
    st = rec["outbound"]["settings"]
    e = st["vnext"][0] if "vnext" in st else st["servers"][0]
    return e["address"], e["port"]


def alive(rec):
    try:
        with socket.create_connection(endpoint(rec), timeout=3):
            return True
    except OSError:
        return False


def main():
    recs = json.loads((TMP / "parsed.json").read_text(encoding="utf-8"))
    with ThreadPoolExecutor(max_workers=100) as ex:
        flags = list(ex.map(alive, recs))

    ok = [r for r, f in zip(recs, flags) if f]
    dead_ids = [r["id"] for r, f in zip(recs, flags) if not f]

    (TMP / "alive.json").write_text(json.dumps(ok, ensure_ascii=False), encoding="utf-8")
    (TMP / "precheck.json").write_text(json.dumps({"dead_ids": dead_ids}), encoding="utf-8")
    print(f"[precheck] alive: {len(ok)}  dead: {len(dead_ids)}")


if __name__ == "__main__":
    main()
