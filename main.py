
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import HTMLResponse
from typing import List
from openai import OpenAI
from openpyxl import load_workbook
from pypdf import PdfReader
from docx import Document
import os, io, json, base64, html, statistics

app = FastAPI(title="AI Credit Analysis V5", version="5.0.0")
MODEL=os.getenv("OPENAI_MODEL","gpt-5")
MAX_FILE_MB=int(os.getenv("MAX_FILE_MB","15"))
MAX_TOTAL_MB=int(os.getenv("MAX_TOTAL_MB","40"))

def h(x): return html.escape(str(x if x is not None else ""))
def n(x,d=0.0):
    try:
        if isinstance(x,str): x=x.replace(",","").replace("٬","").replace("%","").strip()
        return float(x)
    except: return d
def dv(a,b,d=0): return d if n(b)==0 else n(a)/n(b)
def money(x): return f"{n(x):,.0f}"
def pct(x): return f"{n(x)*100:.1f}%"
def rx(x): return "∞" if n(x)>=90 else f"{n(x):.2f}x"
def clamp(x,a=0,b=100): return max(a,min(b,n(x)))

def local_text(data,name):
    ext=os.path.splitext(name.lower())[1]
    try:
        if ext==".pdf":
            r=PdfReader(io.BytesIO(data)); out=[]
            for i,p in enumerate(r.pages[:100],1):
                t=p.extract_text() or ""
                if t.strip(): out.append(f"\n--- PAGE {i} ---\n{t}")
            return "".join(out)[:450000]
        if ext in (".xlsx",".xlsm"):
            wb=load_workbook(io.BytesIO(data),data_only=True,read_only=True); out=[]
            for ws in wb.worksheets[:25]:
                out.append(f"\n### SHEET {ws.title}\n")
                for ri,row in enumerate(ws.iter_rows(values_only=True),1):
                    vals=[str(v) if v is not None else "" for v in row[:60]]
                    if any(v.strip() for v in vals): out.append(f"R{ri}\t"+"\t".join(vals))
                    if sum(map(len,out))>300000: break
            return "\n".join(out)[:450000]
        if ext==".docx":
            d=Document(io.BytesIO(data)); out=[p.text for p in d.paragraphs if p.text.strip()]
            for t in d.tables:
                for r in t.rows: out.append("\t".join(c.text for c in r.cells))
            return "\n".join(out)[:450000]
        if ext in (".csv",".txt"):
            for enc in ("utf-8-sig","utf-8","cp1256","latin-1"):
                try:return data.decode(enc)[:450000]
                except:pass
    except: pass
    return ""

