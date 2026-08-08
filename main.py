
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse
from typing import List
from openpyxl import load_workbook
from pypdf import PdfReader
from docx import Document
import os, io, html, statistics, re, csv

app = FastAPI(title="AI Credit Analysis V5.1 Offline", version="5.1.0")
MAX_FILE_MB=int(os.getenv("MAX_FILE_MB","15"))
MAX_TOTAL_MB=int(os.getenv("MAX_TOTAL_MB","40"))

def h(x): return html.escape(str("" if x is None else x))
def n(x,d=0.0):
    try:
        if isinstance(x,str): x=x.replace(",","").replace("٬","").replace("%","").strip()
        return float(x)
    except: return d
def dv(a,b,d=0):
    b=n(b); return d if b==0 else n(a)/b
def money(x): return f"{n(x):,.0f}"
def pct(x): return f"{n(x)*100:.1f}%"
def rx(x): return "∞" if n(x)>=90 else f"{n(x):.2f}x"
def clamp(x,a=0,b=100): return max(a,min(b,n(x)))

ALIASES={
"revenue":["revenue","sales","turnover","الإيرادات","الايرادات","المبيعات"],
"cogs":["cost of goods sold","cost of sales","cogs","تكلفة المبيعات","تكلفة البضاعة المباعة"],
"gross_profit":["gross profit","مجمل الربح","إجمالي الربح","اجمالي الربح"],
"ebitda":["ebitda","الربح قبل الفوائد والضرائب والاستهلاك والإطفاء"],
"net_profit":["net profit","net income","صافي الربح","صافي الدخل"],
"cash":["cash","cash and cash equivalents","النقد","النقدية","النقد وما في حكمه"],
"receivables":["receivables","accounts receivable","trade receivables","الذمم المدينة","المدينون"],
"inventory":["inventory","stocks","المخزون","المخزون السلعي"],
"current_assets":["current assets","الأصول المتداولة","الاصول المتداولة"],
"total_assets":["total assets","إجمالي الأصول","اجمالي الاصول"],
"payables":["payables","accounts payable","trade payables","الذمم الدائنة","الدائنون"],
"current_liabilities":["current liabilities","الالتزامات المتداولة","الخصوم المتداولة"],
"total_debt":["total debt","borrowings","loans","إجمالي الدين","اجمالي الدين","القروض"],
"total_liabilities":["total liabilities","إجمالي الالتزامات","اجمالي الالتزامات","إجمالي الخصوم","اجمالي الخصوم"],
"equity":["equity","shareholders equity","حقوق الملكية","حقوق المساهمين"],
"cfo":["cash flow from operations","operating cash flow","net cash from operating activities","التدفق النقدي التشغيلي","صافي النقد من الأنشطة التشغيلية"],
"interest_expense":["interest expense","finance cost","finance costs","مصروف الفوائد","تكلفة التمويل","تكاليف التمويل"]}

def norm(s):
    s=str(s or "").strip().lower()
    for a,b in [("إ","ا"),("أ","ا"),("آ","ا"),("ى","ي"),("ة","ه")]: s=s.replace(a,b)
    return re.sub(r"\s+"," ",s)
NAL={k:[norm(x) for x in v] for k,v in ALIASES.items()}

def metric(label):
    z=norm(label)
    for k,als in NAL.items():
        for a in als:
            if z==a or (len(a)>=5 and a in z): return k

def num(v):
    if v is None:return None
    if isinstance(v,(int,float)):return float(v)
    s=str(v).strip()
    if not s:return None
    neg=s.startswith("(") and s.endswith(")")
    s=s.strip("()").replace(",","").replace("٬","").replace(" ","").replace("−","-")
    if not re.fullmatch(r"[-+]?\d*\.?\d+",s):return None
    x=float(s); return -x if neg else x

def yearcols(row):
    out=[]
    for i,v in enumerate(row):
        m=re.search(r"(20\d{2}|19\d{2})",str(v or ""))
        if m: out.append((i,m.group(1)))
    return out

