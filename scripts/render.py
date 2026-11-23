import base64
import json
import pathlib
import re
import urllib.parse

ROOT = pathlib.Path(__file__).resolve().parent.parent
TMP = pathlib.Path("/tmp/ucsub")
PREFIX = "Telegram: @UCIRANIR"

ISO_CODES = set("""
AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI BJ BL BM BN BO BQ BR BS BT BV BW BY BZ
CA CC CD CF CG CH CI CK CL CM CN CO CR CU CV CW CX CY CZ DE DJ DK DM DO DZ EC EE EG EH ER ES ET FI FJ FK FM FO
FR GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS GT GU GW GY HK HM HN HR HT HU ID IE IL IM IN IO IQ IR IS IT JE
JM JO JP KE KG KH KI KM KN KP KR KW KY KZ LA LB LC LI LK LR LS LT LU LV LY MA MC MD ME MF MG MH MK ML MM MN MO
MP MQ MR MS MT MU MV MW MX MY MZ NA NC NE NF NG NI NL NO NP NR NU NZ OM PA PE PF PG PH PK PL PM PN PR PS PT PW
PY QA RE RO RS RU RW SA SB SC SD SE SG SH SI SJ SK SL SM SN SO SR SS ST SV SX SY SZ TC TD TF TG TH TJ TK TL TM
TN TO TR TT TV TW TZ UA UG UM US UY UZ VA VC VE VG VI VN VU WF WS YE YT ZA ZM ZW
""".split())

# Short words that look like country codes but are usually not countries in a name
STOP_CODES = {"IN", "IT", "IS", "ON", "OR", "AT", "TO", "AS", "BE", "BY", "ME", "OK", "NO", "DO",
              "GO", "AM", "AN", "UP", "WE", "OF", "IF", "MY", "SO", "HI", "ID", "TG"}

NAME_MAP = {
    "united states": "US", "united kingdom": "GB", "great britain": "GB", "britain": "GB",
    "england": "GB", "scotland": "GB", "uk": "GB", "usa": "US", "america": "US",
    "germany": "DE", "france": "FR", "netherlands": "NL", "holland": "NL", "iran": "IR",
    "japan": "JP", "singapore": "SG", "finland": "FI", "sweden": "SE", "turkey": "TR",
    "turkiye": "TR", "russia": "RU", "canada": "CA", "hong kong": "HK", "poland": "PL",
    "estonia": "EE", "latvia": "LV", "lithuania": "LT", "armenia": "AM", "georgia": "GE",
    "austria": "AT", "switzerland": "CH", "italy": "IT", "spain": "ES", "brazil": "BR",
    "india": "IN", "china": "CN", "korea": "KR", "taiwan": "TW", "uae": "AE",
    "emirates": "AE", "israel": "IL", "qatar": "QA", "kazakhstan": "KZ", "ukraine": "UA",
    "romania": "RO", "bulgaria": "BG", "czech": "CZ", "ireland": "IE", "norway": "NO",
    "denmark": "DK", "belgium": "BE", "australia": "AU", "malaysia": "MY", "vietnam": "VN",
    "thailand": "TH", "indonesia": "ID", "pakistan": "PK", "iraq": "IQ", "azerbaijan": "AZ",
    "moldova": "MD", "hungary": "HU", "serbia": "RS", "portugal": "PT", "greece": "GR",
    "saudi": "SA", "bahrain": "BH", "kuwait": "KW", "oman": "OM", "philippines": "PH",
    "mexico": "MX", "argentina": "AR", "chile": "CL", "colombia": "CO", "peru": "PE",
    "new zealand": "NZ", "south africa": "ZA", "egypt": "EG", "nigeria": "NG",
    "kenya": "KE", "morocco": "MA", "tunisia": "TN", "algeria": "DZ", "afghanistan": "AF",
}

REGIONAL_RE = re.compile(r"[\U0001F1E6-\U0001F1FF]{2}")
CODE_RE = re.compile(r"(?<![A-Za-z])([A-Za-z]{2})(?![A-Za-z])")
NAMES_SORTED = sorted(NAME_MAP, key=len, reverse=True)


def flag_from_code(code):
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in code.upper())


def detect_flag(remark):
    m = REGIONAL_RE.search(remark)
    if m:
        return m.group(0)

    low = remark.lower()
    for name in NAMES_SORTED:
        if re.search(r"(?<![a-z])" + re.escape(name) + r"(?![a-z])", low):
            return flag_from_code(NAME_MAP[name])

    for tok in CODE_RE.findall(remark):
        t = tok.upper()
        if t in ISO_CODES and t not in STOP_CODES:
            return flag_from_code(t)
    return ""


def main():
    selected = json.loads((TMP / "selected.json").read_text(encoding="utf-8"))
    if not selected:
        print("[render] no healthy configs; keeping previous output")
        return

    lines = []
    flagged = 0
    for i, rec in enumerate(selected, 1):
        flag = detect_flag(rec.get("remark", ""))
        if flag:
            flagged += 1
        name = f"{flag} {PREFIX} {i}" if flag else f"{PREFIX} {i}"

        if rec["proto"] == "vmess":
            obj = dict(rec["vmess"])
            obj["ps"] = name
            encoded = base64.b64encode(json.dumps(obj, ensure_ascii=False).encode("utf-8")).decode()
            lines.append("vmess://" + encoded)
        else:
            lines.append(rec["share"] + "#" + urllib.parse.quote(name, safe=""))

    text = "\n".join(lines) + "\n"
    (ROOT / "output" / "X.txt").write_text(text, encoding="utf-8")
    (ROOT / "output" / "X_base64.txt").write_text(
        base64.b64encode(text.encode("utf-8")).decode() + "\n", encoding="utf-8"
    )
    print(f"[render] wrote {len(lines)} configs ({flagged} with country flag)")


if __name__ == "__main__":
    main()