SCHEMA={"type":"object","additionalProperties":False,"properties":{
"company":{"type":"object","additionalProperties":False,"properties":{
"name":{"type":"string"},"sector":{"type":"string"},"legal_form":{"type":"string"},"business_description":{"type":"string"},
"management_summary":{"type":"string"}},"required":["name","sector","legal_form","business_description","management_summary"]},
"periods":{"type":"array","items":{"type":"object","additionalProperties":False,"properties":{
"period":{"type":"string"},"currency":{"type":"string"},"revenue":{"type":"number"},"cogs":{"type":"number"},
"gross_profit":{"type":"number"},"ebitda":{"type":"number"},"net_profit":{"type":"number"},"cash":{"type":"number"},
"receivables":{"type":"number"},"inventory":{"type":"number"},"current_assets":{"type":"number"},"total_assets":{"type":"number"},
"payables":{"type":"number"},"current_liabilities":{"type":"number"},"total_debt":{"type":"number"},
"total_liabilities":{"type":"number"},"equity":{"type":"number"},"cfo":{"type":"number"},"interest_expense":{"type":"number"}},
"required":["period","currency","revenue","cogs","gross_profit","ebitda","net_profit","cash","receivables","inventory",
"current_assets","total_assets","payables","current_liabilities","total_debt","total_liabilities","equity","cfo","interest_expense"]}},
"facility":{"type":"object","additionalProperties":False,"properties":{
"purpose":{"type":"string"},"requested_amount":{"type":"number"},"currency":{"type":"string"},"tenor_months":{"type":"number"},
"annual_rate":{"type":"number"},"existing_annual_debt_service":{"type":"number"},"repayment_source":{"type":"string"}},
"required":["purpose","requested_amount","currency","tenor_months","annual_rate","existing_annual_debt_service","repayment_source"]},
"collateral":{"type":"array","items":{"type":"object","additionalProperties":False,"properties":{
"type":{"type":"string"},"market_value":{"type":"number"},"forced_sale_value":{"type":"number"},"legal_status":{"type":"string"}},
"required":["type","market_value","forced_sale_value","legal_status"]}},
"behavior":{"type":"object","additionalProperties":False,"properties":{
"days_past_due":{"type":"number"},"default_flag":{"type":"boolean"},"bureau_summary":{"type":"string"},"account_turnover_summary":{"type":"string"}},
"required":["days_past_due","default_flag","bureau_summary","account_turnover_summary"]},
"qualitative":{"type":"object","additionalProperties":False,"properties":{
"character":{"type":"number"},"capacity":{"type":"number"},"capital":{"type":"number"},"collateral":{"type":"number"},
"conditions":{"type":"number"},"management":{"type":"number"},"governance":{"type":"number"},"market":{"type":"number"}},
"required":["character","capacity","capital","collateral","conditions","management","governance","market"]},
"strengths":{"type":"array","items":{"type":"string"}},"risks":{"type":"array","items":{"type":"string"}},
"missing_items":{"type":"array","items":{"type":"string"}},"document_warnings":{"type":"array","items":{"type":"string"}},
"evidence":{"type":"array","items":{"type":"object","additionalProperties":False,"properties":{
"field":{"type":"string"},"value":{"type":"string"},"source_file":{"type":"string"},"location":{"type":"string"},
"confidence":{"type":"number"},"comment":{"type":"string"}},"required":["field","value","source_file","location","confidence","comment"]}}
},"required":["company","periods","facility","collateral","behavior","qualitative","strengths","risks","missing_items","document_warnings","evidence"]}

PROMPT='''أنت محرك Document Intelligence مصرفي للائتمان المؤسسي. استخرج من الملفات فقط ولا تخمّن.
حافظ على السنوات والعملات والوحدات. اربط القيم المهمة باسم الملف والصفحة/الورقة في evidence.
افحص معادلة الأصول=الالتزامات+حقوق الملكية، ومجمل الربح≈الإيراد-التكلفة، وأبلغ عن التناقضات.
استخدم 0 للحقل غير الموجود وأضفه إلى missing_items. قيّم 5Cs والإدارة والحوكمة والسوق 0-100؛ عند ضعف الدليل استخدم 50 واشرح النقص.
لا تذكر أي دراسة مرجعية أو حالة مرجعية. أخرج JSON فقط.'''

def ai_extract(items):
    key=os.getenv("OPENAI_API_KEY","").strip()
    if not key: raise RuntimeError("OPENAI_API_KEY غير مضاف في Railway → Variables.")
    client=OpenAI(api_key=key); content=[{"type":"input_text","text":PROMPT}]; texts=[]
    for it in items:
        name=it["name"]; ext=os.path.splitext(name.lower())[1]
        if ext in (".png",".jpg",".jpeg",".webp"):
            mime="image/png" if ext==".png" else "image/webp" if ext==".webp" else "image/jpeg"
            content.append({"type":"input_image","image_url":f"data:{mime};base64,{base64.b64encode(it['data']).decode()}","detail":"high"})
            content.append({"type":"input_text","text":"اسم ملف الصورة: "+name})
        elif ext==".pdf":
            content.append({"type":"input_file","filename":name,"file_data":base64.b64encode(it["data"]).decode()})
            if it["text"]: texts.append(f"\n===== {name} =====\n{it['text'][:100000]}")
        elif it["text"]: texts.append(f"\n===== {name} =====\n{it['text'][:160000]}")
    if texts: content.append({"type":"input_text","text":"نص وجداول مساعدة:\n"+"".join(texts)[:400000]})
    r=client.responses.create(model=MODEL,store=False,input=[{"role":"user","content":content}],
        text={"format":{"type":"json_schema","name":"credit_extract","strict":True,"schema":SCHEMA}})
    return json.loads(r.output_text)

