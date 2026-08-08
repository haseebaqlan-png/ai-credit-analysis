
from fastapi import FastAPI, Request, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from typing import List
import io, os, re, html, json, math, csv
from datetime import datetime

app = FastAPI(
    title="AI Credit Analysis",
    version="4.0.0",
    description="Document-first corporate credit underwriting and decision-support platform"
)

# -------------------- Utilities --------------------

def safe_div(a, b, default=0.0):
    try:
        b=float(b)
        return default if b == 0 else float(a)/b
    except Exception:
        return default

def clamp(v, lo=0.0, hi=100.0):
    try:
        return max(lo, min(hi, float(v)))
    except Exception:
        return lo

def money(v):
    try:
        return f"{float(v):,.0f}"
    except Exception:
        return "-"

def pct(v, d=1):
    try:
        return f"{float(v)*100:.{d}f}%"
    except Exception:
        return "-"

def ratio(v, d=2):
    try:
        return f"{float(v):.{d}f}x"
    except Exception:
        return "-"

def as_float(form, key, default=0.0):
    try:
        x=form.get(key, default)
        if x in (None, ""): return float(default)
        s=str(x).replace(",","").replace("٬","").replace(" ","")
        return float(s)
    except Exception:
        return float(default)

def yes(form, key):
    return str(form.get(key,"")).lower() in {"1","true","yes","on","نعم"}

def clean_text(s):
    return re.sub(r"\s+"," ", str(s or "")).strip()

def numeric(v):
    if isinstance(v,(int,float)) and not isinstance(v,bool):
        return float(v)
    if isinstance(v,str):
        s=v.replace(",","").replace("٬","").replace("%","").strip()
        if re.fullmatch(r"-?\d+(?:\.\d+)?",s):
            try: return float(s)
            except: return None
    return None

def confidence_badge(c):
    if c >= .90: return "high"
    if c >= .70: return "medium"
    return "low"

# -------------------- Document extraction --------------------

FIELD_SYNONYMS = {
    "borrower_name":["اسم الشركة","اسم العميل","اسم المنشأة","company name","borrower name"],
    "sector":["النشاط","القطاع","طبيعة النشاط","business activity","sector"],
    "revenue":["صافي المبيعات","المبيعات","الإيرادات","sales / revenues","sales","revenue"],
    "gross_profit":["مجمل الربح","إجمالي الربح","gross profit"],
    "net_income":["صافي الربح","net income","net profit"],
    "ebitda":["ebitda"],
    "cash":["النقد","النقدية","الأموال الجاهزة","cash"],
    "receivables":["ذمم مدينة","المدينون","accounts receivable","receivables"],
    "inventory":["المخزون","inventory"],
    "current_assets":["إجمالي الموجودات المتداولة","إجمالي الأصول المتداولة","total current assets","current assets"],
    "total_assets":["إجمالي الموجودات","إجمالي الأصول","total assets"],
    "payables":["ذمم دائنة","الدائنون","accounts payable","payables"],
    "current_liabilities":["إجمالي المطلوبات المتداولة","إجمالي الالتزامات المتداولة","total current liabilities","current liabilities"],
    "total_liabilities":["إجمالي المطلوبات","إجمالي الالتزامات","total liabilities"],
    "equity":["إجمالي حقوق الملكية","حقوق الملكية","tangible net worth","equity"],
    "cfo":["التدفقات النقدية التشغيلية","التدفق النقدي من العمليات","cash flow from operations","operating cash flow"],
    "interest_expense":["تكلفة التمويل","مصروف الفوائد","interest expense","finance cost"],
    "existing_debt_service":["خدمة الدين القائمة","existing debt service"],
    "requested_amount":["مبلغ الائتمان المطلوب","مبلغ التمويل المطلوب","الائتمان المطلوب","requested amount","facility amount"],
    "collateral_market":["القيمة السوقية","قيمة الضمان قبل التحفظ","market value","collateral value"],
}

LABELS = {
    "borrower_name":"اسم العميل/الشركة","sector":"النشاط/القطاع",
    "revenue":"الإيرادات/المبيعات","gross_profit":"مجمل الربح","net_income":"صافي الربح","ebitda":"EBITDA",
    "cash":"النقدية","receivables":"الذمم المدينة","inventory":"المخزون","current_assets":"الأصول المتداولة",
    "total_assets":"إجمالي الأصول","payables":"الذمم الدائنة","current_liabilities":"الالتزامات المتداولة",
    "total_liabilities":"إجمالي الالتزامات","equity":"حقوق الملكية","cfo":"التدفق النقدي التشغيلي",
    "interest_expense":"تكلفة/فوائد التمويل","existing_debt_service":"خدمة الدين القائمة",
    "requested_amount":"مبلغ التمويل المطلوب","collateral_market":"القيمة السوقية للضمان"
}

def synonym_hit(text):
    t=clean_text(text).lower()
    best=None
    for key, syns in FIELD_SYNONYMS.items():
        for s in syns:
            ss=s.lower()
            if ss in t:
                score = len(ss)/max(len(t),1)
                if best is None or score > best[2]:
                    best=(key,s,score)
    return best

