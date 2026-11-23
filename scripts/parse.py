import base64
import hashlib
import json
import pathlib
import re
import urllib.parse
from collections import Counter

TMP = pathlib.Path("/tmp/ucsub")
UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def b64_text(s):
    s = s.strip().replace("-", "+").replace("_", "/")
    s += "=" * (-len(s) % 4)
    try:
        return base64.b64decode(s, validate=True).decode("utf-8")
    except Exception:
        return None


def qdict(query):
    return {k: v[0] for k, v in urllib.parse.parse_qs(query, keep_blank_values=True).items()}


def split_hostport(hp):
    hp = hp.strip().rstrip("/")
    if hp.startswith("["):
        host, _, rest = hp[1:].partition("]")
        port = rest.lstrip(":")
    else:
        host, _, port = hp.rpartition(":")
    if not host or not port.isdigit():
        raise ValueError("bad host:port")
    return host, int(port)


def build_stream(p):
    net = p.get("type") or "tcp"
    if net == "raw":
        net = "tcp"
    if net not in ("tcp", "ws", "grpc", "xhttp", "httpupgrade"):
        raise ValueError(f"unsupported network: {net}")

    stream = {"network": net}
    host = p.get("host", "")
    path = p.get("path") or "/"

    if net == "tcp":
        if p.get("headerType") == "http":
            stream["tcpSettings"] = {
                "header": {
                    "type": "http",
                    "request": {"path": [path], "headers": {"Host": [host] if host else []}},
                }
            }
    elif net == "ws":
        ws = {"path": path}
        if host:
            ws["headers"] = {"Host": host}
        stream["wsSettings"] = ws
    elif net == "grpc":
        stream["grpcSettings"] = {
            "serviceName": p.get("serviceName", ""),
            "multiMode": p.get("mode") == "multi",
        }
    elif net == "httpupgrade":
        hu = {"path": path}
        if host:
            hu["host"] = host
        stream["httpupgradeSettings"] = hu
    elif net == "xhttp":
        xh = {"path": path, "mode": p.get("mode") or "auto"}
        if host:
            xh["host"] = host
        extra = p.get("extra")
        if extra:
            try:
                xh["extra"] = json.loads(extra)
            except Exception:
                pass
        stream["xhttpSettings"] = xh

    sec = p.get("security") or "none"
    if sec == "tls":
        alpn = [a for a in (p.get("alpn") or "").split(",") if a]
        tls = {
            "serverName": p.get("sni") or host,
            "fingerprint": p.get("fp") or "chrome",
            "allowInsecure": p.get("insecure") in ("1", "true") or p.get("allowInsecure") in ("1", "true"),
        }
        if alpn:
            tls["alpn"] = alpn
        stream["security"] = "tls"
        stream["tlsSettings"] = tls
    elif sec == "reality":
        stream["security"] = "reality"
        stream["realitySettings"] = {
            "serverName": p.get("sni") or host,
            "fingerprint": p.get("fp") or "chrome",
            "publicKey": p.get("pbk", ""),
            "shortId": p.get("sid", ""),
            "spiderX": p.get("spx") or "/",
        }
    else:
        stream["security"] = "none"
    return stream


def parse_vless(body):
    base, _, query = body.partition("?")
    base = base.rstrip("/")
    uid, sep, hp = base.rpartition("@")
    if not sep:
        raise ValueError("no uuid")
    uid = urllib.parse.unquote(uid)
    addr, port = split_hostport(hp)
    p = qdict(query)

    user = {"id": uid, "encryption": p.get("encryption") or "none"}
    flow = p.get("flow", "")
    if flow.startswith("xtls-rprx-vision"):
        user["flow"] = "xtls-rprx-vision"

    return {
        "protocol": "vless",
        "settings": {"vnext": [{"address": addr, "port": port, "users": [user]}]},
        "streamSettings": build_stream(p),
    }