def extract_xlsx(data,name):
    wb=load_workbook(io.BytesIO(data),data_only=True,read_only=True); periods={}; ev=[]
    for ws in wb.worksheets[:30]:
        rows=[list(r[:80]) for r in ws.iter_rows(values_only=True)]
        hdr=[]
        for r in rows[:20]:
            y=yearcols(r)
            if y: hdr=y; break
        if not hdr: continue
        for ri,row in enumerate(rows,1):
            k=None
            for v in row[:12]:
                if isinstance(v,str) and v.strip():
                    k=metric(v)
                    if k: break
            if not k: continue
            for ci,yr in hdr:
                if ci<len(row):
                    val=num(row[ci])
                    if val is not None:
                        periods.setdefault(yr,{})[k]=val
                        ev.append({"field":k,"value":val,"file":name,"where":f"{ws.title}!R{ri}C{ci+1}","confidence":.99})
    return periods,ev

def extract_csv(data,name):
    text=""
    for enc in ("utf-8-sig","utf-8","cp1256","latin-1"):
        try:text=data.decode(enc);break
        except:pass
    rows=list(csv.reader(io.StringIO(text))); periods={}; ev=[]; hdr=[]
    for r in rows[:20]:
        y=yearcols(r)
        if y:hdr=y;break
    for ri,row in enumerate(rows,1):
        k=None
        for v in row[:8]:
            k=metric(v)
            if k:break
        if not k:continue
        for ci,yr in hdr:
            if ci<len(row):
                val=num(row[ci])
                if val is not None:
                    periods.setdefault(yr,{})[k]=val
                    ev.append({"field":k,"value":val,"file":name,"where":f"R{ri}C{ci+1}","confidence":.98})
    return periods,ev

def pdf_text(data):
    r=PdfReader(io.BytesIO(data)); out=[]
    for i,p in enumerate(r.pages[:100],1):
        t=p.extract_text() or ""
        if t.strip():out.append(f"--- PAGE {i} ---\n{t}")
    return "\n".join(out)

def docx_text(data):
    d=Document(io.BytesIO(data)); out=[p.text for p in d.paragraphs if p.text.strip()]
    for t in d.tables:
        for r in t.rows:out.append(" | ".join(c.text for c in r.cells))
    return "\n".join(out)

def extract_text(text,name):
    periods={};ev=[]; page="text"
    for line in [x.strip() for x in text.splitlines() if x.strip()]:
        if line.startswith("--- PAGE"):page=line
        k=metric(line)
        if not k:continue
        yrs=re.findall(r"(20\d{2}|19\d{2})",line)
        vals=[]
        for s in re.findall(r"\(?-?\d[\d,٬]*(?:\.\d+)?\)?",line):
            q=s.replace(",","").replace("٬","")
            if re.fullmatch(r"20\d{2}|19\d{2}",q):continue
            try:vals.append(float(q.strip("()"))*(-1 if s.startswith("(") else 1))
            except:pass
        if vals:
            yr=yrs[-1] if yrs else "Latest"
            periods.setdefault(yr,{})[k]=vals[-1]
            ev.append({"field":k,"value":vals[-1],"file":name,"where":page,"confidence":.70})
    return periods,ev

def merge(sets):
    out={}
    for ps in sets:
        for yr,v in ps.items():out.setdefault(yr,{}).update(v)
    return out

def finalize(ps):
    out=[]
    for yr in sorted(ps):
        p={"period":yr}
        for k in ALIASES:p[k]=float(ps[yr].get(k,0) or 0)
        if p["gross_profit"]==0 and p["revenue"] and p["cogs"]:p["gross_profit"]=p["revenue"]-p["cogs"]
        out.append(p)
    return out

