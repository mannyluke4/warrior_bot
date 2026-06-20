"""Full-YTD stock-filter verification (2026-06-20).
Question: does the low-float -> clean-tradeable-day edge hold across ALL 116 cached
days (Jan 2 - Jun 19), or was it a May/Jun artifact?

Method: for every cached date, take the FULL scanner universe (all symbols with a
tick_cache file that day = junk included), pull ohlcv-1d (+20d lookback for rvol),
label each stock-DAY GOOD = (range>=25% AND closed in top 40% of range) = trended
and held. Then P(GOOD | stock filter) vs base. ohlcv-1d only -> cheap. Pre-6/17 free.
Run: ./venv/bin/python stock_filter_ytd.py
"""
import os, glob, json
from dotenv import load_dotenv
load_dotenv("/Users/duffy/warrior_bot_v2/.env", override=True)
import databento as db
from statistics import median
from float_cache import load_float_cache

c=db.Historical(os.getenv("DATABENTO_API_KEY") or os.getenv("DB_API_KEY"))
fc=load_float_cache()
LEV={"SOXS","SOXL","TQQQ","SQQQ","MSTU","MSTZ","TSLL","TSLZ","NVDL","NVDU","SPXU","SPXL","UVXY","VXX",
     "SVXY","TNA","TZA","LABU","LABD","FNGU","FNGD","BITX","BITU","ETHU","CONL","SOXX","UVIX","BITO","UVXY"}
import re
DATES=sorted(n for d in glob.glob("tick_cache/2026-*") if os.path.isdir(d)
             for n in [d.split("/")[-1]] if re.fullmatch(r"\d{4}-\d{2}-\d{2}", n))
rows=[]; skipped=[]
for date in DATES:
    ss=sorted({os.path.basename(p).split(".")[0] for p in glob.glob(f"tick_cache/{date}/*.json.gz")
               if ".tmp" not in p and os.path.basename(p).split(".")[0] not in LEV})
    if not ss: continue
    y,m,d=map(int,date.split("-")); nd=date[:8]+f"{d+1:02d}"
    start=f"{y}-{m:02d}-01"  # generous lookback; trim in code
    try:
        df=c.timeseries.get_range(dataset="DBEQ.BASIC",schema="ohlcv-1d",symbols=ss,
                                  stype_in="raw_symbol",start=start,end=nd).to_df()
    except Exception as e:
        skipped.append((date,repr(e)[:50])); continue
    if df.empty: continue
    for sym,g in df.groupby("symbol"):
        g=g.sort_values("ts_event")
        if len(g)<2: continue
        day=g.iloc[-1]; prev=g.iloc[-2]
        o,h,l,cl,v=float(day.open),float(day.high),float(day.low),float(day.close),float(day.volume)
        if l<=0 or o<=0 or v<100000: continue
        hist=[float(x) for x in g.volume.iloc[-21:-1]]
        avgv=median(hist) if len(hist)>=3 else v
        fl=fc.get(sym)
        rng=(h-l)/l*100; cpos=(cl-l)/(h-l) if h>l else 0
        gap=(o-float(prev.close))/float(prev.close)*100 if prev.close else 0
        good=(rng>=25 and cpos>=0.6)
        rows.append(dict(sym=sym,date=date,good=good,float_m=fl/1e6 if fl else None,
                         gap=gap,rng=rng,cpos=round(cpos,2),dvol=cl*v/1e6,
                         rvol=v/avgv if avgv else None,price=o))
json.dump(rows,open("/tmp/stock_filter_ytd.json","w"))
nG=sum(r['good'] for r in rows); base=nG/len(rows) if rows else 0
print(f"\n=== FULL YTD: {len(DATES)} dates, {len(rows)} stock-days, {nG} GOOD ({base*100:.0f}%) ===")
if skipped: print(f"  skipped {len(skipped)} dates (likely 6/17+ license): {[s[0] for s in skipped]}")
G=[r for r in rows if r['good']]; B=[r for r in rows if not r['good']]
def med(rs,k): vs=[r[k] for r in rs if r.get(k) is not None]; return round(median(vs),1) if vs else None
print(f"\n{'feature':10} {'GOOD':>8} {'rest':>8}")
for k in ('float_m','gap','dvol','rvol','price'): print(f"  {k:8} {str(med(G,k)):>8} {str(med(B,k)):>8}")
print(f"\n=== P(GOOD | filter) vs base {base*100:.0f}% ===")
def pr(cond,lab):
    s=[r for r in rows if cond(r)]
    if len(s)<25: return
    g=sum(r['good'] for r in s); p=g/len(s)
    mult=p/base if base else 0
    fl="  <<<" if mult>=1.4 else ("  (weak)" if mult>=1.15 else "")
    print(f"  {lab:24} n={len(s):>4}  P={p*100:>2.0f}%  {mult:.1f}x{fl}")
pr(lambda r:r['float_m'] and r['float_m']<10,"float<10M")
pr(lambda r:r['float_m'] and r['float_m']<5,"float<5M")
pr(lambda r:r['float_m'] and r['float_m']<3,"float<3M")
pr(lambda r:r['float_m'] and 10<=r['float_m']<50,"float 10-50M")
pr(lambda r:r['float_m'] and r['float_m']>=50,"float>=50M")
pr(lambda r:r['price']<3,"price<$3")
pr(lambda r:3<=r['price']<10,"price $3-10")
pr(lambda r:r['price']>=10,"price>=$10")
pr(lambda r:r['rvol'] and r['rvol']>=5,"RVOL>=5x")
pr(lambda r:r['rvol'] and r['rvol']>=10,"RVOL>=10x")
pr(lambda r:r['float_m'] and r['float_m']<10 and r['price']<5,"float<10M AND price<$5")
# month-by-month stability of the float<10M edge
print("\n=== float<10M edge stability by month ===")
for mo in ("2026-01","2026-02","2026-03","2026-04","2026-05","2026-06"):
    mr=[r for r in rows if r['date'].startswith(mo)]
    if not mr: continue
    b=sum(r['good'] for r in mr)/len(mr)
    lf=[r for r in mr if r['float_m'] and r['float_m']<10]
    if len(lf)<10: print(f"  {mo}: base {b*100:.0f}%  float<10M n={len(lf)} (thin)"); continue
    p=sum(r['good'] for r in lf)/len(lf)
    print(f"  {mo}: base {b*100:>2.0f}%  float<10M {p*100:>2.0f}%  ({p/b if b else 0:.1f}x)  n={len(lf)}")