def extract_spreadsheet(data: bytes, filename: str):
    from openpyxl import load_workbook
    wb=load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    observations=[]
    snippets=[]
    for ws in wb.worksheets:
        max_rows=min(ws.max_row or 0, 500)
        max_cols=min(ws.max_column or 0, 60)
        for r in range(1,max_rows+1):
            vals=[]
            for c in range(1,max_cols+1):
                v=ws.cell(r,c).value
                if v not in (None,""):
                    vals.append((c,v))
            if not vals: continue
            row_text=" | ".join(clean_text(v) for _,v in vals)
            snippets.append({"loc":f"{ws.title}!R{r}","text":row_text[:1500]})
            for idx,(c,v) in enumerate(vals):
                if not isinstance(v,str): continue
                hit=synonym_hit(v)
                if not hit: continue
                key=hit[0]
                # Look to the right first, then anywhere in same row.
                candidates=[]
                for c2,v2 in vals:
                    nv=numeric(v2)
                    if nv is not None and c2>c:
                        candidates.append((c2,nv))
                if key in ("borrower_name","sector"):
                    txt_candidates=[(c2,clean_text(v2)) for c2,v2 in vals if c2>c and isinstance(v2,str) and clean_text(v2)]
                    if txt_candidates:
                        c2,val=txt_candidates[0]
                        observations.append({"field":key,"value":val,"source":filename,"location":f"{ws.title}!{ws.cell(r,c2).coordinate}","confidence":.94})
                elif candidates:
                    c2,val=candidates[0]
                    observations.append({"field":key,"value":val,"source":filename,"location":f"{ws.title}!{ws.cell(r,c2).coordinate}","confidence":.93})
    return observations, snippets

def extract_pdf(data: bytes, filename: str):
    from pypdf import PdfReader
    reader=PdfReader(io.BytesIO(data))
    observations=[]; snippets=[]
    for pno,page in enumerate(reader.pages[:250],start=1):
        text=page.extract_text() or ""
        for ln,line in enumerate(text.splitlines(),start=1):
            line=clean_text(line)
            if not line: continue
            snippets.append({"loc":f"page {pno}, line {ln}","text":line[:1200]})
            hit=synonym_hit(line)
            if not hit: continue
            key=hit[0]
            if key in ("borrower_name","sector"):
                for sep in [":","-","–"]:
                    if sep in line:
                        after=clean_text(line.split(sep,1)[1])
                        if after and not numeric(after):
                            observations.append({"field":key,"value":after,"source":filename,"location":f"page {pno}","confidence":.77})
                            break
            else:
                nums=re.findall(r"(?<!\d)-?\d[\d,٬]*(?:\.\d+)?",line)
                if nums:
                    try:
                        val=float(nums[-1].replace(",","").replace("٬",""))
                        observations.append({"field":key,"value":val,"source":filename,"location":f"page {pno}","confidence":.76})
                    except: pass
    return observations,snippets

def extract_docx(data: bytes, filename: str):
    from docx import Document
    doc=Document(io.BytesIO(data))
    observations=[]; snippets=[]
    lines=[p.text for p in doc.paragraphs]
    for tbl in doc.tables:
        for row in tbl.rows:
            lines.append(" | ".join(c.text for c in row.cells))
    for i,line in enumerate(lines,start=1):
        line=clean_text(line)
        if not line: continue
        snippets.append({"loc":f"block {i}","text":line[:1200]})
        hit=synonym_hit(line)
        if not hit: continue
        key=hit[0]
        if key not in ("borrower_name","sector"):
            nums=re.findall(r"(?<!\d)-?\d[\d,٬]*(?:\.\d+)?",line)
            if nums:
                try:
                    val=float(nums[-1].replace(",","").replace("٬",""))
                    observations.append({"field":key,"value":val,"source":filename,"location":f"block {i}","confidence":.72})
                except: pass
    return observations,snippets

def extract_textlike(data: bytes, filename: str):
    text=None
    for enc in ("utf-8-sig","utf-8","cp1256","latin-1"):
        try:
            text=data.decode(enc); break
        except: pass
    text=text or ""
    observations=[]; snippets=[]
    for i,line in enumerate(text.splitlines(),start=1):
        line=clean_text(line)
        if not line: continue
        snippets.append({"loc":f"line {i}","text":line[:1200]})
        hit=synonym_hit(line)
        if not hit: continue
        key=hit[0]
        if key not in ("borrower_name","sector"):
            nums=re.findall(r"(?<!\d)-?\d[\d,٬]*(?:\.\d+)?",line)
            if nums:
                try:
                    observations.append({"field":key,"value":float(nums[-1].replace(",","").replace("٬","")),"source":filename,"location":f"line {i}","confidence":.68})
                except: pass
    return observations,snippets

def classify_document(filename, text_sample):
    t=(filename+" "+text_sample).lower()
    classes=[
        ("قوائم مالية",["قوائم","ميزانية","financial","balance sheet","income statement"]),
        ("تدفقات نقدية",["تدفقات","cash flow"]),
        ("طلب تمويل/تسهيل",["طلب","تسهيل","ائتمان","facility","loan request"]),
        ("ضمانات",["ضمان","رهن","عقار","collateral","guarantee"]),
        ("كشف حساب",["كشف حساب","bank statement"]),
        ("وثائق قانونية",["سجل تجاري","عقد تأسيس","ترخيص","legal"]),
        ("استعلام ائتماني",["مركزية المخاطر","bureau","credit report"]),
    ]
    for name,words in classes:
        if any(w in t for w in words): return name
    return "مستند داعم"