def metrics(p):
    rev=n(p.get("revenue")); cogs=n(p.get("cogs")); gp=n(p.get("gross_profit")); e=n(p.get("ebitda")); ni=n(p.get("net_profit"))
    ca=n(p.get("current_assets")); cl=n(p.get("current_liabilities")); inv=n(p.get("inventory")); eq=n(p.get("equity"))
    debt=n(p.get("total_debt")); ta=n(p.get("total_assets")); cfo=n(p.get("cfo")); intr=n(p.get("interest_expense"))
    ar=n(p.get("receivables")); ap=n(p.get("payables"))
    return {"gm":dv(gp,rev),"nm":dv(ni,rev),"em":dv(e,rev),"cr":dv(ca,cl,99),"qr":dv(ca-inv,cl,99),
            "de":dv(debt,eq,99),"da":dv(debt,ta),"ic":dv(e,intr,99 if e>0 else 0),"cfom":dv(cfo,rev),
            "dso":dv(ar,rev)*365 if rev else 0,"dio":dv(inv,cogs)*365 if cogs else 0,"dpo":dv(ap,cogs)*365 if cogs else 0}

def lin(v,bad,good,higher=True):
    if good==bad:return 50
    z=(v-bad)/(good-bad)*100 if higher else (bad-v)/(bad-good)*100
    return clamp(z)

def engine(data):
    ps=data.get("periods",[]); p=ps[-1] if ps else {}; m=metrics(p); f=data.get("facility",{}); b=data.get("behavior",{}); q=data.get("qualitative",{})
    req=n(f.get("requested_amount")); yrs=max(n(f.get("tenor_months"),12)/12,1); rate=n(f.get("annual_rate"))
    if rate>1:rate/=100
    ds=n(f.get("existing_annual_debt_service"))+req/yrs+req*rate
    dscr=dv(p.get("cfo"),ds,99 if n(p.get("cfo"))>0 else 0)
    coll=sum(n(x.get("forced_sale_value")) for x in data.get("collateral",[])); cov=dv(coll,req)
    qavg=statistics.mean([clamp(q.get(k,50)) for k in ["character","capacity","capital","collateral","conditions","management","governance","market"]])
    fin=lin(m["cr"],.8,1.8)*.1+lin(m["qr"],.35,1.1)*.08+lin(m["de"],4,.8,False)*.15+lin(m["ic"],1,5)*.12+lin(dscr,.8,1.75)*.27+lin(m["em"],.03,.2)*.1+(100 if n(p.get("cfo"))>0 else 10)*.1+lin(m["dso"]+m["dio"]-m["dpo"],150,30,False)*.08
    ev=data.get("evidence",[]); conf=statistics.mean([clamp(n(x.get("confidence"),.5),0,1)*100 for x in ev]) if ev else 35
    quality=conf*.7+max(0,100-len(data.get("missing_items",[]))*7)*.3
    score=round(fin*.6+qavg*.3+quality*.1,1)
    grade,risk=(("1","منخفضة جداً") if score>=90 else ("2","منخفضة") if score>=82 else ("3","متوسطة-منخفضة") if score>=74 else ("4","متوسطة") if score>=66 else ("5","متوسطة-مرتفعة") if score>=58 else ("6","مرتفعة") if score>=50 else ("7","مرتفعة جداً") if score>=40 else ("8","حرجة"))
    equity=n(p.get("equity")); debt=n(p.get("total_debt")); cashlim=max(n(p.get("cfo"))/1.25-n(f.get("existing_annual_debt_service")),0)/((1/yrs)+rate) if ((1/yrs)+rate)>0 else 0
    levlim=max(3*equity-debt,0); colllim=coll/1.2 if coll else req; limit=max(0,min(req,cashlim,levlim,colllim))
    flags=[]
    if n(b.get("days_past_due"))>=90 or b.get("default_flag"):flags.append("مؤشر تعثر/تأخر 90 يوماً أو أكثر.")
    if dscr<1:flags.append(f"DSCR {dscr:.2f}x أقل من 1.00x.")
    elif dscr<1.25:flags.append(f"DSCR {dscr:.2f}x دون المستوى الإرشادي 1.25x.")
    if m["de"]>3:flags.append(f"Debt/Equity {m['de']:.2f}x مرتفع.")
    if quality<70:flags.append(f"جودة/ثقة البيانات {quality:.0f}/100 تحتاج استكمالاً.")
    decision="لا يوصى بالموافقة بالشكل الحالي" if (b.get("default_flag") or n(b.get("days_past_due"))>=90 or dscr<1) else "مؤهل للموافقة المشروطة بعد استكمال الضوابط" if score>=74 and dscr>=1.25 and quality>=75 else "مراجعة وإعادة هيكلة قبل العرض على اللجنة"
    color="red" if "لا يوصى" in decision else "green" if "مؤهل" in decision else "amber"
    sc=[("الأساسي",dscr),("ضغط متوسط",dv(n(p.get("cfo"))*.75,ds)),("ضغط شديد",dv(n(p.get("cfo"))*.55,ds))]
    dpd=n(b.get("days_past_due")); stage="Stage 3" if b.get("default_flag") or dpd>=90 else "Stage 2" if dpd>30 else "Stage 1"
    pdmap={"1":.005,"2":.01,"3":.02,"4":.04,"5":.075,"6":.13,"7":.22,"8":.35}; pd=pdmap[grade]*(2 if stage=="Stage 2" else 1); pd=1 if stage=="Stage 3" else min(pd,1)
    lgd=clamp((1-dv(coll*.85,req))*100,10,90)/100 if req else 0
    return {"m":m,"score":score,"grade":grade,"risk":risk,"quality":quality,"dscr":dscr,"cov":cov,"limit":limit,"cashlim":cashlim,"levlim":levlim,"colllim":colllim,"flags":flags,"decision":decision,"color":color,"sc":sc,"stage":stage,"pd":pd,"lgd":lgd,"ecl":req*pd*lgd}