def metrics(p):
    rev=n(p.get("revenue"));cogs=n(p.get("cogs"));gp=n(p.get("gross_profit"));eb=n(p.get("ebitda"));ni=n(p.get("net_profit"))
    ca=n(p.get("current_assets"));cl=n(p.get("current_liabilities"));inv=n(p.get("inventory"));eq=n(p.get("equity"));debt=n(p.get("total_debt"))
    ta=n(p.get("total_assets"));cfo=n(p.get("cfo"));intr=n(p.get("interest_expense"));ar=n(p.get("receivables"));ap=n(p.get("payables"))
    return {"gm":dv(gp,rev),"nm":dv(ni,rev),"em":dv(eb,rev),"cr":dv(ca,cl,99),"qr":dv(ca-inv,cl,99),"de":dv(debt,eq,99),
    "ic":dv(eb,intr,99 if eb>0 else 0),"cfom":dv(cfo,rev),"dso":dv(ar,rev)*365 if rev else 0,"dio":dv(inv,cogs)*365 if cogs else 0,"dpo":dv(ap,cogs)*365 if cogs else 0}

def lin(v,bad,good,higher=True):
    z=(v-bad)/(good-bad)*100 if higher else (bad-v)/(bad-good)*100
    return clamp(z)

def engine(periods,req,months,rate,existing,coll,dpd,default,qscore):
    p=periods[-1] if periods else {};m=metrics(p);yrs=max(n(months)/12,1);rate=n(rate)/100 if n(rate)>1 else n(rate)
    ds=n(existing)+n(req)/yrs+n(req)*rate;dscr=dv(p.get("cfo"),ds,99 if n(p.get("cfo"))>0 else 0)
    fin=lin(m["cr"],.8,1.8)*.10+lin(m["qr"],.35,1.1)*.08+lin(m["de"],4,.8,False)*.15+lin(m["ic"],1,5)*.12+lin(dscr,.8,1.75)*.27+lin(m["em"],.03,.2)*.10+(100 if n(p.get("cfo"))>0 else 10)*.10+lin(m["dso"]+m["dio"]-m["dpo"],150,30,False)*.08
    score=round(fin*.75+clamp(qscore)*.25,1)
    grade,risk=(("1","منخفضة جداً") if score>=90 else ("2","منخفضة") if score>=82 else ("3","متوسطة-منخفضة") if score>=74 else ("4","متوسطة") if score>=66 else ("5","متوسطة-مرتفعة") if score>=58 else ("6","مرتفعة") if score>=50 else ("7","مرتفعة جداً") if score>=40 else ("8","حرجة"))
    cashlim=max(n(p.get("cfo"))/1.25-n(existing),0)/((1/yrs)+rate) if ((1/yrs)+rate)>0 else 0
    levlim=max(3*n(p.get("equity"))-n(p.get("total_debt")),0);colllim=n(coll)/1.2 if n(coll) else n(req);limit=max(0,min(n(req),cashlim,levlim,colllim))
    decision="لا يوصى بالموافقة بالشكل الحالي" if default or n(dpd)>=90 or dscr<1 else "مؤهل للموافقة المشروطة" if score>=74 and dscr>=1.25 else "مراجعة وإعادة هيكلة قبل العرض على اللجنة"
    color="red" if "لا يوصى" in decision else "green" if "مؤهل" in decision else "amber"
    stage="Stage 3" if default or n(dpd)>=90 else "Stage 2" if n(dpd)>30 else "Stage 1"
    pdmap={"1":.005,"2":.01,"3":.02,"4":.04,"5":.075,"6":.13,"7":.22,"8":.35};pd=pdmap[grade]*(2 if stage=="Stage 2" else 1);pd=1 if stage=="Stage 3" else min(pd,1)
    lgd=clamp((1-dv(n(coll)*.85,n(req)))*100,10,90)/100 if n(req) else 0
    return {"m":m,"score":score,"grade":grade,"risk":risk,"dscr":dscr,"cashlim":cashlim,"levlim":levlim,"colllim":colllim,"limit":limit,"decision":decision,"color":color,"stage":stage,"pd":pd,"lgd":lgd,"ecl":n(req)*pd*lgd,"sc":[("الأساسي",dscr),("ضغط متوسط",dv(n(p.get("cfo"))*.75,ds)),("ضغط شديد",dv(n(p.get("cfo"))*.55,ds))]}