def merge_observations(obs):
    # Prefer higher-confidence evidence and retain full audit trail.
    merged={}
    trace={}
    for o in obs:
        k=o["field"]
        trace.setdefault(k,[]).append(o)
        cur=merged.get(k)
        if cur is None or o["confidence"]>cur["confidence"]:
            merged[k]=o
    return merged,trace

# -------------------- Credit engine --------------------

def rating_band(score):
    for floor,grade,label,risk in [
        (90,"1","ممتاز","منخفضة جداً"),(82,"2","قوي جداً","منخفضة"),
        (74,"3","قوي","متوسطة-منخفضة"),(66,"4","جيد","متوسطة"),
        (58,"5","مقبول بحذر","متوسطة-مرتفعة"),(50,"6","ضعيف نسبياً","مرتفعة"),
        (40,"7","ضعيف","مرتفعة جداً"),(0,"8","حرج","حرجة")]:
        if score>=floor: return grade,label,risk
    return "8","حرج","حرجة"

def pd_proxy(score):
    for floor,p in [(90,.005),(82,.01),(74,.02),(66,.04),(58,.075),(50,.13),(40,.22),(0,.35)]:
        if score>=floor:return p
    return .35

def linear(v,bad,good,higher=True):
    if good==bad:return 50
    raw=(v-bad)/(good-bad)*100 if higher else (bad-v)/(bad-good)*100
    return clamp(raw)

