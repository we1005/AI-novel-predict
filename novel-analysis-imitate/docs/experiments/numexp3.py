# 第三轮(确认):弱断言开环控制,数字设定 vs 尽力校准的自然语言(steelman),6 样本
import json, re, time, urllib.request, urllib.error, statistics as st
import os
_ROOT=os.path.abspath(os.path.join(os.path.dirname(__file__),"..","..",".."))
cfg=json.load(open(os.path.join(_ROOT,"backend","data","settings.json")))  # key 从 gitignore 的 settings.json 读
x=cfg["providers"]["xiaomi"]; KEY=x["api_key"]; BASE=x["base_url"].rstrip("/")
H={"Authorization":f"Bearer {KEY}","Content-Type":"application/json"}
MODEL="mimo-v2.5"
HEDGE=re.compile(r"似乎|仿佛|如同|宛如|好像|大概|也许|约莫")
def hk(t): return round(len(HEDGE.findall(t))/max(1,len(t))*1000,2)
def gen(extra,seed,tries=4):
    body={"model":MODEL,"messages":[{"role":"system","content":"你是一位中文小说写手。"+extra},
          {"role":"user","content":"写一段约500字的中文小说场景:一个人深夜独自在老公寓里等一通迟迟不来的电话。只写正文。"+f"(变体{seed})"}],
          "max_completion_tokens":900,"temperature":0.9,"top_p":0.95}
    for k in range(tries):
        try:
            req=urllib.request.Request(BASE+"/chat/completions",data=json.dumps(body).encode(),headers=H,method="POST")
            return json.loads(urllib.request.urlopen(req,timeout=120).read())["choices"][0]["message"]["content"] or ""
        except urllib.error.HTTPError as e:
            if e.code==429: time.sleep(3*(k+1)); continue
            time.sleep(2)
        except Exception: time.sleep(2)
    return ""
W="“似乎、仿佛、宛如、好像、大概、也许”这类表示推测/不确定的弱断言词"
NUM={2:f"风格要求:让{W}的密度约为每千字 2 处(约500字即约1处)。",
     6:f"风格要求:让{W}的密度约为每千字 6 处(约500字即约3处)。",
     12:f"风格要求:让{W}的密度约为每千字 12 处(约500字即约6处)。"}
# steelman 自然语言:用编辑会用的、尽量到位的定性表达
QUAL={"低":f"风格要求:语气笃定干脆,通篇几乎不用{W},点到为止。",
      "中":f"风格要求:克制而自然地用一点{W},既不刻意堆砌也不完全回避,保持轻微的不确定感。",
      "高":f"风格要求:大量、反复地用{W},让整段叙述弥漫浓重的迟疑与不确定。"}
SAMP=6
print("== 数字设定 ==")
numres={}
for tgt,p in NUM.items():
    vs=[hk(gen(p,f"n{tgt}{s}")) for s in range(SAMP)]; numres[tgt]=vs
    print(f"  目标≈{tgt:<3} 实测={[round(v,1) for v in vs]} 均值={round(st.mean(vs),2)} 标准差={round(st.pstdev(vs),2)} MAE={round(st.mean([abs(v-tgt) for v in vs]),2)}")
print("== 自然语言(steelman)==")
qres={}
for lab,p in QUAL.items():
    vs=[hk(gen(p,f"q{lab}{s}")) for s in range(SAMP)]; qres[lab]=vs
    print(f"  档位{lab}  实测={[round(v,1) for v in vs]} 均值={round(st.mean(vs),2)} 标准差={round(st.pstdev(vs),2)}")
def mono(seq): return all(seq[i]<seq[i+1] for i in range(len(seq)-1))
nm=[st.mean(numres[t]) for t in (2,6,12)]; qm=[st.mean(qres[l]) for l in ("低","中","高")]
print(f"\n数字  三档均值={[round(v,1) for v in nm]} 单调={mono(nm)}")
print(f"自然语言 三档均值={[round(v,1) for v in qm]} 单调={mono(qm)}")
json.dump({"num":numres,"qual":qres},open("/tmp/numexp3_results.json","w"),ensure_ascii=False,indent=2)
