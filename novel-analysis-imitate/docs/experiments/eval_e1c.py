# E1c:消除长度混淆(参考=单章特征均值,单位统一为单章),给独立尺子公平机会
import sqlite3, re, os, math, statistics as st, random
random.seed(7)
import os as _os
ROOT=_os.path.abspath(_os.path.join(_os.path.dirname(__file__),"..","..","..","backend","data","books"))
POS="余烬之铳"; NEGS=["末法王座","天之炽-江南","《九州·缥缈录》-江南"]
HEDGE=re.compile(r"似乎|仿佛|如同|宛如|好像|大概|也许|约莫"); REDUP=re.compile(r"([一-龥])\1")
def bodies(slug,k):
    rows=sqlite3.connect(os.path.join(ROOT,slug,"novel.db")).execute(
        "SELECT body FROM chapter_fts WHERE length(body)>1200 ORDER BY chapter").fetchall()
    rows=[r[0] for r in rows if r[0]]; random.shuffle(rows); return rows[:k]
def feats(t):
    n=max(1,len(t)); kk=n/1000
    sents=[s for s in re.split(r"[。!?…]",t) if s.strip()]; slen=[len(s) for s in sents] or [0]
    paras=[p for p in t.split("\n") if p.strip()]; plen=[len(p) for p in paras] or [0]
    dia=sum(len(m) for m in re.findall(r"“[^”]*”",t)); ms=st.mean(slen)
    return {"avg_sent_len":ms,"sent_cv":(st.pstdev(slen)/ms if ms else 0),"para_len":st.mean(plen),
            "dialogue_ratio":dia/n,"comma_k":(t.count(",")+t.count("、"))/kk,
            "hedge_k":len(HEDGE.findall(t))/kk,"redup_k":len(REDUP.findall(t))/kk}
KEYS_INDEP=["avg_sent_len","sent_cv","para_len","dialogue_ratio","comma_k"]
KEYS_REGEX=["hedge_k","redup_k"]
KEYS_2=["avg_sent_len","dialogue_ratio"]
refch=[feats(t) for t in bodies(POS,18)]
ref={k:st.mean(f[k] for f in refch) for k in (KEYS_INDEP+KEYS_REGEX)}   # 参考=单章特征均值
pos=[feats(t) for t in bodies(POS,14)]
neg=[feats(t) for s in NEGS for t in bodies(s,6)]
pool=pos+neg
def auc(keys):
    zs={k:(st.mean(f[k] for f in pool),st.pstdev(f[k] for f in pool) or 1) for k in keys}
    z=lambda f:[(f[k]-zs[k][0])/zs[k][1] for k in keys]
    zr=[(ref[k]-zs[k][0])/zs[k][1] for k in keys]
    d=lambda f:math.dist(z(f),zr)
    dp=[d(f) for f in pos]; dn=[d(f) for f in neg]
    return sum(1 for p in dp for q in dn if p<q)/(len(dp)*len(dn))
print(f"R_regex(hedge/redup)            AUC = {round(auc(KEYS_REGEX),3)}")
print(f"R_indep(句长/cv/段长/对白比/逗号) AUC = {round(auc(KEYS_INDEP),3)}")
print(f"R_2feat(仅 句长+对白比)          AUC = {round(auc(KEYS_2),3)}")
print(f"R_all(独立+正则 全 7 维)         AUC = {round(auc(KEYS_INDEP+KEYS_REGEX),3)}")