def consistency(periods):
    out=[]
    for p in periods:
        ta=n(p["total_assets"]);tl=n(p["total_liabilities"]);eq=n(p["equity"])
        if ta and (tl or eq) and abs(ta-(tl+eq))/max(abs(ta),1)>.03:out.append(f'{p["period"]}: معادلة المركز المالي غير متوازنة.')
        r=n(p["revenue"]);c=n(p["cogs"]);gp=n(p["gross_profit"])
        if r and c and gp and abs(gp-(r-c))/max(abs(gp),1)>.05:out.append(f'{p["period"]}: مجمل الربح لا يتطابق مع الإيراد ناقص التكلفة.')
    return out

def chart(ps,key,title):
    vals=[n(x.get(key)) for x in ps];labs=[x["period"] for x in ps]
    if not vals:return f'<div class="chart"><b>{h(title)}</b><p>لا بيانات</p></div>'
    W,H,P=620,230,44;mn=min(vals);mx=max(vals)
    if mx==mn:mx=mn+1
    pts=[]
    for i,v in enumerate(vals):
        x=P+(W-2*P)*i/max(len(vals)-1,1);y=H-P-(H-2*P)*(v-mn)/(mx-mn);pts.append((x,y,v))
    path=" ".join(("M" if i==0 else "L")+f" {x:.1f} {y:.1f}" for i,(x,y,v) in enumerate(pts))
    dots="".join(f'<circle cx="{x}" cy="{y}" r="5"/><text x="{x}" y="{max(17,y-10)}" text-anchor="middle">{money(v)}</text><text x="{x}" y="{H-12}" text-anchor="middle">{h(labs[i])}</text>' for i,(x,y,v) in enumerate(pts))
    return f'<div class="chart"><b>{h(title)}</b><svg viewBox="0 0 {W} {H}"><path d="{path}" class="line"/>{dots}</svg></div>'

CSS='''*{box-sizing:border-box}body{margin:0;background:#eef3f8;color:#11243d;font-family:system-ui,-apple-system,"Segoe UI",Tahoma,Arial}
header{background:linear-gradient(120deg,#071a34,#0d5272);color:#fff}.top,.wrap{max-width:1250px;margin:auto}.top{padding:17px;display:flex;justify-content:space-between;align-items:center}.brand{font-weight:950;font-size:21px}.brand small{display:block;color:#cbd9e8;font-size:11px}.ver{border:1px solid #ffffff35;border-radius:999px;padding:8px 12px}
.wrap{padding:18px 11px 60px}.card{background:#fff;border:1px solid #dce5ee;border-radius:22px;box-shadow:0 10px 30px #0b244015;margin-bottom:14px}.hero,.sec{padding:23px}.hero{background:linear-gradient(135deg,#fff 60%,#e8faf7)}.eye{color:#0b8a7f;font-weight:950;font-size:12px}h1{font-size:31px;margin:8px 0}h2{margin:0 0 12px}h3{margin:20px 0 8px}p{line-height:1.8;color:#637187}.notice{padding:13px;border-radius:13px;background:#fff8e6;border:1px solid #f1d48b;color:#72540a}.ok{background:#ecfdf5;border-color:#a7f3d0;color:#065f46}
.flow,.docs,.kpis,.charts,.cols{display:grid;gap:10px}.flow{grid-template-columns:repeat(6,1fr)}.step,.doc,.kpi,.panel,.chart{border:1px solid #dce5ee;border-radius:15px;padding:14px;background:#fbfdff}.step{text-align:center;font-size:12px}.step b{display:block;font-size:18px}.docs{grid-template-columns:repeat(4,1fr)}.kpis{grid-template-columns:repeat(4,1fr)}.kpi span{font-size:12px;color:#697688}.kpi b{display:block;font-size:23px;margin-top:5px}.charts,.cols{grid-template-columns:1fr 1fr}.chart svg{width:100%;min-width:400px}.line{fill:none;stroke:#0f766e;stroke-width:4}.chart circle{fill:#0f766e}.chart text{font-size:10px;fill:#64748b}
.drop{border:2px dashed #9dadbd;border-radius:18px;padding:26px;text-align:center;background:#f8fafc}input,select{width:100%;padding:12px;background:#fff;border:1px solid #cbd6e2;border-radius:12px}.formgrid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.field label{display:block;font-size:12px;color:#697688;margin:0 0 5px}.btn{border:0;border-radius:12px;padding:13px 18px;background:#087d73;color:#fff;font-weight:900}.decision{padding:17px;border-radius:15px;font-weight:950;font-size:18px}.red{background:#fee2e2;color:#8b1b1b}.amber{background:#fef3c7;color:#7c4a05}.green{background:#dcfce7;color:#14532d}.tbl{overflow:auto}table{width:100%;border-collapse:collapse;min-width:720px;font-size:12px}th,td{padding:9px;border-bottom:1px solid #e5ebf1;text-align:right}th{background:#f8fafc}ul{line-height:1.9}
@media(max-width:760px){.flow{grid-template-columns:repeat(3,1fr)}.docs,.kpis,.charts,.cols,.formgrid{grid-template-columns:1fr 1fr}h1{font-size:26px}}@media(max-width:520px){.docs,.kpis,.charts,.cols,.formgrid{grid-template-columns:1fr}.flow{grid-template-columns:repeat(2,1fr)}.hero,.sec{padding:17px}}'''

