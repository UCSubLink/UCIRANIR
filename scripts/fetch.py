import base64
import pathlib
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
TMP = pathlib.Path("/tmp/ucsub")
TMP.mkdir(parents=True, exist_ok=True)
PREFIXES = ("vless://", "ss://")


def read_sources():
    urls = []
    for line in (ROOT / "sources.txt").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            urls.append(line)
    return urls


def download(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def maybe_decode_base64(text):
    if any(p in text for p in PREFIXES):
        return text
    s = "".join(text.split())
    s += "=" * (-len(s) % 4)
    try:
        return base64.b64decode(s).decode("utf-8", errors="replace")
    except Exception:
        return text


def main():
    seen = set()
    lines = []
    for url in read_sources():
        try:
            text = maybe_decode_base64(download(url))
        except Exception as e:
            print(f"[fetch] FAILED {url}: {e}")
            continue
        count = 0
        for raw in text.splitlines():
            link = raw.strip()
            if link.startswith(PREFIXES) and link not in seen:
                seen.add(link)
                lines.append(link)
                count += 1
        print(f"[fetch] {url} -> {count} links")

    if not lines:
        raise SystemExit("[fetch] no vless/ss links fetched")

    (TMP / "raw.txt").write_text("\n".join(lines), encoding="utf-8")
    print(f"[fetch] total unique raw links: {len(lines)}")


if __name__ == "__main__":
    main()