MEMO_SCHEMA={"type":"object","additionalProperties":False,"properties":{
"executive_summary":{"type":"string"},"financial_assessment":{"type":"string"},"cashflow_assessment":{"type":"string"},"working_capital_assessment":{"type":"string"},
"facility_assessment":{"type":"string"},"collateral_assessment":{"type":"string"},"business_management_assessment":{"type":"string"},
"strengths":{"type":"array","items":{"type":"string"}},"risks":{"type":"array","items":{"type":"string"}},"mitigants":{"type":"array","items":{"type":"string"}},
"conditions":{"type":"array","items":{"type":"string"}},"covenants":{"type":"array","items":{"type":"string"}},"early_warnings":{"type":"array","items":{"type":"string"}},
"committee_questions":{"type":"array","items":{"type":"string"}},"recommendation_rationale":{"type":"string"}},
"required":["executive_summary","financial_assessment","cashflow_assessment","working_capital_assessment","facility_assessment","collateral_assessment","business_management_assessment","strengths","risks","mitigants","conditions","covenants","early_warnings","committee_questions","recommendation_rationale"]}

def ai_memo(data,e):
    client=OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    prompt="أنت محلل ائتماني مؤسسي أول. اكتب مذكرة عربية احترافية من الحقائق فقط، لا تخترع. ركز على السداد والتدفق ورأس المال العامل والمخاطر والمخففات والشروط. لا تذكر أي مرجع سري.\nDATA:\n"+json.dumps(data,ensure_ascii=False)[:180000]+"\nENGINE:\n"+json.dumps(e,ensure_ascii=False)[:40000]
    r=client.responses.create(model=MODEL,store=False,input=prompt,text={"format":{"type":"json_schema","name":"memo","strict":True,"schema":MEMO_SCHEMA}})
    return json.loads(r.output_text)

