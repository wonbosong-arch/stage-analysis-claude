"""종목 목록 갱신: 미국(Nasdaq 스크리너) + 한국(네이버 금융)에서 시총 $1B 이상 종목을 stocks.csv 로 저장"""
import re, csv, os, sys, requests
FX = float(os.environ.get("USDKRW", "1400")); MIN_USD = 1e9
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"}

def us():
    out = []
    for ex, code in [("nasdaq", "NAS"), ("nyse", "NYS"), ("amex", "AMS")]:
        j = requests.get("https://api.nasdaq.com/api/screener/stocks", params={"tableonly": "true", "limit": "25000", "exchange": ex, "download": "true"}, headers=UA, timeout=60).json()["data"]
        for r in j.get("rows") or j["table"]["rows"]:
            s = (r.get("symbol") or "").strip()
            try: cap = float((r.get("marketCap") or "0").replace(",", "").replace("$", ""))
            except ValueError: cap = 0
            if re.fullmatch(r"[A-Z]{1,5}", s) and cap >= MIN_USD:
                out.append(["stock", f"US_{s}", (r.get("name") or s)[:40].replace(",", " "), "US", code, s, (r.get("sector") or "Other").replace(",", " "), round(cap / 1e9, 2)])
    return out

def kr():
    sec = {}
    h = requests.get("https://finance.naver.com/sise/sise_group.naver?type=upjong", headers=UA, timeout=30).content.decode("euc-kr", "ignore")
    for no, nm in re.findall(r'sise_group_detail\.naver\?type=upjong&(?:amp;)?no=(\d+)">([^<]+)</a>', h):
        d = requests.get(f"https://finance.naver.com/sise/sise_group_detail.naver?type=upjong&no={no}", headers=UA, timeout=30).content.decode("euc-kr", "ignore")
        for c in set(re.findall(r"code=(\d{6})", d)): sec[c] = nm.strip()
    out = []
    for sosok in (0, 1):
        for p in range(1, 60):
            h = requests.get("https://finance.naver.com/sise/sise_market_sum.naver", params={"sosok": sosok, "page": p}, headers=UA, timeout=30).content.decode("euc-kr", "ignore")
            low = False
            for t in re.findall(r"<tr[^>]*>(.*?)</tr>", h, re.S):
                m = re.search(r'code=(\d{6})"[^>]*>([^<]+)</a>', t)
                if not m: continue
                cells = [re.sub(r"<[^>]+>|\s", "", c) for c in re.findall(r"<td[^>]*>(.*?)</td>", t, re.S)]
                if len(cells) < 7: continue
                cap_usd = float(cells[6].replace(",", "")) * 1e8 / FX
                if cap_usd < MIN_USD: low = True; continue
                out.append(["stock", f"KR_{m.group(1)}", m.group(2).strip().replace(",", " "), "KR", "KRX", m.group(1), sec.get(m.group(1), "기타"), round(cap_usd / 1e9, 2)])
            if low: break
    return out

if __name__ == "__main__":
    rows = []
    for fn in (us, kr):
        try: r = fn(); print(fn.__name__, len(r)); rows += r
        except Exception as e: print("실패", fn.__name__, e)
    if len(rows) < 100: print("종목 수 부족 -> 기존 stocks.csv 유지"); sys.exit(0)
    with open("stocks.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["kind", "id", "name", "market", "exch", "symbol", "sector", "mcap_b"]); w.writerows(rows)
    print("stocks.csv", len(rows))