def analyze_credit(d):
    rev=d["revenue"]; gp=d["gross_profit"]; ni=d["net_income"]; ebitda=d["ebitda"]
    cash=d["cash"]; ar=d["receivables"]; inv=d["inventory"]; ca=d["current_assets"]; ta=d["total_assets"]
    ap=d["payables"]; cl=d["current_liabilities"]; tl=d["total_liabilities"]; eq=d["equity"]
    cfo=d["cfo"]; interest=d["interest_expense"]; request=d["requested_amount"]
    existing_ds=d["existing_debt_service"]; tenor=max(d["tenor_months"],1); rate=max(d["profit_rate"],0)
    collateral=d["collateral_market"]*(1-clamp(d["collateral_haircut"],0,95)/100) if d["collateral_legal"] else 0

    cogs=max(rev-gp,0)
    gross_margin=safe_div(gp,rev); net_margin=safe_div(ni,rev); ebitda_margin=safe_div(ebitda,rev)
    current_ratio=safe_div(ca,cl,99); quick_ratio=safe_div(ca-inv,cl,0)
    leverage=safe_div(tl,eq,99); debt_assets=safe_div(tl,ta,99)
    interest_cover=safe_div(ebitda,interest,99 if ebitda>0 else 0)
    dso=safe_div(ar,rev)*365
    dio=safe_div(inv,cogs)*365 if cogs else 0
    dpo=safe_div(ap,cogs)*365 if cogs else 0
    wc_days=max(dso+dio-dpo,0)
    gross_wc_need=cogs/365*wc_days if cogs else 0
    nwc=ca-cl
    external_wc=max(gross_wc_need-max(nwc,0),0)
    years=max(tenor/12,1)
    proposed_service=request/years + request*rate
    total_ds=existing_ds+proposed_service
    dscr=safe_div(cfo,total_ds,99 if cfo>0 else 0)
    proforma_lev=safe_div(tl+request,eq,99)
    coll_cov=safe_div(collateral,request,0)
    request_assets=safe_div(request,ta,99)

    financial = (
        linear(gross_margin,.03,.20)*.08 +
        linear(net_margin,0,.10)*.08 +
        linear(current_ratio,.8,1.8)*.08 +
        linear(quick_ratio,.05,1.0)*.06 +
        linear(leverage,4,.8,False)*.12 +
        linear(interest_cover,1,4)*.10 +
        linear(dscr,.8,1.75)*.25 +
        (100 if cfo>0 else 0)*.08 +
        linear(wc_days,120,20,False)*.07 +
        linear(safe_div(eq,max(ta-ca,1)),.5,1.5)*.08
    )
    qualitative=(
        clamp(d["repayment_score"])*.25 +
        linear(d["management_score"],1,5)*.18 +
        linear(d["governance_score"],1,5)*.12 +
        linear(d["market_score"],1,5)*.15 +
        (100 if d["audited_fs"] else 45)*.10 +
        (100 if d["bureau_regular"] else 30)*.10 +
        (100 if not d["legal_cases"] else 20)*.10
    )
    data_quality=clamp(d["data_quality"])
    score=round(financial*.55+qualitative*.35+data_quality*.10,1)
    grade,label,risk=rating_band(score)

    severe=[]; exceptions=[]; mitigants=[]
    if d["days_past_due"]>=90 or d["default_flag"]:
        severe.append("وجود مؤشر تعثر/تأخر 90 يوماً أو أكثر؛ يتطلب تصنيفاً ومراجعة متخصصة.")
    elif d["days_past_due"]>30:
        exceptions.append("تأخر يتجاوز 30 يوماً؛ يتطلب تقييم الزيادة الجوهرية في مخاطر الائتمان.")
    if dscr<1.0: severe.append(f"DSCR بعد التمويل {dscr:.2f}x أقل من 1.00x.")
    elif dscr<1.25: exceptions.append(f"DSCR بعد التمويل {dscr:.2f}x دون المستوى الإرشادي 1.25x.")
    if proforma_lev>3: exceptions.append(f"الرافعة المتوقعة بعد التمويل {proforma_lev:.2f}x مرتفعة.")
    if quick_ratio<.5: exceptions.append(f"السيولة السريعة {quick_ratio:.2f}x منخفضة.")
    if request_assets>.5: exceptions.append(f"الطلب يعادل {request_assets*100:.1f}% من إجمالي الأصول.")
    if external_wc>0 and request>external_wc*1.25:
        exceptions.append("قيمة التمويل تتجاوز الاحتياج الخارجي المحسوب لرأس المال العامل بأكثر من 25%.")
    if not d["collateral_legal"] and request>0:
        exceptions.append("قابلية تنفيذ الضمان قانونياً لم تُثبت.")
    elif coll_cov<1:
        exceptions.append(f"تغطية الضمان بعد التحفظ {coll_cov:.2f}x أقل من 1.00x.")
    if data_quality<70: exceptions.append(f"جودة البيانات {data_quality:.0f}/100؛ يلزم استكمال/مراجعة المستندات.")

    if cfo>0: mitigants.append("التدفق النقدي التشغيلي موجب.")
    if current_ratio>=1.2: mitigants.append("نسبة التداول داعمة.")
    if d["bureau_regular"]: mitigants.append("السلوك الائتماني الخارجي منتظم وفق البيانات المتاحة.")
    if coll_cov>=1.2 and d["collateral_legal"]: mitigants.append("تغطية ضمان جيدة بعد التحفظ وقابلية تنفيذ مثبتة.")
    if not mitigants: mitigants.append("لم تُثبت عوامل تخفيف كافية من البيانات الحالية.")

    target_dscr=1.25
    available_service=max(cfo/target_dscr-existing_ds,0)
    service_factor=(1/years)+rate
    cashflow_limit=max(available_service/max(service_factor,.01),0)
    leverage_limit=max(3*eq-tl,0)
    collateral_limit=collateral/1.20 if collateral>0 else request
    wc_limit=external_wc if external_wc>0 else request
    recommended=max(0,min(request,cashflow_limit,leverage_limit,collateral_limit,wc_limit))

    if severe:
        decision="لا يوصى بالموافقة بالشكل الحالي"
        cls="decline"
    elif score>=74 and dscr>=1.25 and data_quality>=75 and len(exceptions)<=2:
        decision="مؤهل للموافقة المشروطة ضمن الصلاحيات والسياسات"
        cls="approve"
    elif score>=58 and dscr>=1.0:
        decision="مراجعة/إعادة هيكلة قبل العرض على اللجنة"
        cls="review"
    else:
        decision="مخاطر مرتفعة — إعادة هيكلة جوهرية أو عدم الموافقة"
        cls="decline"

    # IFRS 9 decision-support indicators (not regulatory/calibrated estimates)
    if d["days_past_due"]>=90 or d["default_flag"]:
        stage="Stage 3"
    elif d["days_past_due"]>30 or d["sicr_flag"]:
        stage="Stage 2"
    else:
        stage="Stage 1"
    pd12=pd_proxy(score)
    weighted_pd=1.0 if stage=="Stage 3" else min(pd12*(2.0 if stage=="Stage 2" else 1.0),1)
    ead=request
    recoverable=min(collateral*.85,ead) if d["collateral_legal"] else 0
    lgd=clamp((1-safe_div(recoverable,ead))*100,10,90)/100 if ead>0 else 0
    ecl=ead*weighted_pd*lgd

    scenarios=[]
    for name, rev_s, cfo_s, wc_add in [
        ("الأساسي",0,0,0),("ضغط متوسط",-0.15,-0.25,20),("ضغط شديد",-0.30,-0.45,45)]:
        s_cfo=cfo*(1+cfo_s)
        s_dscr=safe_div(s_cfo,total_ds,0)
        s_wc=max(cogs*(1+rev_s)/365*(wc_days+wc_add)-max(nwc,0),0) if cogs else 0
        scenarios.append((name,s_dscr,s_wc,"مريح" if s_dscr>=1.25 else "حساس" if s_dscr>=1 else "غير مغطى"))

    return {
        "score":score,"grade":grade,"label":label,"risk":risk,"decision":decision,"decision_class":cls,
        "financial":financial,"qualitative":qualitative,"data_quality":data_quality,
        "gross_margin":gross_margin,"net_margin":net_margin,"ebitda_margin":ebitda_margin,
        "current_ratio":current_ratio,"quick_ratio":quick_ratio,"leverage":leverage,"debt_assets":debt_assets,
        "interest_cover":interest_cover,"dso":dso,"dio":dio,"dpo":dpo,"wc_days":wc_days,
        "gross_wc_need":gross_wc_need,"nwc":nwc,"external_wc":external_wc,"dscr":dscr,
        "proforma_leverage":proforma_lev,"collateral_adjusted":collateral,"coll_cov":coll_cov,
        "cashflow_limit":cashflow_limit,"leverage_limit":leverage_limit,"collateral_limit":collateral_limit,
        "wc_limit":wc_limit,"recommended_limit":recommended,"exceptions":exceptions,"severe":severe,
        "mitigants":mitigants,"stage":stage,"pd12":pd12,"lgd":lgd,"ead":ead,"ecl":ecl,"scenarios":scenarios
    }

# -------------------- UI --------------------

