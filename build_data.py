"""매일 실행: KIS API(또는 MOCK=1 가짜데이터)로 일봉 수집 -> 주봉 변환 -> Stage 판별 -> site/ 에 JSON 생성"""
import os, json, csv, time, random, datetime as dt
import pandas as pd, requests

BASE = "https://openapi.koreainvestment.com:9443"
MOCK = os.environ.get("MOCK") == "1"
OUT = "site"; os.makedirs(f"{OUT}/d", exist_ok=True)
END = dt.date.today()
START = END - dt.timedelta(days=1000)

# ---------- KIS ----------
class KIS:
    def __init__(self):
        self.key, self.sec = os.environ["KIS_APP_KEY"], os.environ["KIS_APP_SECRET"]
        r = requests.post(f"{BASE}/oauth2/tokenP", json={"grant_type": "client_credentials", "appkey": self.key, "appsecret": self.sec}, timeout=20)
        r.raise_for_status(); self.tok = r.json()["access_token"]
    def get(self, path, tr, params):
        h = {"authorization": f"Bearer {self.tok}", "appkey": self.key, "appsecret": self.sec, "tr_id": tr, "custtype": "P"}
        for _ in range(3):
            time.sleep(0.08)
            r = requests.get(BASE + path, headers=h, params=params, timeout=20)
            if r.status_code == 200 and r.json().get("rt_cd") == "0": return r.json()
            time.sleep(1)
        raise RuntimeError(f"KIS 실패 {path} {params} {r.text[:200]}")

def f(d): return d.strftime("%Y%m%d")
def rows_to_df(rows, m):
    df = pd.DataFrame([{"date": pd.to_datetime(r[m[0]]), "open": float(r[m[1]]), "high": float(r[m[2]]), "low": float(r[m[3]]), "close": float(r[m[4]]), "volume": float(r[m[5]] or 0)} for r in rows if r.get(m[0])])
    return df

