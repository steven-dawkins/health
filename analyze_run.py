import sys, numpy as np, pandas as pd, xml.etree.ElementTree as ET
gpx, data = sys.argv[1], sys.argv[2]
ns = {"g": "http://www.topografix.com/GPX/1/1"}
pts = []
for p in ET.parse(gpx).getroot().iterfind(".//g:trkpt", ns):
    t = pd.Timestamp(p.find("g:time", ns).text).tz_localize(None)
    pts.append((t, float(p.get("lat")), float(p.get("lon")), float(p.find("g:ele", ns).text)))
df = pd.DataFrame(pts, columns=["t", "lat", "lon", "ele"])
la, lo = np.radians(df.lat.values), np.radians(df.lon.values)
d = 2*6371000*np.arcsin(np.sqrt(np.sin(np.diff(la)/2)**2 + np.cos(la[:-1])*np.cos(la[1:])*np.sin(np.diff(lo)/2)**2))
dt = df.t.diff().dt.total_seconds().values[1:]
# drop pauses / GPS jumps
ok = (dt > 0) & (dt < 10) & (d/dt < 8)
df["dist"] = np.concatenate([[0], np.cumsum(np.where(ok, d, 0))])
df["sec"] = (df.t - df.t.iloc[0]).dt.total_seconds()
df["ele_s"] = df.ele.rolling(15, center=True, min_periods=1).mean()
total = df.dist.iloc[-1]
print(f"GPS distance {total/1000:.2f} km, elapsed {df.sec.iloc[-1]/60:.1f} min ({int(df.sec.iloc[-1]//3600)}:{int(df.sec.iloc[-1]%3600//60):02d}:{int(df.sec.iloc[-1]%60):02d})\n")

def load(n):
    x = pd.read_csv(f"{data}/{n}.csv", usecols=["startDate","endDate","value"])
    x["startDate"] = pd.to_datetime(x.startDate.str[:19]); x["endDate"] = pd.to_datetime(x.endDate.str[:19])
    x["mid"] = x.startDate + (x.endDate - x.startDate)/2
    return x[(x.mid >= df.t.iloc[0]) & (x.mid <= df.t.iloc[-1])]
hr = load("heart_rate"); met = {k: load(n) for k, n in [("power","running_power"),("stride","running_stride_length"),("vosc","running_vertical_oscillation"),("gct","running_ground_contact_time")]}

def agg(lo_t, hi_t, frame):
    s = frame[(frame.mid >= lo_t) & (frame.mid < hi_t)].value
    return s.mean() if len(s) else np.nan
def seg(d0, d1):
    a = df[(df.dist >= d0) & (df.dist <= d1)]
    if len(a) < 2: return None
    t0, t1 = a.t.iloc[0], a.t.iloc[-1]
    dist = a.dist.iloc[-1]-a.dist.iloc[0]; sec = (t1-t0).total_seconds()
    e = a.ele_s.diff().dropna()
    r = dict(dist=dist, sec=sec, pace=sec/(dist/1000), up=e[e>0].sum(), down=-e[e<0].sum(),
             hr=agg(t0,t1,hr), **{k: agg(t0,t1,v) for k,v in met.items()})
    # cadence proxy: speed / stride
    r["cad"] = (dist/sec)/r["stride"]*60 if r["stride"] == r["stride"] and r["stride"] > 0 else np.nan
    return r
def pf(p): return f"{int(p//60)}:{int(p%60):02d}"
def row(label, r):
    return f"{label:<10}{pf(r['pace']):>7}{r['hr']:>6.0f}{r['power']:>6.0f}{r['stride']:>7.2f}{r['cad']:>6.0f}{r['gct']:>6.0f}{r['vosc']:>6.1f}{r['up']:>5.0f}{r['down']:>5.0f}"
hdr = f"{'':<10}{'pace':>7}{'HR':>6}{'W':>6}{'stride':>7}{'spm':>6}{'GCT':>6}{'VO':>6}{'up':>5}{'dn':>5}"
print("PER KM\n"+hdr)
rows=[]
k=0
while k*1000 < total:
    r = seg(k*1000, min((k+1)*1000, total))
    if r and r["dist"] > 300:
        lab = f"km {k+1}" if r["dist"] > 990 else f"last {r['dist']:.0f}m"
        print(row(lab, r)); rows.append((k+1, r))
    k += 1
print("\nPER 5 KM\n"+hdr)
for k in range(0, int(total//5000)+1):
    r = seg(k*5000, min((k+1)*5000, total))
    if r and r["dist"] > 500: print(row(f"{k*5}-{min((k+1)*5, total/1000):.1f}", r))
h1, h2 = seg(0, 21097), seg(21097, total)
print(f"\nHalves: 1st {pf(h1['pace'])}/km HR {h1['hr']:.0f}  |  2nd {pf(h2['pace'])}/km HR {h2['hr']:.0f}  (diff {h2['pace']-h1['pace']:+.0f}s/km)")
# find collapse: first km where pace is >10s slower than the 5-30km median and stays so
base = np.median([r['pace'] for k, r in rows if 5 <= k <= 30])
print(f"Median pace km5-30: {pf(base)}")
for k, r in rows:
    if k > 30 and r['pace'] > base + 10:
        print(f"First km after 30 >10s/km slower than median: km {k}"); break
# stops / walking: seconds below 2.0 m/s per km, using 1s speed
sp = np.gradient(df.dist.values, df.sec.values)
df["spd"] = pd.Series(sp).rolling(5, center=True, min_periods=1).mean()
print("\nSLOW SECONDS (<2.2 m/s i.e. slower than 7:35/km) per km, km 30+")
for k in range(30, int(total//1000)+1):
    a = df[(df.dist >= k*1000) & (df.dist < (k+1)*1000)]
    if len(a): print(f"  km {k+1}: {int((a.spd < 2.2).sum())}s")