STYLE = """
*{box-sizing:border-box}body{margin:0;background:#f3f6fb;color:#13233b;font-family:system-ui,-apple-system,'Segoe UI',Arial,sans-serif}
header{background:linear-gradient(135deg,#071a36,#164f79);color:#fff;position:sticky;top:0;z-index:9}
.top,.wrap{max-width:1180px;margin:auto}.top{padding:16px;display:flex;justify-content:space-between;align-items:center;gap:12px}
.brand{font-size:20px;font-weight:950}.brand small{display:block;font-size:11px;color:#c9d7e7;font-weight:600}
.ver{border:1px solid #ffffff30;background:#ffffff12;border-radius:999px;padding:8px 11px;font-size:12px}
.wrap{padding:20px 13px 60px}.card{background:#fff;border:1px solid #dfe7f0;border-radius:20px;box-shadow:0 12px 35px #0b1d3410;margin-bottom:14px}
.hero{padding:26px;background:linear-gradient(135deg,#fff 55%,#eafbf8)}.kicker{font-size:12px;color:#09897f;font-weight:900;letter-spacing:.6px}
h1{font-size:30px;margin:8px 0}h2{margin:0 0 10px}p{line-height:1.8;color:#64748b}
.security{padding:12px 14px;border-radius:13px;background:#f0f9ff;border:1px solid #bae6fd;color:#075985;font-size:13px;line-height:1.7}
.upload{padding:22px}.drop{border:2px dashed #a9b8c8;border-radius:18px;padding:28px;text-align:center;background:#f8fafc}
input[type=file]{width:100%;padding:12px;background:#fff;border:1px solid #d7e0ea;border-radius:12px}.btn{border:0;border-radius:12px;padding:13px 18px;font-weight:900;cursor:pointer}
.pri{background:#102b4e;color:white}.go{background:#087f73;color:white}.alt{background:#e9eff6;color:#203652}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.field{display:flex;flex-direction:column;gap:5px}
label{font-weight:800;font-size:13px}input,select,textarea{font:inherit;border:1px solid #cfdae6;border-radius:11px;padding:11px 12px;background:#fff}
small.help{color:#7b8798}.section{padding:20px}.toolbar{display:flex;gap:9px;justify-content:flex-end;flex-wrap:wrap}
.docs{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}.doc{border:1px solid #dfe7ef;padding:13px;border-radius:14px;background:#fbfdff}
.doc b{display:block}.tag{display:inline-block;margin-top:6px;padding:4px 7px;border-radius:999px;background:#edf2f7;font-size:11px}
.table{width:100%;border-collapse:collapse;font-size:12px}.table th,.table td{padding:9px;border-bottom:1px solid #e5ebf2;text-align:right;vertical-align:top}.table th{background:#f8fafc}
.badge{padding:4px 8px;border-radius:999px;font-size:11px;font-weight:900}.high{background:#dcfce7;color:#166534}.medium{background:#fef3c7;color:#92400e}.low{background:#fee2e2;color:#991b1b}
.kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}.kpi{padding:14px;border-radius:15px;background:#f8fafc;border:1px solid #e2e8f0}.kpi b{display:block;font-size:22px;margin-top:5px}
.decision{padding:18px;border-radius:15px;font-weight:900}.approve{background:#dcfce7;color:#14532d}.review{background:#fef3c7;color:#78350f}.decline{background:#fee2e2;color:#7f1d1d}
.memo{padding:22px}.memo h3{border-bottom:1px solid #e2e8f0;padding-bottom:7px}.list{line-height:1.9}
@media(max-width:760px){.grid,.docs,.kpis{grid-template-columns:1fr}.brand{font-size:17px}h1{font-size:25px}.wrap{padding:14px 10px 45px}.top{padding:13px 10px}}
"""

def shell(body,title="AI Credit Analysis V4"):
    return f"""<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><style>{STYLE}</style></head>
<body><header><div class="top"><div class="brand">AI Credit Analysis<small>Document Intelligence • Corporate Underwriting • Decision Support</small></div><div class="ver">V4 • Document-First</div></div></header>
<main class="wrap">{body}</main></body></html>"""

