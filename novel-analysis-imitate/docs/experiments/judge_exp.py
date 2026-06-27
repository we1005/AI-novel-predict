# 评委可靠性:不同能力档的评委,能否把"原作真文"判为最像?(impostor + 换评委)
import sqlite3, os, json, urllib.request, urllib.error, time, statistics as st
import os
_ROOT=os.path.abspath(os.path.join(os.path.dirname(__file__),"..","..",".."))
cfg=json.load(open(os.path.join(_ROOT,"backend","data","settings.json")))  # key 从 gitignore 的 settings.json 读
x=cfg["providers"]["xiaomi"]; KEY=x["api_key"]; BASE=x["base_url"].rstrip("/")
H={"Authorization":f"Bearer {KEY}","Content-Type":"application/json"}
ROOT=os.path.join(_ROOT,"backend","data","books")
def passage(slug,idx,clip=600):
    rows=sqlite3.connect(os.path.join(ROOT,slug,"novel.db")).execute(
      "SELECT body FROM chapter_fts WHERE length(body)>1500 ORDER BY chapter").fetchall()
    return (rows[idx][0] or "")[:clip]
ref=passage("余烬之铳",3)
cands={"原作真文(余烬之铳)":passage("余烬之铳",20),
       "网文(末法王座)":passage("末法王座",10),
       "江南腔(天之炽)":passage("天之炽-江南",10)}
def judge(model, ref, cand, tries=4):
    sys="你是严格的文风评审。只输出一个 0-100 的整数,不要任何解释。"
    usr=f"参考文风(原作真实片段):\n{ref}\n\n候选文字:\n{cand}\n\n这段候选在文风上与参考有多接近?给 0-100 分,只输出数字。"
    body={"model":model,"messages":[{"role":"system","content":sys},{"role":"user","content":usr}],
          "max_completion_tokens":2000,"temperature":0.3}
    for k in range(tries):
        try:
            r=json.loads(urllib.request.urlopen(urllib.request.Request(BASE+"/chat/completions",
              data=json.dumps(body).encode(),headers=H,method="POST"),timeout=120).read())
            txt=(r["choices"][0]["message"]["content"] or "").strip()
            import re; m=re.search(r"\d+",txt); 
            return int(m.group()) if m else None
        except urllib.error.HTTPError as e:
            if e.code==429: time.sleep(3*(k+1)); continue
            time.sleep(2)
        except Exception: time.sleep(2)
    return None
for model in ["mimo-v2.5","mimo-v2.5-pro"]:
    print(f"\n=== 评委:{model} ===")
    for name,c in cands.items():
        sc=[judge(model,ref,c) for _ in range(2)]
        sc=[s for s in sc if s is not None]
        print(f"  {name:18s} 相似分={sc}  均={round(st.mean(sc),1) if sc else 'NA'}")
