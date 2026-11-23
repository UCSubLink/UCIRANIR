import json
import os
import pathlib
import socket
import statistics
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor

TMP = pathlib.Path("/tmp/ucsub")
XRAY = os.environ.get("XRAY_BIN", "xray")
TEST_URL = "https://www.gstatic.com/generate_204"
BASE_PORT = 20000
CONC = int(os.environ.get("CONC", "12"))
ROUNDS = 3
MAX_MS = 1500
TIMEOUT = 8


def wait_port(port, timeout=6):
    end = time.time() + timeout
    while time.time() < end:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def curl_once(port):
    cmd = [
        "curl", "-s", "-o", "/dev/null",
        "-w", "%{http_code} %{time_total}",
        "--max-time", str(TIMEOUT),
        "--socks5-hostname", f"127.0.0.1:{port}",
        TEST_URL,
    ]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT + 5).stdout.split()
        if len(out) == 2 and out[0] == "204":
            return float(out[1]) * 1000
    except Exception:
        pass
    return None


def test_one(args):
    idx, rec = args
    port = BASE_PORT + idx
    cfg = {
        "log": {"loglevel": "none"},
        "inbounds": [{
            "listen": "127.0.0.1",
            "port": port,
            "protocol": "socks",
            "settings": {"udp": False},
        }],
        "outbounds": [dict(rec["outbound"], tag="proxy")],
    }
    cfg_path = TMP / f"cfg_{idx}.json"
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")

    proc = subprocess.Popen(
        [XRAY, "run", "-c", str(cfg_path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    samples = []
    try:
        if wait_port(port):
            for _ in range(ROUNDS):
                ms = curl_once(port)
                if ms is None:
                    break
                samples.append(ms)
    finally:
        proc.kill()
        proc.wait()
        cfg_path.unlink(missing_ok=True)

    ok = len(samples) == ROUNDS and statistics.median(samples) < MAX_MS
    latency = round(statistics.median(samples)) if samples else None
    return {"id": rec["id"], "ok": ok, "latency": latency, "samples": samples}


def main():
    recs = json.loads((TMP / "alive.json").read_text(encoding="utf-8"))
    print(f"[test] testing {len(recs)} configs with concurrency {CONC}")

    results = []
    with ThreadPoolExecutor(max_workers=CONC) as ex:
        for i, res in enumerate(ex.map(test_one, enumerate(recs))):
            results.append(res)
            if (i + 1) % 50 == 0:
                print(f"[test] progress {i + 1}/{len(recs)}")

    healthy = sum(1 for r in results if r["ok"])
    print(f"[test] healthy: {healthy} / {len(results)}")
    (TMP / "results.json").write_text(json.dumps(results), encoding="utf-8")


if __name__ == "__main__":
    main()