def shell(body):
    return f'<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>AI Credit Analysis V5.1</title><style>{CSS}</style></head><body><header><div class="top"><div class="brand">AI Credit Analysis<small>Document Intelligence • Corporate Underwriting • Explainable Decision Support</small></div><div class="ver">V5.1 • Offline Core</div></div></header><main class="wrap">{body}</main></body></html>'

@app.get("/",response_class=HTMLResponse)
def home():
    return shell('''<section class="card hero"><div class="eye">DOCUMENT-FIRST CREDIT UNDERWRITING</div><h1>تحليل ائتماني يعمل بدون اشتراك API</h1><p>قراءة محلية للملفات، حسابات مصرفية قابلة للتدقيق، رسوم، فحوص اتساق، Stress Testing ومذكرة ائتمانية إرشادية.</p><div class="notice ok">لا يحتاج OPENAI_API_KEY للتشغيل.</div></section>
<section class="card sec"><div class="flow"><div class="step"><b>01</b>رفع</div><div class="step"><b>02</b>Extract</div><div class="step"><b>03</b>Reconcile</div><div class="step"><b>04</b>Ratios</div><div class="step"><b>05</b>Stress</div><div class="step"><b>06</b>Memo</div></div></section>
<section class="card sec"><h2>رفع ملف العميل</h2><form method="post" action="/underwrite" enctype="multipart/form-data"><div class="drop"><input type="file" name="files" multiple required accept=".pdf,.xlsx,.xlsm,.docx,.csv,.txt"><p>أفضل دقة: Excel/CSV، ثم PDF النصي وWord. PDF المصور يحتاج OCR لاحقاً.</p></div><h3>بيانات التسهيل المكملة</h3><div class="formgrid">
<div class="field"><label>اسم العميل</label><input name="company_name"></div><div class="field"><label>مبلغ التمويل</label><input name="requested_amount" type="number" step="any" value="0"></div><div class="field"><label>المدة بالأشهر</label><input name="tenor_months" type="number" value="12"></div>
<div class="field"><label>العائد السنوي %</label><input name="annual_rate" type="number" step="any" value="0"></div><div class="field"><label>خدمة الدين القائمة</label><input name="existing_annual_debt_service" type="number" step="any" value="0"></div><div class="field"><label>قيمة الضمان المحتسبة</label><input name="collateral_value" type="number" step="any" value="0"></div>
<div class="field"><label>أيام التأخر</label><input name="dpd" type="number" value="0"></div><div class="field"><label>تعثر قائم؟</label><select name="default_flag"><option value="0">لا</option><option value="1">نعم</option></select></div><div class="field"><label>التقييم النوعي 0-100</label><input name="qualitative_score" type="number" value="50"></div>
</div><p><button class="btn">تشغيل التحليل الائتماني</button></p></form></section>''')

