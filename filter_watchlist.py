import json, sys

date = sys.argv[1]
with open(f'scanner_results/{date}.json') as f:
    candidates = json.load(f)

profile_a = []
profile_b = []

for c in candidates:
    sym = c['symbol']
    profile = c.get('profile', 'X')
    gap = c['gap_pct']
    price = c['pm_price']
    flt = c.get('float_millions')

    if profile == 'X' or flt is None:
        continue

    if profile == 'A':
        if 0.5 <= flt <= 5.0 and 3.0 <= price <= 10.0 and 10.0 <= gap <= 40.0:
            profile_a.append(c)

    elif profile == 'B':
        if 5.0 <= flt <= 50.0 and 3.0 <= price <= 10.0 and 10.0 <= gap <= 25.0:
            profile_b.append(c)

profile_b.sort(key=lambda x: x['gap_pct'], reverse=True)
profile_b = profile_b[:2]

print(f"=== {date} Watchlist ===")
for c in profile_a:
    print(f"  {c['symbol']}:A gap={c['gap_pct']:+.1f}% float={c['float_millions']}M start={c['sim_start']}")
for c in profile_b:
    print(f"  {c['symbol']}:B gap={c['gap_pct']:+.1f}% float={c['float_millions']}M start={c['sim_start']}")
print(f"  Total: {len(profile_a)} A + {len(profile_b)} B = {len(profile_a)+len(profile_b)} stocks")