def chart(ps,key,title):
    vals=[n(x.get(key)) for x in ps]; labs=[str(x.get("period","")) for x in ps]
    if not vals:return f'<div class="empty">{h(title)}: لا بيانات</div>'
    W,H,P=620,230,44; mn=min(vals); mx=max(vals)
    if mx==mn:mx=mn+1
    pts=[]
    for i,v in enumerate(vals):
        x=P+(W-2*P)*i/max(len(vals)-1,1); y=H-P-(H-2*P)*(v-mn)/(mx-mn); pts.append((x,y,v))
    path=" ".join(("M" if i==0 else "L")+f" {x:.1f} {y:.1f}" for i,(x,y,v) in enumerate(pts))
    dots="".join(f'<circle cx="{x}" cy="{y}" r="5"/><text x="{x}" y="{max(17,y-10)}" text-anchor="middle">{money(v)}</text><text x="{x}" y="{H-12}" text-anchor="middle">{h(labs[i])}</text>' for i,(x,y,v) in enumerate(pts))
    return f'<div class="chart"><b>{h(title)}</b><svg viewBox="0 0 {W} {H}"><path d="{path}" class="line"/>{dots}</svg></div>'

CSS='''*{box-sizing:border-box}body{margin:0;background:#eef3f8;color:#11243d;font-family:system-ui,-apple-system,"Segoe UI",Tahoma,Arial}
header{background:linear-gradient(120deg,#071a34,#0d5272);color:#fff}.top,.wrap{max-width:1250px;margin:auto}.top{padding:17px;display:flex;justify-content:space-between;align-items:center}.brand{font-weight:950;font-size:21px}.brand small{display:block;color:#cbd9e8;font-size:11px}.ver{border:1px solid #ffffff35;border-radius:999px;padding:8px 12px}
.wrap{padding:18px 11px 60px}.card{background:#fff;border:1px solid #dce5ee;border-radius:22px;box-shadow:0 10px 30px #0b244015;margin-bottom:14px}.hero,.sec{padding:23px}.hero{background:linear-gradient(135deg,#fff 60%,#e8faf7)}.eye{color:#0b8a7f;font-weight:950;font-size:12px}h1{font-size:32px;margin:8px 0}h2{margin:0 0 12px}h3{margin:20px 0 8px}p{line-height:1.8;color:#637187}.notice{padding:13px;border-radius:13px;background:#fff8e6;border:1px solid #f1d48b;color:#72540a}.ok{background:#ecfdf5;border-color:#a7f3d0;color:#065f46}.bad{background:#fff1f2;border-color:#fecdd3;color:#9f1239}
.flow,.docs,.kpis,.charts,.cols{display:grid;gap:10px}.flow{grid-template-columns:repeat(6,1fr)}.step,.doc,.kpi,.panel,.chart{border:1px solid #dce5ee;border-radius:15px;padding:14px;background:#fbfdff}.step{text-align:center;font-size:12px}.step b{display:block;font-size:18px}.docs{grid-template-columns:repeat(4,1fr)}.kpis{grid-template-columns:repeat(4,1fr)}.kpi span{font-size:12px;color:#697688}.kpi b{display:block;font-size:23px;margin-top:5px}.charts,.cols{grid-template-columns:1fr 1fr}.chart svg{width:100%;min-width:400px}.line{fill:none;stroke:#0f766e;stroke-width:4}.chart circle{fill:#0f766e}.chart text{font-size:10px;fill:#64748b}
.drop{border:2px dashed #9dadbd;border-radius:18px;padding:26px;text-align:center;background:#f8fafc}input[type=file]{width:100%;padding:12px;background:#fff;border:1px solid #cbd6e2;border-radius:12px}.btn{border:0;border-radius:12px;padding:13px 18px;background:#087d73;color:#fff;font-weight:900}.decision{padding:17px;border-radius:15px;font-weight:950;font-size:18px}.red{background:#fee2e2;color:#8b1b1b}.amber{background:#fef3c7;color:#7c4a05}.green{background:#dcfce7;color:#14532d}.tbl{overflow:auto}table{width:100%;border-collapse:collapse;min-width:720px;font-size:12px}th,td{padding:9px;border-bottom:1px solid #e5ebf1;text-align:right}th{background:#f8fafc}ul{line-height:1.9}details{margin-top:10px;border:1px solid #dde5ed;border-radius:13px;padding:11px}summary{font-weight:900}
@media(max-width:760px){.flow{grid-template-columns:repeat(3,1fr)}.docs,.kpis,.charts,.cols{grid-template-columns:1fr 1fr}h1{font-size:26px}}@media(max-width:520px){.docs,.kpis,.charts,.cols{grid-template-columns:1fr}.flow{grid-template-columns:repeat(2,1fr)}.hero,.sec{padding:17px}.top{padding:12px 9px}}'''