def parse_ss(body):
    if "plugin=" in body:
        raise ValueError("plugin not supported")
    base, _, query = body.partition("?")
    base = base.rstrip("/")

    if "@" in base:
        userinfo, _, hp = base.rpartition("@")
        mp = b64_text(userinfo)
        if mp is None or ":" not in mp:
            mp = urllib.parse.unquote(userinfo)
    else:
        decoded = b64_text(base)
        if decoded is None or "@" not in decoded:
            raise ValueError("bad ss body")
        mp, _, hp = decoded.rpartition("@")

    if ":" not in mp:
        raise ValueError("no method")
    method, _, password = mp.partition(":")
    addr, port = split_hostport(hp)

    return {
        "protocol": "shadowsocks",
        "settings": {"servers": [{"address": addr, "port": port, "method": method, "password": password}]},
        "streamSettings": build_stream(qdict(query)),
    }


def ss_vmess_obj(body):
    s = body.strip()
    for suffix in ("vless", "vmess"):
        if s.endswith(suffix):
            s = s[: -len(suffix)]
    decoded = b64_text(s)
    if not decoded:
        return None
    try:
        obj = json.loads(decoded)
    except Exception:
        return None
    return obj if isinstance(obj, dict) and "add" in obj else None


def vmess_outbound(o):
    p = {
        "type": o.get("net") or "tcp",
        "headerType": o.get("type") or "",
        "host": o.get("host") or "",
        "path": o.get("path") or "",
        "security": "tls" if o.get("tls") == "tls" else "",
        "sni": o.get("sni") or "",
        "alpn": o.get("alpn") or "",
        "fp": o.get("fp") or "",
        "serviceName": o.get("path") or "",
    }
    return {
        "protocol": "vmess",
        "settings": {
            "vnext": [
                {
                    "address": str(o["add"]),
                    "port": int(o["port"]),
                    "users": [
                        {
                            "id": o["id"],
                            "alterId": int(o.get("aid") or 0),
                            "security": o.get("scy") or "auto",
                        }
                    ],
                }
            ]
        },
        "streamSettings": build_stream(p),
    }


def remark_of(text):
    return urllib.parse.unquote(text.partition("#")[2]).strip()


def parse_link(link):
    if link.startswith("vless://"):
        body = link[len("vless://"):].split("#", 1)[0]
        return {
            "proto": "vless",
            "share": "vless://" + body,
            "remark": remark_of(link),
            "outbound": parse_vless(body),
        }

    if link.startswith("ss://"):
        body = link[len("ss://"):].split("#", 1)[0]
        base = body.partition("?")[0]

        # ss:// wrapping a UUID is really a vless link
        if "@" in base and UUID_RE.match(base.rpartition("@")[0]):
            return {
                "proto": "vless",
                "share": "vless://" + body,
                "remark": remark_of(link),
                "outbound": parse_vless(body),
            }

        # ss:// wrapping base64 JSON is really a vmess link
        obj = ss_vmess_obj(body)
        if obj:
            return {
                "proto": "vmess",
                "vmess": obj,
                "remark": str(obj.get("ps", "")),
                "outbound": vmess_outbound(obj),
            }

        return {
            "proto": "ss",
            "share": "ss://" + body,
            "remark": remark_of(link),
            "outbound": parse_ss(body),
        }

    raise ValueError("unsupported scheme")


def main():
    lines = (TMP / "raw.txt").read_text(encoding="utf-8").splitlines()
    stats = Counter()
    seen = {}

    for link in lines:
        link = link.strip()
        if not link:
            continue
        try:
            rec = parse_link(link)
        except Exception:
            stats["invalid"] += 1
            continue
        rec["id"] = hashlib.sha1(json.dumps(rec["outbound"], sort_keys=True).encode()).hexdigest()[:16]
        if rec["id"] in seen:
            stats["duplicate"] += 1
            continue
        seen[rec["id"]] = rec
        stats[rec["proto"]] += 1

    recs = list(seen.values())
    (TMP / "parsed.json").write_text(json.dumps(recs, ensure_ascii=False), encoding="utf-8")
    print(f"[parse] unique configs: {len(recs)}")
    print(f"[parse] stats: {dict(stats)}")
    if not recs:
        raise SystemExit("[parse] nothing to test")


if __name__ == "__main__":
    main()
