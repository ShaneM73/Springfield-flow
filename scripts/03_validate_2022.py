"""Phase 1c: reproduce the handoff's 2022 JT00 cross-section numbers from the panel.

Usage: python scripts/03_validate_2022.py      -> outputs/springfield/validation_2022.csv
"""
import duckdb
import pandas as pd

from config import OUT, metro_def

M = metro_def("springfield")
od = OUT / "springfield"
cty = ",".join(f"'{c}'" for c in M["counties"])
con = duckdb.connect()
con.execute(f"""CREATE VIEW b AS SELECT *, substr(h_geocode,1,5) hc, substr(w_geocode,1,5) wc,
               substr(h_geocode,1,5) IN ({cty}) h_in, substr(w_geocode,1,5) IN ({cty}) w_in
               FROM '{od/'blockflows.parquet'}' WHERE year=2022 AND jt='JT00' AND part='main'""")
con.execute(f"""CREATE VIEW p AS SELECT *, substr(h_node,1,5) IN ({cty}) h_in, substr(w_node,1,5) IN ({cty}) w_in
               FROM '{od/'panel.parquet'}' WHERE year=2022 AND jt='JT00' AND part='main'""")
q = lambda s: con.execute(s).fetchone()[0]

expected, got = {}, {}
def chk(k, exp, val): expected[k] = exp; got[k] = val

chk("Jobs in MSA (MO residents, main)", 212808, q("SELECT sum(S000) FROM b WHERE w_in"))
chk("Live and work in MSA", 158912, q("SELECT sum(S000) FROM b WHERE w_in AND h_in"))
chk("Commute in from outside MSA (MO)", 53896, q("SELECT sum(S000) FROM b WHERE w_in AND NOT h_in"))
chk("Live in MSA, work outside (MO)", 36901, q("SELECT sum(S000) FROM b WHERE h_in AND NOT w_in"))
chk("MSA tracts", 117, q(f"SELECT count(DISTINCT trct) FROM '{od.parent.parent/'parquet/mo/mo_xwalk.parquet'}' WHERE cty IN ({cty})"))
# handoff definition = all directed cross-node flows touching the MSA (outside counties as single nodes)
chk("Cross-node commuters in pairs >=10 (%)", 77.5, round(100 * q(
    "SELECT sum(CASE WHEN S000>=10 THEN S000 ELSE 0 END)/sum(S000) FROM p WHERE (h_in OR w_in) AND h_node<>w_node"), 1))
expected["(info) within-MSA cross-tract in pairs >=10 (%)"] = "-"
got["(info) within-MSA cross-tract in pairs >=10 (%)"] = round(100 * q(
    "SELECT sum(CASE WHEN S000>=10 THEN S000 ELSE 0 END)/sum(S000) FROM p WHERE h_in AND w_in AND h_node<>w_node"), 1)

cnty = {"Greene": (122620, 173676, 1.42, 78), "Christian": (39101, 19382, 0.50, 21),
        "Webster": (14359, 7912, 0.55, 24), "Polk": (13201, 9493, 0.72, 36), "Dallas": (6532, 2345, 0.36, 15)}
for fips, name in M["counties"].items():
    rw = q(f"SELECT sum(S000) FROM b WHERE hc='{fips}'")
    jobs = q(f"SELECT sum(S000) FROM b WHERE wc='{fips}'")
    own = q(f"SELECT sum(S000) FROM b WHERE hc='{fips}' AND wc='{fips}'")
    e = cnty[name]
    chk(f"{name} resident workers", e[0], rw); chk(f"{name} jobs", e[1], jobs)
    chk(f"{name} jobs/resident worker", e[2], round(jobs / rw, 2)); chk(f"{name} work in own county %", e[3], round(100 * own / rw))


def wmedian(sql_weight, where):
    d = con.execute(f"SELECT miles, {sql_weight} w FROM b WHERE h_in AND w_in AND {where}").df()
    d = d[d.w > 0].sort_values("miles")
    c = d.w.cumsum()
    return round(float(d.miles[c >= d.w.sum() / 2].iloc[0]), 1)


for fips, name, e in [("29077", "Greene", 5.0), ("29043", "Christian", 10.4), ("29167", "Polk", 15.2),
                      ("29225", "Webster", 17.2), ("29059", "Dallas", 23.5)]:
    chk(f"Median miles, home {name}", e, wmedian("S000", f"hc='{fips}'"))
for col, lab, e in [("SE01", "<=$1,250", 5.7), ("SE02", "$1,251-3,333", 6.0), ("SE03", ">$3,333", 7.2),
                    ("SI01", "goods", 8.5), ("SI02", "trade/transp/util", 7.1), ("SI03", "other services", 5.9)]:
    chk(f"Median miles, {lab}", e, wmedian(col, "true"))
chk("Christian -> Greene", 22062, q("SELECT sum(S000) FROM b WHERE hc='29043' AND wc='29077'"))
tj = con.execute("SELECT w_node, sum(S000) j FROM p WHERE w_in GROUP BY 1 ORDER BY j DESC").df()
chk("Top-5 tract share of MSA jobs (%)", 27, round(100 * tj.j.head(5).sum() / tj.j.sum()))
chk("Largest tract", "29077002200", tj.w_node.iloc[0])
chk("Largest tract jobs (~)", 18000, int(tj.j.iloc[0]))
src = con.execute("SELECT h_node FROM p WHERE w_in AND NOT h_in GROUP BY 1 ORDER BY sum(S000) DESC LIMIT 4").df()
chk("Top outside sources", "29109,29213,29209,29097", ",".join(src.h_node))

res = pd.DataFrame({"measure": list(expected), "handoff": list(expected.values()), "pipeline": list(got.values())})
res["match"] = [a == "-" or str(a) == str(b) or (isinstance(a, (int, float)) and abs(float(b) - a) <= max(0.051, 0.05 * abs(a) * ("~" in m)))
                for m, a, b in zip(res.measure, res.handoff, res.pipeline)]
res.to_csv(od / "validation_2022.csv", index=False)
pd.set_option("display.width", 200)
print(res.to_string(index=False))
print(f"\n{res.match.sum()}/{len(res)} match")