def shell(body,title="AI Credit Analysis V5"):
    return f'<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{h(title)}</title><style>{CSS}</style></head><body><header><div class="top"><div class="brand">AI Credit Analysis<small>AI Document Intelligence • Corporate Underwriting • Explainable Decision Support</small></div><div class="ver">V5 • AI-Powered</div></div></header><main class="wrap">{body}</main></body></html>'

@app.get("/",response_class=HTMLResponse)
def home():
    ready=bool(os.getenv("OPENAI_API_KEY","").strip())
    status='<div class="notice ok">● الذكاء الاصطناعي متصل وجاهز.</div>' if ready else '<div class="notice bad">● أضف OPENAI_API_KEY في Railway → Variables لتفعيل القراءة الذكية.</div>'
    body=f'''<section class="card hero"><div class="eye">AI-POWERED CORPORATE UNDERWRITING</div><h1>من مستندات العميل إلى مذكرة لجنة ائتمانية</h1><p>قراءة متعددة الملفات والسنوات، أدلة مصدرية، فحوص اتساق، Financial Spreading، مؤشرات ورسوم، 5Cs، DSCR، رأس المال العامل، حجم التسهيل، الضمان، اختبارات الضغط، الشروط ومؤشرات الإنذار المبكر.</p>{status}</section>
<section class="card sec"><div class="flow"><div class="step"><b>01</b>رفع</div><div class="step"><b>02</b>AI Extraction</div><div class="step"><b>03</b>Reconcile</div><div class="step"><b>04</b>Credit Engine</div><div class="step"><b>05</b>Stress</div><div class="step"><b>06</b>Memo</div></div></section>
<section class="card sec"><h2>رفع ملف العميل</h2><form method="post" action="/underwrite" enctype="multipart/form-data"><div class="drop"><input type="file" name="files" multiple required accept=".pdf,.xlsx,.xlsm,.docx,.csv,.txt,.png,.jpg,.jpeg,.webp"><p>ارفع القوائم + طلب التمويل + كشوف الحساب + الضمانات + الاستعلامات والوثائق الداعمة.</p><button class="btn">تحليل المستندات بالذكاء الاصطناعي</button></div></form><div class="notice" style="margin-top:12px">قبل بيانات العملاء الحقيقية يجب اعتماد مزود الذكاء الاصطناعي وسياسات الخصوصية والاحتفاظ والصلاحيات داخل البنك. لا تضع مفتاح API في GitHub.</div></section>'''
    return shell(body)