@app.post("/underwrite",response_class=HTMLResponse)
async def underwrite(files:List[UploadFile]=File(...),company_name:str=Form(""),requested_amount:float=Form(0),tenor_months:float=Form(12),annual_rate:float=Form(0),existing_annual_debt_service:float=Form(0),collateral_value:float=Form(0),dpd:float=Form(0),default_flag:int=Form(0),qualitative_score:float=Form(50)):
    sets=[];ev=[];docs=[];total=0
    for f in files[:25]:
        data=await f.read();total+=len(data);name=f.filename or "document";ext=os.path.splitext(name.lower())[1]
        if len(data)>MAX_FILE_MB*1024*1024 or total>MAX_TOTAL_MB*1024*1024:return HTMLResponse(shell('<section class="card sec"><h2>حجم الملفات يتجاوز الحد المسموح.</h2></section>'),413)
        ps={};e=[]
        if ext in (".xlsx",".xlsm"):ps,e=extract_xlsx(data,name)
        elif ext==".csv":ps,e=extract_csv(data,name)
        elif ext==".pdf":ps,e=extract_text(pdf_text(data),name)
        elif ext==".docx":ps,e=extract_text(docx_text(data),name)
        elif ext==".txt":
            text=""
            for enc in ("utf-8-sig","utf-8","cp1256","latin-1"):
                try:text=data.decode(enc);break
                except:pass
            ps,e=extract_text(text,name)
        sets.append(ps);ev+=e;docs.append((name,len(data),len(e)))
    periods=finalize(merge(sets));E=engine(periods,requested_amount,tenor_months,annual_rate,existing_annual_debt_service,collateral_value,dpd,bool(default_flag),qualitative_score);m=E["m"];issues=consistency(periods)
    doccards="".join(f'<div class="doc"><b>{h(a)}</b><br><small>{b/1024:.0f} KB • {c} قيم مستخرجة</small></div>' for a,b,c in docs)
    kpairs=[("التقييم",f'{E["score"]:.0f}/100'),("المخاطر",f'{E["grade"]} — {E["risk"]}'),("DSCR",rx(E["dscr"])),("الحد الإرشادي",money(E["limit"])),("Current Ratio",rx(m["cr"])),("Quick Ratio",rx(m["qr"])),("Debt/Equity",rx(m["de"])),("Interest Cover",rx(m["ic"])),("EBITDA Margin",pct(m["em"])),("CFO Margin",pct(m["cfom"])),("DSO",f'{m["dso"]:.0f} يوم'),("دورة النقد",f'{m["dso"]+m["dio"]-m["dpo"]:.0f} يوم')]
    kp="".join(f'<div class="kpi"><span>{a}</span><b>{b}</b></div>' for a,b in kpairs)
    rows="".join(f'<tr><td>{h(x["period"])}</td><td>{money(x["revenue"])}</td><td>{money(x["ebitda"])}</td><td>{money(x["net_profit"])}</td><td>{money(x["cfo"])}</td><td>{money(x["total_assets"])}</td><td>{money(x["total_debt"])}</td><td>{money(x["equity"])}</td><td>{rx(metrics(x)["cr"])}</td><td>{rx(metrics(x)["de"])}</td></tr>' for x in periods)
    sc="".join(f'<tr><td>{a}</td><td>{rx(b)}</td><td>{"مقبول" if b>=1.25 else "حساس" if b>=1 else "غير مغطى"}</td></tr>' for a,b in E["sc"])
    evid="".join(f'<tr><td>{h(x["field"])}</td><td>{money(x["value"])}</td><td>{h(x["file"])}</td><td>{h(x["where"])}</td><td>{x["confidence"]*100:.0f}%</td></tr>' for x in ev[:200])
    li=lambda xs,fb="لا توجد":"".join(f"<li>{h(x)}</li>" for x in xs) if xs else f"<li>{fb}</li>"
    risks=[]
    if E["dscr"]<1.25:risks.append(f'DSCR عند {E["dscr"]:.2f}x يحتاج معالجة.')
    if m["de"]>3:risks.append(f'Debt/Equity عند {m["de"]:.2f}x مرتفع.')
    risks+=issues
    strengths=[]
    if E["dscr"]>=1.25:strengths.append(f'DSCR عند {E["dscr"]:.2f}x.')
    if m["cr"]>=1.2:strengths.append(f'Current Ratio عند {m["cr"]:.2f}x.')
    body=f'''<section class="card hero"><div class="eye">CREDIT MEMORANDUM • HUMAN REVIEW REQUIRED</div><h1>{h(company_name or "العميل")}</h1><div class="decision {E["color"]}">{h(E["decision"])}</div></section>
<section class="card sec"><h2>المستندات</h2><div class="docs">{doccards}</div></section><section class="card sec"><h2>لوحة القرار</h2><div class="kpis">{kp}</div></section>
<section class="card sec"><h2>الاتجاهات</h2><div class="charts">{chart(periods,"revenue","الإيرادات")}{chart(periods,"ebitda","EBITDA")}{chart(periods,"cfo","التدفق التشغيلي")}{chart(periods,"total_debt","إجمالي الدين")}</div></section>
<section class="card sec"><h2>Financial Spreading</h2><div class="tbl"><table><tr><th>الفترة</th><th>الإيرادات</th><th>EBITDA</th><th>صافي الربح</th><th>CFO</th><th>الأصول</th><th>الدين</th><th>حقوق الملكية</th><th>Current</th><th>D/E</th></tr>{rows}</table></div></section>
<section class="card sec"><div class="cols"><div class="panel"><h2>هيكلة التسهيل</h2><p>قيد التدفق: <b>{money(E["cashlim"])}</b></p><p>قيد الرافعة: <b>{money(E["levlim"])}</b></p><p>قيد الضمان: <b>{money(E["colllim"])}</b></p><p>الحد الإرشادي: <b>{money(E["limit"])}</b></p></div><div class="panel"><h2>فحوص الاتساق</h2><ul>{li(issues,"لم تظهر فروقات اتساق جوهرية ضمن البيانات المستخرجة.")}</ul></div></div></section>
<section class="card sec"><h2>Stress Testing</h2><div class="tbl"><table><tr><th>السيناريو</th><th>DSCR</th><th>الحالة</th></tr>{sc}</table></div></section>
<section class="card sec"><div class="cols"><div class="panel"><h2>نقاط القوة</h2><ul>{li(strengths)}</ul></div><div class="panel"><h2>المخاطر</h2><ul>{li(risks)}</ul></div></div></section>
<section class="card sec"><h2>IFRS 9 — مؤشرات إرشادية</h2><div class="kpis"><div class="kpi"><span>Stage</span><b>{E["stage"]}</b></div><div class="kpi"><span>PD proxy</span><b>{pct(E["pd"])}</b></div><div class="kpi"><span>LGD proxy</span><b>{pct(E["lgd"])}</b></div><div class="kpi"><span>ECL indicative</span><b>{money(E["ecl"])}</b></div></div></section>
<section class="card sec"><h2>الشروط والإنذار المبكر</h2><div class="cols"><div class="panel"><h3>شروط مقترحة</h3><ul><li>استكمال KYC/AML والمستندات القانونية.</li><li>تحديث القوائم وكشوف الحساب والالتزامات قبل الصرف.</li><li>الحفاظ على DSCR لا يقل عن 1.25x.</li></ul></div><div class="panel"><h3>Early Warning</h3><ul><li>تراجع المبيعات أو EBITDA.</li><li>تحول CFO للسالب.</li><li>ارتفاع DSO أو تراكم المخزون.</li><li>ظهور تأخر بالسداد.</li></ul></div></div></section>
<section class="card sec"><h2>Audit Trail — مصدر الأرقام</h2><div class="tbl"><table><tr><th>الحقل</th><th>القيمة</th><th>الملف</th><th>الموقع</th><th>الثقة</th></tr>{evid}</table></div></section>'''
    return shell(body)

@app.get("/health")
def health():return {"status":"ok","version":"5.1.0","mode":"offline-core","openai_required":False}
