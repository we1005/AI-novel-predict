# 第二轮:闭环纠偏 —— 数字反馈 vs 自然语言反馈(系统 compare()→回灌 的真实机制)
import json, re, time, urllib.request, urllib.error, statistics as st
import os
_ROOT=os.path.abspath(os.path.join(os.path.dirname(__file__),"..","..",".."))
cfg=json.load(open(os.path.join(_ROOT,"backend","data","settings.json")))  # key 从 gitignore 的 settings.json 读
x=cfg["providers"]["xiaomi"]; KEY=x["api_key"]; BASE=x["base_url"].rstrip("/")
H={"Authorization":f"Bearer {KEY}","Content-Type":"application/json"}
MODEL="mimo-v2.5"
HEDGE=re.compile(r"似乎|仿佛|如同|宛如|好像|大概|也许|约莫")
def hk(t): return round(len(HEDGE.findall(t))/max(1,len(t))*1000,2)
def chat(msgs,tries=4):
    body={"model":MODEL,"messages":msgs,"max_completion_tokens":900,"temperature":0.85,"top_p":0.95}
    for k in range(tries):
        try:
            req=urllib.request.Request(BASE+"/chat/completions",data=json.dumps(body).encode(),headers=H,method="POST")
            return json.loads(urllib.request.urlopen(req,timeout=120).read())["choices"][0]["message"]["content"] or ""
        except urllib.error.HTTPError as e:
            if e.code==429: time.sleep(3*(k+1)); continue
            time.sleep(2)
        except Exception: time.sleep(2)
    return ""
TOPIC="写一段约500字的中文小说场景:一个人深夜独自在老公寓里等一通迟迟不来的电话。只写正文。"
WORDS="“似乎、仿佛、宛如、好像、大概、也许”这类模糊推测的弱断言词"
TARGET=5
SAMPLES=4
num_err=[]; nl_err=[]; d0s=[]
print(f"目标弱断言密度 = 每千字 {TARGET} 处\n")
for s in range(SAMPLES):
    draft=chat([{"role":"system","content":f"你是中文小说写手。请频繁使用{WORDS},让叙述充满迟疑。"},
                {"role":"user","content":TOPIC+f"(变体{s})"}])
    d0=hk(draft); d0s.append(d0)
    # 数字反馈纠偏
    numc=chat([{"role":"system","content":"你是中文小说写手,擅长按量化指标改写。"},
               {"role":"user","content":f"下面这段文字里{WORDS}的密度是每千字 {d0} 处,目标是每千字 {TARGET} 处。请改写它,把该密度调整到目标附近,保持情节与篇幅。只输出改写后的正文:\n\n{draft}"}])
    dn=hk(numc); num_err.append(abs(dn-TARGET))
    # 自然语言反馈纠偏
    nlc=chat([{"role":"system","content":"你是中文小说写手。"},
              {"role":"user","content":f"下面这段文字模糊推测的措辞太多了,读起来很迟疑。请改写它,明显减少这类模糊措辞,让语气更笃定,保持情节与篇幅。只输出改写后的正文:\n\n{draft}"}])
    dl=hk(nlc); nl_err.append(abs(dl-TARGET))
    print(f"s{s}: 初稿={d0:<6} → 数字纠偏={dn:<6}(|偏差|={round(abs(dn-TARGET),2)})  自然语言纠偏={dl:<6}(|偏差|={round(abs(dl-TARGET),2)})")
    time.sleep(0.3)
print(f"\n初稿均值={round(st.mean(d0s),2)}")
print(f"数字反馈   平均|偏差目标|={round(st.mean(num_err),2)}  (越小越准)")
print(f"自然语言反馈 平均|偏差目标|={round(st.mean(nl_err),2)}")
json.dump({"target":TARGET,"d0":d0s,"num_err":num_err,"nl_err":nl_err},open("/tmp/numexp2_results.json","w"),ensure_ascii=False,indent=2)