@app.post("/underwrite",response_class=HTMLResponse)
async def underwrite(files:List[UploadFile]=File(...)):
    items=[]; total=0; docs=[]
    for f in files[:25]:
        data=await f.read(); total+=len(data)
        if len(data)>MAX_FILE_MB*1024*1024 or total>MAX_TOTAL_MB*1024*1024:return HTMLResponse(shell('<section class="card sec"><h2>حجم الملفات يتجاوز الحد المسموح.</h2></section>'),413)
        t=local_text(data,f.filename or "document"); items.append({"name":f.filename or "document","data":data,"text":t}); docs.append((f.filename or "document",len(data),bool(t)))
    try:data=ai_extract(items)
    except Exception as ex:return HTMLResponse(shell(f'<section class="card sec"><h2>تعذر تشغيل AI</h2><div class="notice bad">{h(ex)}</div><p>راجع Railway Variables وDeploy Logs. لا تشارك مفتاح API هنا.</p></section>'),500)
    e=engine(data)
    try:memo=ai_memo(data,e)
    except Exception: memo=None
    ps=data.get("periods",[]); m=e["m"]; c=data.get("company",{}); f=data.get("facility",{}); q=data.get("qualitative",{})
    doccards="".join(f'<div class="doc"><b>{h(a)}</b><br><small>{b/1024:.0f} KB • {"Text+AI" if t else "Vision/File AI"}</small></div>' for a,b,t in docs)
    k=[("التقييم",f'{e["score"]:.0f}/100'),("المخاطر",f'{e["grade"]} — {e["risk"]}'),("DSCR",rx(e["dscr"])),("الحد الإرشادي",money(e["limit"])),("Current Ratio",rx(m["cr"])),("Quick Ratio",rx(m["qr"])),("Debt/Equity",rx(m["de"])),("Interest Cover",rx(m["ic"])),("EBITDA Margin",pct(m["em"])),("CFO Margin",pct(m["cfom"])),("DSO",f'{m["dso"]:.0f} يوم'),("دورة النقد",f'{m["dso"]+m["dio"]-m["dpo"]:.0f} يوم')]
    kp="".join(f'<div class="kpi"><span>{a}</span><b>{b}</b></div>' for a,b in k)
    rows="".join(f'<tr><td>{h(x.get("period"))}</td><td>{h(x.get("currency"))}</td><td>{money(x.get("revenue"))}</td><td>{money(x.get("ebitda"))}</td><td>{money(x.get("net_profit"))}</td><td>{money(x.get("cfo"))}</td><td>{rx(metrics(x)["cr"])}</td><td>{rx(metrics(x)["de"])}</td></tr>' for x in ps)
    qual="".join(f'<p><b>{lab}</b>: {clamp(q.get(key,50)):.0f}/100</p>' for key,lab in [("character","Character"),("capacity","Capacity"),("capital","Capital"),("collateral","Collateral"),("conditions","Conditions"),("management","الإدارة"),("governance","الحوكمة"),("market","السوق")])
    li=lambda xs,fb="غير متوفر":"".join(f"<li>{h(x)}</li>" for x in xs) if xs else f"<li>{fb}</li>"
    flags=li(e["flags"],"لا توجد بوابات كمية حادة ظاهرة.")
    sc="".join(f'<tr><td>{a}</td><td>{rx(b)}</td><td>{"مقبول" if b>=1.25 else "حساس" if b>=1 else "غير مغطى"}</td></tr>' for a,b in e["sc"])
    mm=memo or {}; memoh=""
    for title,key in [("الملخص التنفيذي","executive_summary"),("التحليل المالي","financial_assessment"),("التدفقات وقدرة السداد","cashflow_assessment"),("رأس المال العامل","working_capital_assessment"),("هيكل التسهيل","facility_assessment"),("الضمانات","collateral_assessment"),("النشاط والإدارة","business_management_assessment"),("مبررات التوصية","recommendation_rationale")]:
        if mm.get(key):memoh+=f'<h3>{title}</h3><p>{h(mm[key])}</p>'
    evid="".join(f'<tr><td>{h(x.get("field"))}</td><td>{h(x.get("value"))}</td><td>{h(x.get("source_file"))}</td><td>{h(x.get("location"))}</td><td>{n(x.get("confidence"))*100:.0f}%</td><td>{h(x.get("comment"))}</td></tr>' for x in data.get("evidence",[])[:100])
    body=f'''<section class="card hero"><div class="eye">AI CREDIT MEMORANDUM • HUMAN REVIEW REQUIRED</div><h1>{h(c.get("name") or "العميل")}</h1><p>{h(c.get("sector"))} • {h(c.get("business_description"))}</p><div class="decision {e["color"]}">{h(e["decision"])}</div></section>
<section class="card sec"><h2>المستندات</h2><div class="docs">{doccards}</div></section>
<section class="card sec"><h2>لوحة القرار</h2><div class="kpis">{kp}</div></section>
<section class="card sec"><h2>الاتجاهات</h2><div class="charts">{chart(ps,"revenue","الإيرادات")}{chart(ps,"ebitda","EBITDA")}{chart(ps,"cfo","التدفق التشغيلي")}{chart(ps,"total_debt","إجمالي الدين")}</div></section>
<section class="card sec"><h2>Financial Spreading</h2><div class="tbl"><table><tr><th>الفترة</th><th>العملة</th><th>الإيرادات</th><th>EBITDA</th><th>صافي الربح</th><th>CFO</th><th>Current</th><th>D/E</th></tr>{rows}</table></div></section>
<section class="card sec"><div class="cols"><div class="panel"><h2>5Cs + الإدارة والحوكمة</h2>{qual}</div><div class="panel"><h2>هيكل التسهيل</h2><p><b>الغرض:</b> {h(f.get("purpose"))}</p><p><b>الطلب:</b> {money(f.get("requested_amount"))} {h(f.get("currency"))}</p><p><b>مصدر السداد:</b> {h(f.get("repayment_source"))}</p><p><b>قيد التدفق:</b> {money(e["cashlim"])}</p><p><b>قيد الرافعة:</b> {money(e["levlim"])}</p><p><b>قيد الضمان:</b> {money(e["colllim"])}</p><p><b>الحد المقترح:</b> {money(e["limit"])}</p></div></div></section>
<section class="card sec"><h2>اختبارات الضغط</h2><div class="tbl"><table><tr><th>السيناريو</th><th>DSCR</th><th>الحالة</th></tr>{sc}</table></div></section>
<section class="card sec"><div class="cols"><div class="panel"><h2>نقاط القوة</h2><ul>{li(mm.get("strengths") or data.get("strengths",[]))}</ul><h3>المخففات</h3><ul>{li(mm.get("mitigants",[]))}</ul></div><div class="panel"><h2>المخاطر والاستثناءات</h2><ul>{flags}{li(mm.get("risks") or data.get("risks",[]),"لا توجد مخاطر وصفية إضافية.")}</ul></div></div></section>
<section class="card sec"><h2>IFRS 9 — مؤشرات إرشادية</h2><div class="kpis"><div class="kpi"><span>Stage</span><b>{e["stage"]}</b></div><div class="kpi"><span>PD proxy</span><b>{pct(e["pd"])}</b></div><div class="kpi"><span>LGD proxy</span><b>{pct(e["lgd"])}</b></div><div class="kpi"><span>ECL indicative</span><b>{money(e["ecl"])}</b></div></div><p>لا تعد قياسات رقابية/محاسبية معتمدة قبل المعايرة والتحقق والحوكمة.</p></section>
<section class="card sec"><h2>مذكرة اللجنة بالذكاء الاصطناعي</h2>{memoh}<div class="cols"><div class="panel"><h3>الشروط السابقة للصرف</h3><ul>{li(mm.get("conditions",[]))}</ul><h3>Covenants</h3><ul>{li(mm.get("covenants",[]))}</ul></div><div class="panel"><h3>الإنذار المبكر</h3><ul>{li(mm.get("early_warnings",[]))}</ul><h3>أسئلة اللجنة</h3><ul>{li(mm.get("committee_questions",[]))}</ul></div></div></section>
<section class="card sec"><h2>جودة البيانات والتتبع</h2><div class="kpis"><div class="kpi"><span>Data Quality</span><b>{e["quality"]:.0f}/100</b></div><div class="kpi"><span>Missing</span><b>{len(data.get("missing_items",[]))}</b></div><div class="kpi"><span>Evidence</span><b>{len(data.get("evidence",[]))}</b></div><div class="kpi"><span>AI Model</span><b style="font-size:14px">{h(MODEL)}</b></div></div>
<details><summary>النواقص والتحذيرات</summary><h3>نواقص</h3><ul>{li(data.get("missing_items",[]))}</ul><h3>تحذيرات</h3><ul>{li(data.get("document_warnings",[]))}</ul></details>
<details><summary>Audit Trail — مصدر القيم</summary><div class="tbl"><table><tr><th>الحقل</th><th>القيمة</th><th>الملف</th><th>الموقع</th><th>الثقة</th><th>تعليق</th></tr>{evid}</table></div></details></section>'''
    return shell(body)

@app.get("/health")
def health():return {"status":"ok","version":"5.0.0","ai_configured":bool(os.getenv("OPENAI_API_KEY","").strip()),"model":MODEL}
