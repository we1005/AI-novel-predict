# 受控实验:数字设定值 vs 自然语言档位,谁更能控制可测风格量
import json, re, time, urllib.request, urllib.error, statistics as st
import os
_ROOT=os.path.abspath(os.path.join(os.path.dirname(__file__),"..","..",".."))
cfg=json.load(open(os.path.join(_ROOT,"backend","data","settings.json")))  # key 从 gitignore 的 settings.json 读
x=cfg["providers"]["xiaomi"]; KEY=x["api_key"]; BASE=x["base_url"].rstrip("/")
H={"Authorization":f"Bearer {KEY}","Content-Type":"application/json"}
MODEL="mimo-v2.5"
HEDGE=re.compile(r"似乎|仿佛|如同|宛如|好像|大概|也许|约莫")
LEXSET=["蠕动","黏腻","腥臭","低语","阴影","触须","痉挛","腐烂","潮湿","裂缝"]
TOPIC="写一段约500字的中文小说场景:一个人深夜独自在老公寓里等一通迟迟不来的电话。只写正文,不要标题、不要解释、不要分点。"

def gen(extra, seed, tries=4):
    sys_="你是一位中文小说写手。"+extra
    body={"model":MODEL,"messages":[{"role":"system","content":sys_},
          {"role":"user","content":TOPIC+f"(变体{seed})"}],
          "max_completion_tokens":900,"temperature":0.9,"top_p":0.95}
    for k in range(tries):
        try:
            req=urllib.request.Request(BASE+"/chat/completions",data=json.dumps(body).encode(),headers=H,method="POST")
            d=json.loads(urllib.request.urlopen(req,timeout=120).read())
            return d["choices"][0]["message"]["content"] or ""
        except urllib.error.HTTPError as e:
            if e.code==429: time.sleep(3*(k+1)); continue
            time.sleep(2)
        except Exception: time.sleep(2)
    return ""

def hedge_k(t): return round(len(HEDGE.findall(t))/max(1,len(t))*1000,2)
def lex_k(t):   return round(sum(t.count(w) for w in LEXSET)/max(1,len(t))*1000,2)

WORDS="“似乎、仿佛、宛如、好像、大概、也许”这类表示不确定/推测的弱断言词"
def hedge_numeric(n):   return f"风格要求:让{WORDS}的出现密度约为每千字 {n} 处(本段约500字,即约 {round(n/2)} 处)。其余照常写。"
def hedge_qual(level):  return {"low":f"风格要求:语气笃定,几乎不用{WORDS}。",
                                "mid":f"风格要求:偶尔使用{WORDS},营造一点不确定感。",
                                "high":f"风格要求:频繁使用{WORDS},让叙述充满迟疑与不确定感。"}[level]
LW="、".join(LEXSET)
def lex_numeric(n):     return f"风格要求:有意识地使用这些“潮湿腐坏/不安感”词汇:{LW};让它们的总出现密度约为每千字 {n} 处(本段约500字,即约 {round(n/2)} 处)。"
def lex_qual(level):    return {"low":f"风格要求:画面干净克制,几乎不用“潮湿腐坏/不安感”的词({LW}等)。",
                                "mid":f"风格要求:适度点缀一些“潮湿腐坏/不安感”的词({LW}等)。",
                                "high":f"风格要求:大量铺陈“潮湿腐坏/不安感”的词({LW}等),让环境密集渗出阴湿腐坏的气息。"}[level]

LEVELS=["low","mid","high"]
HEDGE_T={"low":1,"mid":5,"high":10}; LEX_T={"low":2,"mid":8,"high":16}
SAMPLES=3
rows=[]

# 基线(无风格指令)
print("== 基线 ==")
base_h=[]; base_l=[]
for s in range(SAMPLES):
    t=gen("",f"b{s}"); base_h.append(hedge_k(t)); base_l.append(lex_k(t))
    print(f"  baseline s{s}: len={len(t)} hedge={hedge_k(t)} lex={lex_k(t)}")

def run(axis, meas, numf, qualf, T):
    print(f"\n== 轴:{axis} ==")
    for cond,fn in [("numeric",numf),("qual",qualf)]:
        for lv in LEVELS:
            vals=[]
            for s in range(SAMPLES):
                t=gen(fn(T[lv] if cond=="numeric" else lv), f"{cond}{lv}{s}")
                v=meas(t); vals.append(v)
                rows.append({"axis":axis,"cond":cond,"level":lv,"target":T[lv],"val":v,"len":len(t)})
                time.sleep(0.3)
            m=round(st.mean(vals),2); sd=round(st.pstdev(vals),2)
            tgt=T[lv]
            mae=round(abs(m-tgt),2)
            print(f"  {cond:7s} {lv:4s} 目标≈{tgt:<3} 实测均值={m:<6} 标准差={sd:<5} |均值-目标|={mae}")
    return

run("hedge", hedge_k, hedge_numeric, hedge_qual, HEDGE_T)
run("lex",   lex_k,   lex_numeric,   lex_qual,   LEX_T)

out={"model":MODEL,"baseline":{"hedge":base_h,"lex":base_l},"rows":rows,
     "hedge_targets":HEDGE_T,"lex_targets":LEX_T}
json.dump(out,open("/tmp/numexp_results.json","w"),ensure_ascii=False,indent=2)
print("\n结果落 /tmp/numexp_results.json")
