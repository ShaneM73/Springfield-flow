"""Ad-hoc decomposition used in outputs/manuscript/ACS_LODES_WIDENING.md: LODES in-/out-commuting by distance band and ACS window, LODES vs ACS in-commuters by origin-county distance, composition of far in-commuters. Run from the repo root."""
import duckdb, pandas as pd, numpy as np, json, sys
con=duckdb.connect()
M=['springfield','columbia','jeffcity','joplin','stjoseph','capegirardeau','kansascity','stlouis']
W={'2006-2010':range(2006,2011),'2011-2015':range(2011,2016),'2016-2020':range(2016,2021)}
acs=pd.read_csv('outputs/external/acs_county_flows_raw.csv',dtype={'h_cty':str,'w_cty':str})
outA=[];outB=[];outC=[];outD=[]
for m in M:
    cty=set(json.load(open(f'outputs/{m}/counties.json')).keys()); cl="','".join(cty)
    q=f"""
    WITH p AS (SELECT year,jt,h_node,w_node,S000,SE03,SA01,SI01, dist_sum/dist_n AS mi,
         CASE WHEN length(h_node)=11 THEN substr(h_node,1,5) ELSE h_node END AS h_cty
         FROM 'outputs/{m}/panel.parquet' WHERE substr(w_node,1,5) IN ('{cl}') AND year BETWEEN 2006 AND 2020)
    SELECT year,jt, h_cty IN ('{cl}') AS internal,
      CASE WHEN mi<=30 THEN 'a<=30' WHEN mi<=60 THEN 'b30-60' WHEN mi<=100 THEN 'c60-100' ELSE 'd>100' END AS band,
      sum(S000) s, sum(SE03) se3, sum(SA01) sa1 FROM p GROUP BY 1,2,3,4"""
    d=con.sql(q).df()
    d['win']=d.year.apply(lambda y: next((k for k,v in W.items() if y in v),None)); d=d.dropna(subset=['win'])
    for jt in ['JT00','JT02']:
        x=d[d.jt==jt]; tot=x.groupby('win').s.sum()
        ext=x[~x.internal].groupby(['win','band']).s.sum().unstack().fillna(0)
        r=(ext.div(tot,axis=0)*100).round(2); r['all_ext']=r.sum(axis=1); r['metro']=m; r['jt']=jt; outA.append(r.reset_index())
        e=x[~x.internal].groupby(['win','band']).agg(s=('s','sum'),se3=('se3','sum'),sa1=('sa1','sum'))
        e['hi_share']=(e.se3/e.s).round(3); e['young_share']=(e.sa1/e.s).round(3); e['metro']=m; e['jt']=jt; outC.append(e.reset_index())
    # county-origin JT00 vs ACS in-commuters by origin distance
    q2=f"""
    WITH p AS (SELECT year,h_node,w_node,S000, dist_sum/dist_n AS mi,
         CASE WHEN length(h_node)=11 THEN substr(h_node,1,5) ELSE h_node END AS h_cty
         FROM 'outputs/{m}/panel.parquet' WHERE jt='JT00' AND substr(w_node,1,5) IN ('{cl}') AND year BETWEEN 2006 AND 2020)
    SELECT year,h_cty, sum(S000) s, sum(S000*mi)/sum(S000) mi FROM p WHERE h_cty NOT IN ('{cl}') GROUP BY 1,2"""
    l=con.sql(q2).df(); l['win']=l.year.apply(lambda y: next((k for k,v in W.items() if y in v),None))
    lw=l.groupby(['win','h_cty']).agg(lodes=('s','mean'),mi=('mi','mean')).reset_index()
    a=acs[acs.w_cty.isin(cty)&~acs.h_cty.isin(cty)].groupby(['period','h_cty']).workers.sum().reset_index().rename(columns={'period':'win','workers':'acs'})
    j=lw.merge(a,on=['win','h_cty'],how='outer').fillna({'lodes':0,'acs':0})
    j['mi']=j.groupby('h_cty').mi.transform('mean')
    j['dbin']=pd.cut(j.mi,[0,40,80,150,1e5],labels=['<40','40-80','80-150','>150'])
    g=j.groupby(['win','dbin'],observed=True)[['lodes','acs']].sum().round(0); g['ratio']=(g.lodes/g.acs.replace(0,np.nan)).round(2); g['metro']=m; outB.append(g.reset_index())
    # out-commuters: residents working outside metro, LODES JT00 (all parts incl. oos) vs ACS
    q3=f"""SELECT year, sum(S000) s FROM 'outputs/{m}/panel.parquet' WHERE jt='JT00' AND length(h_node)=11 AND substr(h_node,1,5) IN ('{cl}') AND substr(w_node,1,5) NOT IN ('{cl}') AND year BETWEEN 2006 AND 2020 GROUP BY 1"""
    q4=f"""SELECT year, sum(S000) s FROM 'outputs/{m}/panel.parquet' WHERE jt='JT00' AND length(h_node)=11 AND substr(h_node,1,5) IN ('{cl}') AND year BETWEEN 2006 AND 2020 GROUP BY 1"""
    o=con.sql(q3).df().set_index('year').s; rr=con.sql(q4).df().set_index('year').s
    for k,v in W.items():
        yrs=[y for y in v if y in o.index]
        ao=acs[acs.h_cty.isin(cty)&~acs.w_cty.isin(cty)&(acs.period==k)].workers.sum(); ar=acs[acs.h_cty.isin(cty)&(acs.period==k)].workers.sum()
        outD.append(dict(metro=m,win=k,lodes_out_share=round(o[yrs].sum()/rr[yrs].sum(),3),acs_out_share=round(ao/ar,3)))
A=pd.concat(outA); B=pd.concat(outB); C=pd.concat(outC); D=pd.DataFrame(outD)
A.to_csv('outputs/external/lodes_incommute_bands_windows.csv',index=False); B.to_csv('outputs/external/lodes_vs_acs_origin_distance.csv',index=False); C.to_csv('outputs/external/lodes_incommute_composition.csv',index=False); D.to_csv('outputs/external/lodes_vs_acs_outcommute.csv',index=False)
pd.set_option('display.width',250)
print("A: external in-commuters as % of metro jobs by distance band (JT00), window averages")
print(A[A.jt=='JT00'].pivot_table(index='metro',columns='win',values=['a<=30','b30-60','c60-100','d>100','all_ext']).round(2).to_string())
print("\nB: in-commuters by origin-county distance bin, LODES JT00 vs ACS")
print(B.pivot_table(index=['metro','dbin'],columns='win',values=['lodes','acs','ratio'],observed=True).to_string())
print("\nC: high-earner (SE03) share of external in-commuters by band, JT02")
print(C[C.jt=='JT02'].pivot_table(index=['metro','band'],columns='win',values='hi_share').round(3).to_string())
print("\nD: out-commuter share of resident workers, LODES vs ACS")
print(D.pivot_table(index='metro',columns='win',values=['lodes_out_share','acs_out_share']).to_string())