def fetch_kis(k, it):
    frames, end = [], END
    while end > START:
        beg = max(START, end - dt.timedelta(days=140))
        if it["exch"] == "KRX":
            j = k.get("/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice", "FHKST03010100",
                {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": it["symbol"], "FID_INPUT_DATE_1": f(beg), "FID_INPUT_DATE_2": f(end), "FID_PERIOD_DIV_CODE": "D", "FID_ORG_ADJ_PRC": "0"})
            df = rows_to_df(j["output2"], ["stck_bsop_date", "stck_oprc", "stck_hgpr", "stck_lwpr", "stck_clpr", "acml_vol"])
        elif it["exch"] == "KRIDX":
            j = k.get("/uapi/domestic-stock/v1/quotations/inquire-daily-indexchartprice", "FHKUP03500100",
                {"FID_COND_MRKT_DIV_CODE": "U", "FID_INPUT_ISCD": it["symbol"], "FID_INPUT_DATE_1": f(beg), "FID_INPUT_DATE_2": f(end), "FID_PERIOD_DIV_CODE": "D"})
            df = rows_to_df(j["output2"], ["stck_bsop_date", "bstp_nmix_oprc", "bstp_nmix_hgpr", "bstp_nmix_lwpr", "bstp_nmix_prpr", "acml_vol"])
        else:
            j = k.get("/uapi/overseas-price/v1/quotations/dailyprice", "HHDFS76240000",
                {"AUTH": "", "EXCD": it["exch"], "SYMB": it["symbol"], "GUBN": "0", "BYMD": f(end), "MODP": "1"})
            df = rows_to_df(j["output2"], ["xymd", "open", "high", "low", "clos", "tvol"])
        if df.empty: break
        frames.append(df); nxt = df.date.min().date() - dt.timedelta(days=1)
        if nxt >= end: break
        end = nxt
    if not frames: raise RuntimeError("데이터 없음")
    return pd.concat(frames).drop_duplicates("date").sort_values("date").reset_index(drop=True)

def mock(it):
    rnd = random.Random(it["id"]); n = 650; p = 100.0; out = []
    drift = rnd.choice([-0.0006, 0, 0.0004, 0.0009]); d = START
    for _ in range(n):
        while d.weekday() >= 5: d += dt.timedelta(days=1)
        o = p; p *= 1 + drift * (1 if _ > 250 else -0.5) + rnd.gauss(0, 0.014)
        out.append({"date": pd.Timestamp(d), "open": o, "high": max(o, p) * 1.005, "low": min(o, p) * 0.995, "close": p, "volume": rnd.uniform(1e6, 3e6)}); d += dt.timedelta(days=1)
    return pd.DataFrame(out)

# ---------- Stage 판별 ----------
def weekly(df):
    w = df.set_index("date").resample("W-FRI").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
    return w

def classify(w, bench=None):
    if len(w) < 60: return None
    c = w.close; ma = c.rolling(30).mean()
    slope = ma.iloc[-1] / ma.iloc[-6] - 1
    ext = c.iloc[-1] / ma.iloc[-1] - 1
    above = (c > ma).tolist(); wks = 0
    for v in reversed(above):
        if v: wks += 1
        else: break
    rs_ok = None
    if bench is not None:
        ratio = (c / bench.close.reindex(c.index, method="ffill")).dropna()
        if len(ratio) > 35: rs_ok = bool(ratio.iloc[-1] > ratio.rolling(30).mean().iloc[-1])
    vr = w.volume.iloc[-4:].mean() / max(w.volume.iloc[-30:-4].mean(), 1)
    if above[-1] and slope > 0.005: st = 2
    elif (not above[-1]) and slope < -0.005: st = 4
    else: st = 3 if ma.iloc[-1] >= ma.iloc[-27] else 1
    early = bool(st == 2 and wks <= 12 and ext <= 0.15 and rs_ok is not False)
    return {"stage": st, "early": early, "wks": wks, "ext": round(ext * 100, 1), "slope": round(slope * 100, 2), "rs": rs_ok, "vr": round(vr, 2), "close": round(float(c.iloc[-1]), 2)}

def candles(df, n):
    d = df.tail(n)
    return [{"time": r.date.strftime("%Y-%m-%d"), "open": round(r.open, 4), "high": round(r.high, 4), "low": round(r.low, 4), "close": round(r.close, 4), "volume": r.volume} for r in d.itertuples()]

def main():
    items = list(csv.DictReader(open("universe.csv", encoding="utf-8")))
    k = None if MOCK else KIS()
    data, errors = {}, []
    for it in items:
        try:
            if it["kind"] == "stock" and it["mcap_b"] and float(it["mcap_b"]) < 1: continue
            data[it["id"]] = mock(it) if MOCK else fetch_kis(k, it)
        except Exception as e: errors.append(f'{it["id"]}: {e}')
    bench = {it["market"]: weekly(data[it["id"]]) for it in items if it["kind"] == "index" and it["id"] in data}
    res = []
    for it in items:
        if it["id"] not in data: continue
        df = data[it["id"]]; w = weekly(df)
        r = classify(w, None if it["kind"] == "commodity" or it["kind"] == "index" else bench.get(it["market"]))
        if not r: continue
        res.append({"id": it["id"], "name": it["name"], "kind": it["kind"], "market": it["market"], "sector": it["sector"], **r})
        json.dump({"d": candles(df, 260), "w": candles(w.reset_index(), 150)}, open(f'{OUT}/d/{it["id"]}.json', "w"))
    json.dump({"updated": dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime("%Y-%m-%d %H:%M KST"), "mock": MOCK, "items": res, "errors": errors}, open(f"{OUT}/data.json", "w"), ensure_ascii=False)
    print(f"완료: {len(res)}개, 오류 {len(errors)}개")
    for e in errors: print(" -", e)

if __name__ == "__main__": main()