@app.get("/",response_class=HTMLResponse)
def home():
    body="""
    <section class="card hero">
      <div class="kicker">DOCUMENT-FIRST CREDIT UNDERWRITING</div>
      <h1>من المستندات إلى مذكرة ائتمانية متكاملة</h1>
      <p>ارفع ملفات العميل، وسيقوم النظام بتصنيفها واستخراج البيانات المالية والائتمانية، ثم يعرضها للمراجعة البشرية قبل إجراء التحليل المالي، اختبار قدرة السداد، تقييم المخاطر، الضمانات، اختبارات الضغط، الحد المقترح، ومذكرة القرار.</p>
      <div class="security"><b>الخصوصية:</b> لا تعرض المنصة أسماء أو بيانات أي حالات مرجعية ضمن واجهتها أو وثائقها العامة. الملفات المرفوعة في هذه النسخة التجريبية تُقرأ داخل طلب التحليل ولا تُحفظ في قاعدة بيانات دائمة. يجب تطبيق سياسات البنك للأمن والاحتفاظ بالبيانات قبل الاستخدام الإنتاجي.</div>
    </section>
    <section class="card upload">
      <h2>1) مركز رفع المستندات</h2>
      <p>يدعم حالياً Excel/XLSM وPDF النصي وWord وCSV/TXT. المستندات المصورة أو PDF الممسوح ضوئياً تُعلّم بأنها تحتاج OCR في طبقة الإنتاج.</p>
      <form method="post" action="/ingest" enctype="multipart/form-data">
        <div class="drop">
          <input type="file" name="files" multiple required accept=".xlsx,.xlsm,.pdf,.docx,.csv,.txt">
          <p>يمكن رفع القوائم المالية، كشف الحساب، طلب التمويل، بيانات التسهيلات، الضمانات، والاستعلامات والوثائق الداعمة دفعة واحدة.</p>
          <button class="btn pri" type="submit">استخراج وفحص المستندات</button>
        </div>
      </form>
    </section>
    <section class="card section">
      <h2>مسار العمل</h2>
      <div class="docs">
        <div class="doc"><b>01 — Ingest</b><span class="tag">تصنيف المستندات</span></div>
        <div class="doc"><b>02 — Extract</b><span class="tag">استخراج الحقول + مصدر كل رقم</span></div>
        <div class="doc"><b>03 — Validate</b><span class="tag">مراجعة بشرية وتسويات</span></div>
        <div class="doc"><b>04 — Analyze</b><span class="tag">نسب + تدفقات + رأس مال عامل</span></div>
        <div class="doc"><b>05 — Risk</b><span class="tag">مخاطر + ضغط + ضمانات</span></div>
        <div class="doc"><b>06 — Memo</b><span class="tag">مذكرة لجنة قابلة للمراجعة</span></div>
      </div>
    </section>
    """
    return shell(body)

@app.post("/ingest",response_class=HTMLResponse)
async def ingest(files: List[UploadFile] = File(...)):
    all_obs=[]; docs=[]; unsupported=[]
    for f in files[:30]:
        data=await f.read()
        name=f.filename or "document"
        ext=os.path.splitext(name.lower())[1]
        obs=[]; snippets=[]
        try:
            if ext in (".xlsx",".xlsm"):
                obs,snippets=extract_spreadsheet(data,name)
            elif ext==".pdf":
                obs,snippets=extract_pdf(data,name)
            elif ext==".docx":
                obs,snippets=extract_docx(data,name)
            elif ext in (".csv",".txt"):
                obs,snippets=extract_textlike(data,name)
            else:
                unsupported.append(name)
        except Exception as e:
            unsupported.append(f"{name} ({type(e).__name__})")
        all_obs.extend(obs)
        sample=" ".join(x["text"] for x in snippets[:20])[:5000]
        docs.append({"name":name,"size":len(data),"type":classify_document(name,sample),"observations":len(obs)})
    merged,trace=merge_observations(all_obs)

    # Build completeness / data quality from extracted fields.
    critical=["revenue","gross_profit","net_income","cash","receivables","inventory","current_assets","total_assets",
              "payables","current_liabilities","total_liabilities","equity","cfo","requested_amount"]
    present=sum(1 for k in critical if k in merged and merged[k].get("value") not in (None,""))
    data_quality=round(present/len(critical)*100,0)

    docs_html="".join(f'<div class="doc"><b>{html.escape(d["name"])}</b><span class="tag">{d["type"]}</span><p>{d["observations"]} حقل/إشارة مستخرجة • {d["size"]/1024:.1f} KB</p></div>' for d in docs)
    if unsupported:
        docs_html += '<div class="doc"><b>ملفات تحتاج معالجة إضافية</b><p>'+html.escape("، ".join(unsupported))+'</p></div>'

    rows=[]
    for k in LABELS:
        o=merged.get(k)
        if o:
            val=o["value"]; src=f'{o["source"]} — {o["location"]}'; conf=o["confidence"]
        else:
            val=""; src="لم يُستخرج تلقائياً"; conf=.35
        typ="text" if k in ("borrower_name","sector") else "number"
        step='step="any"' if typ=="number" else ""
        rows.append(f"""<tr><td><b>{LABELS[k]}</b></td>
        <td><input style="width:100%" type="{typ}" {step} name="{k}" value="{html.escape(str(val))}"></td>
        <td>{html.escape(src)}</td><td><span class="badge {confidence_badge(conf)}">{conf*100:.0f}%</span></td></tr>""")

    body=f"""
    <section class="card hero"><div class="kicker">EXTRACTION REVIEW</div><h1>مراجعة البيانات قبل التحليل</h1>
    <p>لم يعتمد النظام أي رقم نهائياً بعد. عدّل الحقول غير الصحيحة أو أكمل الناقص؛ كل قيمة مستخرجة مرتبطة بمصدرها وثقة الاستخراج.</p></section>
    <section class="card section"><h2>المستندات المصنفة</h2><div class="docs">{docs_html}</div></section>
    <form method="post" action="/analyze">
    <section class="card section"><h2>الحقول المستخرجة</h2>
      <div style="overflow:auto"><table class="table"><thead><tr><th>الحقل</th><th>القيمة القابلة للتعديل</th><th>المصدر</th><th>الثقة</th></tr></thead>
      <tbody>{''.join(rows)}</tbody></table></div>
      <input type="hidden" name="data_quality" value="{data_quality}">
    </section>
    <section class="card section"><h2>بيانات التحليل التي تحتاج قرار المحلل</h2>
      <div class="grid">
       <div class="field"><label>مدة التسهيل (شهر)</label><input type="number" step="any" name="tenor_months" value="12"></div>
       <div class="field"><label>معدل الربح/الفائدة السنوي</label><input type="number" step="any" name="profit_rate" value="0.07"></div>
       <div class="field"><label>خدمة الدين القائمة سنوياً</label><input type="number" step="any" name="existing_debt_service" value="0"></div>
       <div class="field"><label>نسبة التحفظ على الضمان %</label><input type="number" step="any" name="collateral_haircut" value="30"></div>
       <div class="field"><label>سجل السداد 0–100</label><input type="number" step="any" name="repayment_score" value="70"></div>
       <div class="field"><label>جودة الإدارة 1–5</label><input type="number" step="1" min="1" max="5" name="management_score" value="3"></div>
       <div class="field"><label>الحوكمة 1–5</label><input type="number" step="1" min="1" max="5" name="governance_score" value="3"></div>
       <div class="field"><label>وضع السوق والنشاط 1–5</label><input type="number" step="1" min="1" max="5" name="market_score" value="3"></div>
       <div class="field"><label>أيام التأخر الحالية</label><input type="number" name="days_past_due" value="0"></div>
      </div>
      <div class="grid" style="margin-top:15px">
        <label><input type="checkbox" name="audited_fs" checked> القوائم مدققة</label>
        <label><input type="checkbox" name="bureau_regular" checked> الاستعلام الائتماني منتظم</label>
        <label><input type="checkbox" name="collateral_legal"> قابلية تنفيذ الضمان مثبتة قانونياً</label>
        <label><input type="checkbox" name="legal_cases"> توجد قضايا جوهرية</label>
        <label><input type="checkbox" name="sicr_flag"> مؤشر زيادة جوهرية في المخاطر</label>
        <label><input type="checkbox" name="default_flag"> مؤشر تعثر</label>
      </div>
      <div class="toolbar" style="margin-top:18px"><a class="btn alt" href="/">إلغاء</a><button class="btn go" type="submit">تشغيل الدراسة الائتمانية</button></div>
    </section></form>
    """
    return shell(body,"V4 — Extraction Review")

def parse_credit_form(form):
    keys=["revenue","gross_profit","net_income","ebitda","cash","receivables","inventory","current_assets","total_assets",
          "payables","current_liabilities","total_liabilities","equity","cfo","interest_expense","existing_debt_service",
          "requested_amount","collateral_market","collateral_haircut","tenor_months","profit_rate","repayment_score",
          "management_score","governance_score","market_score","days_past_due","data_quality"]
    d={k:as_float(form,k,0) for k in keys}
    d["borrower_name"]=str(form.get("borrower_name","عميل"))
    d["sector"]=str(form.get("sector",""))
    d["audited_fs"]=yes(form,"audited_fs")
    d["bureau_regular"]=yes(form,"bureau_regular")
    d["collateral_legal"]=yes(form,"collateral_legal")
    d["legal_cases"]=yes(form,"legal_cases")
    d["sicr_flag"]=yes(form,"sicr_flag")
    d["default_flag"]=yes(form,"default_flag")
    if d["ebitda"]<=0 and d["net_income"]>0: d["ebitda"]=d["net_income"]
    return d

@app.post("/analyze",response_class=HTMLResponse)
async def analyze(request:Request):
    form=await request.form()
    d=parse_credit_form(form)
    if d["revenue"]<=0 or d["total_assets"]<=0 or d["equity"]<=0 or d["requested_amount"]<=0:
        return HTMLResponse(shell('<section class="card section"><h2>بيانات غير مكتملة</h2><p>يلزم على الأقل: الإيرادات، إجمالي الأصول، حقوق الملكية، ومبلغ التمويل المطلوب.</p><a class="btn pri" href="/">العودة</a></section>'),status_code=400)
    r=analyze_credit(d)
    kpis=[
      ("التقييم",f'{r["score"]:.0f}/100'),("درجة المخاطر",f'{r["grade"]} — {r["risk"]}'),
      ("DSCR",ratio(r["dscr"])),("الحد المقترح",money(r["recommended_limit"])),
      ("نسبة التداول",ratio(r["current_ratio"])),("السيولة السريعة",ratio(r["quick_ratio"])),
      ("الرافعة بعد التمويل",ratio(r["proforma_leverage"])),("تغطية الضمان",ratio(r["coll_cov"])),
    ]
    khtml="".join(f'<div class="kpi"><span>{a}</span><b>{b}</b></div>' for a,b in kpis)
    severe="".join(f"<li>{html.escape(x)}</li>" for x in r["severe"]) or "<li>لا توجد بوابات رفض حادة محددة من البيانات الحالية.</li>"
    exc="".join(f"<li>{html.escape(x)}</li>" for x in r["exceptions"]) or "<li>لا توجد استثناءات جوهرية ظاهرة.</li>"
    mit="".join(f"<li>{html.escape(x)}</li>" for x in r["mitigants"])
    scen="".join(f"<tr><td>{n}</td><td>{ds:.2f}x</td><td>{money(wc)}</td><td>{st}</td></tr>" for n,ds,wc,st in r["scenarios"])
    body=f"""
    <section class="card hero"><div class="kicker">CREDIT MEMORANDUM • DRAFT FOR HUMAN REVIEW</div>
      <h1>{html.escape(d["borrower_name"])}</h1><p>{html.escape(d["sector"] or "قطاع غير محدد")}</p>
      <div class="decision {r["decision_class"]}">{r["decision"]}</div>
    </section>
    <section class="card section"><h2>لوحة القرار</h2><div class="kpis">{khtml}</div></section>
    <section class="card memo">
      <h2>مذكرة الدراسة الائتمانية</h2>
      <h3>1. الملخص التنفيذي</h3>
      <p>درجة التقييم {r["score"]:.1f}/100، وتصنيف المخاطر {r["grade"]} ({r["label"]}). الحد الإرشادي المقترح هو {money(r["recommended_limit"])} مقارنة بطلب {money(d["requested_amount"])}، مع بقاء القرار خاضعاً للصلاحيات والسياسة الائتمانية والتحقق المستقل.</p>

      <h3>2. التحليل المالي وقدرة السداد</h3>
      <div style="overflow:auto"><table class="table">
      <tr><th>هامش مجمل الربح</th><td>{pct(r["gross_margin"])}</td><th>هامش صافي الربح</th><td>{pct(r["net_margin"])}</td></tr>
      <tr><th>نسبة التداول</th><td>{ratio(r["current_ratio"])}</td><th>السيولة السريعة</th><td>{ratio(r["quick_ratio"])}</td></tr>
      <tr><th>الالتزامات/حقوق الملكية</th><td>{ratio(r["leverage"])}</td><th>تغطية الفوائد</th><td>{ratio(r["interest_cover"])}</td></tr>
      <tr><th>DSCR بعد التمويل</th><td>{ratio(r["dscr"])}</td><th>الرافعة بعد التمويل</th><td>{ratio(r["proforma_leverage"])}</td></tr>
      </table></div>

      <h3>3. رأس المال العامل</h3>
      <p>أيام التحصيل {r["dso"]:.1f}، أيام المخزون {r["dio"]:.1f}، أيام الموردين {r["dpo"]:.1f}، ودورة رأس المال العامل {r["wc_days"]:.1f} يوم. الاحتياج الخارجي المحسوب: {money(r["external_wc"])}.</p>

      <h3>4. القدرة على تحديد حجم التمويل</h3>
      <div style="overflow:auto"><table class="table">
      <tr><th>قيد التدفق النقدي</th><td>{money(r["cashflow_limit"])}</td></tr>
      <tr><th>قيد الرافعة المالية</th><td>{money(r["leverage_limit"])}</td></tr>
      <tr><th>قيد الضمان بعد التحفظ</th><td>{money(r["collateral_limit"])}</td></tr>
      <tr><th>قيد رأس المال العامل</th><td>{money(r["wc_limit"])}</td></tr>
      <tr><th>الحد المقترح (الأدنى)</th><td><b>{money(r["recommended_limit"])}</b></td></tr>
      </table></div>

      <h3>5. المخاطر والاستثناءات</h3><ul class="list">{severe}{exc}</ul>
      <h3>6. عوامل التخفيف</h3><ul class="list">{mit}</ul>

      <h3>7. اختبار الضغط</h3>
      <div style="overflow:auto"><table class="table"><thead><tr><th>السيناريو</th><th>DSCR</th><th>احتياج رأس المال العامل</th><th>الحالة</th></tr></thead><tbody>{scen}</tbody></table></div>

      <h3>8. مؤشرات IFRS 9 / ECL — إرشادية</h3>
      <p>{r["stage"]} • PD proxy: {pct(r["pd12"],2)} • LGD proxy: {pct(r["lgd"],1)} • EAD: {money(r["ead"])} • ECL indicative: {money(r["ecl"])}. لا تُستخدم هذه القيم كقياسات رقابية أو محاسبية معتمدة قبل المعايرة والتحقق والحوكمة.</p>

      <h3>9. جودة البيانات والحوكمة</h3>
      <p>درجة اكتمال/جودة البيانات المستخرجة: {r["data_quality"]:.0f}/100. يجب أن تُعتمد القيم النهائية بعد مطابقة المستندات، التسويات، والتحقق من مصدر كل رقم.</p>

      <h3>10. التوصية</h3>
      <div class="decision {r["decision_class"]}">{r["decision"]}<br>الحد الإرشادي: {money(r["recommended_limit"])}</div>
      <p><b>شروط مقترحة:</b> استكمال أي مستندات ناقصة؛ توثيق مصدر السداد؛ توثيق الضمان وقابليته للتنفيذ؛ تحديث التقييمات عند الحاجة؛ مراقبة DSCR ورأس المال العامل والسلوك الائتماني؛ وعدم الاعتماد على الضمان كبديل عن قدرة السداد.</p>
    </section>
    <section class="card section"><div class="toolbar"><a class="btn pri" href="/">دراسة جديدة</a></div></section>
    """
    return shell(body,"V4 — Credit Memorandum")

@app.get("/health")
def health():
    return {"status":"ok","version":"4.0.0","engine":"document-first-credit-underwriting"}

@app.get("/api/capabilities")
def capabilities():
    return {
      "version":"4.0.0",
      "document_ingestion":["xlsx","xlsm","pdf-text","docx","csv","txt"],
      "audit_trail":True,
      "human_review_required":True,
      "credit_modules":["financial spreading","cash-flow/DSCR","working capital","facility sizing","collateral","stress testing","IFRS9 indicators","credit memo"],
      "ocr":"production integration required for scanned/image-only documents"
    }
