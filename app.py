from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
import math, os, html

app = FastAPI(
    title="AI Credit Analysis",
    version="3.0.0",
    description="Explainable corporate credit decision-support platform"
)

def safe_div(a, b, default=0.0):
    try:
        return default if float(b) == 0 else float(a) / float(b)
    except Exception:
        return default

def clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, float(x)))

def linear_score(v, bad, good, higher_is_better=True):
    v=float(v)
    if good == bad:
        return 50.0
    raw = (v-bad)/(good-bad)*100 if higher_is_better else (bad-v)/(bad-good)*100
    return clamp(raw)

def as_float(form, key, default=0.0):
    try:
        v=form.get(key, default)
        return float(v if v not in (None, "") else default)
    except Exception:
        return float(default)

def as_int(form, key, default=0):
    try:
        return int(float(form.get(key, default) or default))
    except Exception:
        return int(default)

def yes(form, key):
    return str(form.get(key, "no")).lower() in ("yes","1","true","نعم")

def money(x):
    try:
        return f"{float(x):,.0f}"
    except Exception:
        return "-"

def pct(x, digits=1):
    try:
        return f"{float(x)*100:.{digits}f}%"
    except Exception:
        return "-"

def ratio(x, digits=2):
    try:
        return f"{float(x):.{digits}f}x"
    except Exception:
        return "-"

def rating_band(score):
    bands=[
        (90,"1","AAA","ممتاز","منخفضة جدًا"),
        (82,"2","AA","قوي جدًا","منخفضة"),
        (74,"3","A","قوي","متوسطة-منخفضة"),
        (66,"4","BBB","جيد","متوسطة"),
        (58,"5","BB","مقبول بحذر","متوسطة-مرتفعة"),
        (50,"6","B","ضعيف نسبيًا","مرتفعة"),
        (40,"7","CCC","ضعيف","مرتفعة جدًا"),
        (0,"8","CC","حرج","حرجة"),
    ]
    for floor,grade,code,label,risk in bands:
        if score >= floor:
            return grade,code,label,risk
    return "8","CC","حرج","حرجة"

def pd_proxy(score):
    bands=[
        (90,0.005),(82,0.010),(74,0.020),(66,0.040),
        (58,0.075),(50,0.130),(40,0.220),(0,0.350)
    ]
    for floor,p in bands:
        if score >= floor:
            return p
    return 0.35

def qualitative_score(d):
    market = (
        linear_score(d["market_position"],1,5)*0.22 +
        linear_score(d["market_outlook"],1,5)*0.20 +
        linear_score(d["years_business"],1,20)*0.18 +
        linear_score(d["customer_concentration"],60,10,False)*0.12 +
        linear_score(d["supplier_concentration"],70,15,False)*0.10 +
        linear_score(d["fx_exposure"],70,10,False)*0.10 +
        linear_score(d["import_dependency"],100,20,False)*0.08
    )
    working_capital_quality = (
        (100 if d["ar_aging"] else 35)*0.18 +
        (100 if d["inventory_aging"] else 35)*0.18 +
        linear_score(d["customer_concentration"],60,10,False)*0.17 +
        linear_score(d["supplier_concentration"],70,15,False)*0.17 +
        linear_score(d["inventory_liquidity"],1,5)*0.18 +
        (100 if d["insurance"] else 35)*0.12
    )
    capital_structure = (
        linear_score(d["banking_capacity"],1,5)*0.25 +
        linear_score(d["owner_support"],1,5)*0.25 +
        linear_score(d["asset_quality"],1,5)*0.20 +
        linear_score(d["external_debt_concentration"],80,10,False)*0.15 +
        linear_score(d["relationship_years"],0,5)*0.15
    )
    management = (
        linear_score(d["management_quality"],1,5)*0.16 +
        linear_score(d["governance"],1,5)*0.13 +
        linear_score(d["succession"],1,5)*0.10 +
        linear_score(d["integrity"],1,5)*0.13 +
        linear_score(d["transparency"],1,5)*0.12 +
        clamp(d["repayment_score"])*0.16 +
        (100 if d["bureau_regular"] else 20)*0.10 +
        (100 if not d["legal_cases"] else 20)*0.05 +
        (100 if d["audited_fs"] else 45)*0.05
    )
    total = market*0.20 + working_capital_quality*0.20 + capital_structure*0.20 + management*0.40
    return {
        "السوق والنشاط": market,
        "رأس المال العامل والسيولة النوعية": working_capital_quality,
        "هيكل رأس المال والعلاقة المصرفية": capital_structure,
        "الإدارة والسلوك والحوكمة": management,
        "total": total
    }

def financial_score(m):
    scores = {
        "نمو المبيعات": linear_score(m["sales_growth"],-0.10,0.15),
        "هامش مجمل الربح": linear_score(m["gross_margin"],0.03,0.20),
        "هامش صافي الربح": linear_score(m["net_margin"],0.00,0.10),
        "الرافعة المالية": linear_score(m["leverage"],4.0,0.8,False),
        "نسبة التداول": linear_score(m["current_ratio"],0.8,1.8),
        "السيولة السريعة": linear_score(m["quick_ratio"],0.05,1.0),
        "تغطية الفوائد": linear_score(m["interest_cover"],1.0,4.0),
        "DSCR بعد التمويل": linear_score(m["proforma_dscr"],0.8,1.75),
        "التدفق التشغيلي": 100 if m["cfo"] > 0 else 0,
        "الفجوة التمويلية": linear_score(m["wc_gap_days"],120,20,False),
        "حقوق الملكية/الأصول الثابتة": linear_score(m["equity_fixed"],0.5,1.5),
        "التدفق النقدي الحر": linear_score(m["fcf_margin"],-0.05,0.10),
    }
    weights={
        "نمو المبيعات":0.06,
        "هامش مجمل الربح":0.08,
        "هامش صافي الربح":0.08,
        "الرافعة المالية":0.10,
        "نسبة التداول":0.07,
        "السيولة السريعة":0.06,
        "تغطية الفوائد":0.08,
        "DSCR بعد التمويل":0.20,
        "التدفق التشغيلي":0.08,
        "الفجوة التمويلية":0.07,
        "حقوق الملكية/الأصول الثابتة":0.05,
        "التدفق النقدي الحر":0.07,
    }
    total=sum(scores[k]*weights[k] for k in weights)
    return scores,total

def evaluate(d):
    rev=d["revenue"]; prev=d["revenue_prev"]; gp=d["gross_profit"]; ni=d["net_income"]; ebitda=d["ebitda"]
    cash=d["cash"]; ar=d["receivables"]; inv=d["inventory"]; ca=d["current_assets"]; ta=d["total_assets"]
    ap=d["payables"]; cl=d["current_liabilities"]; tl=d["total_liabilities"]; eq=d["equity"]
    cfo=d["cfo"]; capex=d["capex"]; interest=d["interest_expense"]; existing_ds=d["existing_debt_service"]
    request_fc=d["requested_amount"]; fx=d["fx_rate"] if d["facility_currency"]!="BASE" else 1.0
    req=request_fc*fx
    rate=max(d["profit_rate"],0)
    tenor=max(d["tenor_months"],1)
    util=clamp(d["utilization_pct"],0,100)/100
    proposed_ead=req*util

    cogs=max(rev-gp,0)
    sales_growth=safe_div(rev-prev,prev,0)
    gross_margin=safe_div(gp,rev,0); net_margin=safe_div(ni,rev,0); ebitda_margin=safe_div(ebitda,rev,0)
    leverage=safe_div(tl,eq,99); debt_assets=safe_div(tl,ta,99)
    current_ratio=safe_div(ca,cl,99); quick_ratio=safe_div(ca-inv,cl,0)
    interest_cover=safe_div(ebitda,interest,99 if ebitda>0 else 0)
    dso=safe_div(ar,rev,0)*365
    dio=safe_div(inv,cogs,0)*365 if cogs>0 else 0
    dpo=safe_div(ap,cogs,0)*365 if cogs>0 else 0
    wc_gap=max(dso+dio-dpo,0)
    gross_wc_need=cogs/365*wc_gap
    nwc=ca-cl
    external_wc_need=max(gross_wc_need-max(nwc,0),0)
    fcf=cfo-capex
    fcf_margin=safe_div(fcf,rev,0)
    fixed_assets=max(ta-ca,0)
    equity_fixed=safe_div(eq,fixed_assets,99 if eq>0 else 0)

    years=max(tenor/12,1)
    if d["facility_type"]=="REVOLVING":
        annual_principal=req if tenor<=12 else req/years
    else:
        annual_principal=req/years
    proposed_service=annual_principal + req*rate
    total_debt_service=existing_ds+proposed_service
    proforma_dscr=safe_div(cfo,total_debt_service,99 if cfo>0 else 0)
    proforma_leverage=safe_div(tl+req,eq,99)
    request_assets=safe_div(req,ta,99)

    coll_adj=d["collateral_market"]*(1-clamp(d["collateral_haircut"],0,95)/100)
    if not d["collateral_legal"]:
        coll_adj=0
    coll_coverage=safe_div(coll_adj,req,0)
    valuation_stale=d["valuation_age_months"]>12

    metrics=dict(
        sales_growth=sales_growth,gross_margin=gross_margin,net_margin=net_margin,ebitda_margin=ebitda_margin,
        leverage=leverage,debt_assets=debt_assets,current_ratio=current_ratio,quick_ratio=quick_ratio,
        interest_cover=interest_cover,dso=dso,dio=dio,dpo=dpo,wc_gap_days=wc_gap,gross_wc_need=gross_wc_need,
        nwc=nwc,external_wc_need=external_wc_need,fcf=fcf,fcf_margin=fcf_margin,equity_fixed=equity_fixed,
        proposed_service=proposed_service,total_debt_service=total_debt_service,proforma_dscr=proforma_dscr,
        proforma_leverage=proforma_leverage,request_assets=request_assets,req_local=req,coll_adj=coll_adj,
        coll_coverage=coll_coverage,cfo=cfo
    )

    q=qualitative_score(d)
    f_scores,f_total=financial_score(metrics)

    dq_items=[
        100 if d["audited_fs"] else 35,
        100 if d["ar_aging"] else 25,
        100 if d["inventory_aging"] else 25,
        100 if d["bureau_checked"] else 20,
        100 if d["collateral_legal"] else 30,
        100 if not valuation_stale else 55,
        100 if d["customer_concentration"]>0 else 40,
        100 if d["supplier_concentration"]>0 else 40,
    ]
    data_quality=sum(dq_items)/len(dq_items)

    study_style_score=(q["total"]+f_total)/2
    prudential_overlay=(
        f_total*0.55 + q["total"]*0.30 + clamp(d["repayment_score"])*0.10 + data_quality*0.05
    )
    final_score=round(0.45*study_style_score + 0.55*prudential_overlay,1)

    exceptions=[]
    severe=[]
    if d["default_flag"] or d["days_past_due"]>=90:
        severe.append("مؤشر تعثر/تأخر 90 يوماً أو أكثر — يتطلب تصنيفاً ائتمانياً متعثراً ومراجعة متخصصة.")
    elif d["days_past_due"]>30:
        exceptions.append("تأخر أكثر من 30 يوماً — مؤشر زيادة جوهرية في مخاطر الائتمان ما لم توجد أدلة قابلة للدعم لعكس ذلك.")
    if proforma_dscr < 1.0:
        severe.append(f"DSCR بعد التمويل {proforma_dscr:.2f}x أقل من 1.00x؛ التدفق التشغيلي لا يغطي خدمة الدين.")
    elif proforma_dscr < 1.25:
        exceptions.append(f"DSCR بعد التمويل {proforma_dscr:.2f}x دون مستوى 1.25x الإرشادي.")
    if proforma_leverage > 3.0:
        exceptions.append(f"الرافعة المالية المتوقعة ترتفع إلى {proforma_leverage:.2f}x.")
    if request_assets > .50:
        exceptions.append(f"حجم الطلب يعادل {request_assets*100:.1f}% من إجمالي الأصول.")
    if d["facility_type"]=="REVOLVING":
        if external_wc_need<=0 and req>0:
            exceptions.append("النموذج لا يثبت احتياجاً خارجياً لرأس المال العامل وفق دورة التشغيل المدخلة.")
        elif external_wc_need>0 and req>external_wc_need*1.25:
            exceptions.append("الطلب يتجاوز الاحتياج الخارجي المحسوب لرأس المال العامل بأكثر من 25%.")
    if quick_ratio < .5:
        exceptions.append(f"السيولة السريعة منخفضة ({quick_ratio:.2f}x) وتعكس اعتماداً مرتفعاً على تصريف المخزون.")
    if d["fx_exposure"]>25 and d["fx_hedged_pct"]<50:
        exceptions.append("تعرض مرتفع للعملات الأجنبية دون تحوط كافٍ.")
    if not d["insurance"]:
        exceptions.append("تغطية التأمين على الأصول/المخزون غير كافية أو غير مؤكدة.")
    if not d["ar_aging"]:
        exceptions.append("جدول أعمار الذمم المدينة غير متوفر.")
    if not d["inventory_aging"]:
        exceptions.append("تحليل أعمار/ركود المخزون غير متوفر.")
    if not d["collateral_legal"]:
        exceptions.append("القابلية القانونية للضمان للتنفيذ لم تُثبت.")
    if valuation_stale:
        exceptions.append("تقييم الضمان أقدم من 12 شهراً ويحتاج تحديثاً.")
    if coll_coverage < 1.0 and req>0:
        exceptions.append(f"تغطية الضمان بعد التحفظ {coll_coverage:.2f}x أقل من 1.00x.")
    if data_quality < 60:
        exceptions.append(f"جودة/اكتمال البيانات {data_quality:.0f}/100 فقط؛ يلزم استكمال المستندات قبل القرار.")

    target_dscr=1.25
    available_service=max(cfo/target_dscr-existing_ds,0)
    service_factor=(1/years)+rate if d["facility_type"]!="REVOLVING" or tenor>12 else (1+rate)
    cashflow_limit=max(available_service/max(service_factor,0.01),0)
    wc_limit=external_wc_need if d["facility_type"]=="REVOLVING" else req
    collateral_limit=coll_adj/1.20 if coll_adj>0 else 0
    leverage_limit=max(3.0*eq-tl,0)
    candidates=[req,cashflow_limit,leverage_limit]
    if d["facility_type"]=="REVOLVING":
        candidates.append(wc_limit)
    if coll_adj>0:
        candidates.append(collateral_limit)
    recommended_limit=max(0,min(candidates)) if candidates else 0

    if severe:
        decision="لا يوصى بالموافقة بالشكل الحالي"
        decision_class="decline"
    elif final_score>=75 and proforma_dscr>=1.25 and len(exceptions)<=2 and data_quality>=70:
        decision="مؤهل للموافقة الائتمانية المشروطة"
        decision_class="approve"
    elif final_score>=60 and proforma_dscr>=1.0:
        decision="إعادة هيكلة/مراجعة مشروطة قبل العرض على اللجنة"
        decision_class="review"
    else:
        decision="مخاطر مرتفعة — إعادة هيكلة الطلب أو رفضه"
        decision_class="decline"

    grade,code,label,risk=rating_band(final_score)

    if d["default_flag"] or d["days_past_due"]>=90:
        stage="Stage 3"; stage_ar="المرحلة الثالثة – متعثر/منخفض القيمة ائتمانياً"
    elif d["sicr_flag"] or d["days_past_due"]>30:
        stage="Stage 2"; stage_ar="المرحلة الثانية – زيادة جوهرية في مخاطر الائتمان"
    else:
        stage="Stage 1"; stage_ar="المرحلة الأولى – دون زيادة جوهرية مثبتة"

    pd12=pd_proxy(final_score)
    base_pd=pd12
    mod_pd=min(pd12*1.6,1)
    sev_pd=min(pd12*2.8,1)
    if stage=="Stage 3":
        weighted_pd=1.0
    elif stage=="Stage 2":
        years_life=max(tenor/12,1)
        conv=lambda p: 1-(1-p)**years_life
        weighted_pd=.60*conv(base_pd)+.25*conv(mod_pd)+.15*conv(sev_pd)
    else:
        weighted_pd=.60*base_pd+.25*mod_pd+.15*sev_pd

    recoverable=min(coll_adj*0.85, proposed_ead) if d["collateral_legal"] else 0
    lgd=clamp((1-safe_div(recoverable,proposed_ead,0))*100,10,90)/100 if proposed_ead>0 else 0
    discount=1/(1+max(rate,0.01))**max(tenor/12,0.25)
    ecl=proposed_ead*weighted_pd*lgd*discount

    scenarios=[]
    for name,rev_shock,cfo_shock,fx_shock,dio_add,dso_add,dpo_add,weight in [
        ("أساسي",0,0,0,0,0,0,.60),
        ("ضغط متوسط",-0.15,-0.25,0.15,20,5,-5,.25),
        ("ضغط شديد",-0.30,-0.45,0.30,45,10,-10,.15),
    ]:
        stressed_rev=rev*(1+rev_shock)
        stressed_cfo=cfo*(1+cfo_shock)
        fx_mult=1+fx_shock if d["facility_currency"]!="BASE" else 1
        stressed_service=existing_ds+proposed_service*fx_mult
        stress_dscr=safe_div(stressed_cfo,stressed_service,0)
        stress_gap=max((dso+dso_add)+(dio+dio_add)-(dpo+dpo_add),0)
        stress_wc=max((cogs*(1+rev_shock))/365*stress_gap-max(nwc,0),0)
        status="مريح" if stress_dscr>=1.25 else "حساس" if stress_dscr>=1.0 else "غير مغطى"
        scenarios.append(dict(name=name,rev=stressed_rev,cfo=stressed_cfo,dscr=stress_dscr,wc=stress_wc,status=status,weight=weight))

    strengths=[]
    if sales_growth>0.10: strengths.append("نمو إيجابي وقوي في الإيرادات.")
    if cfo>0: strengths.append("تدفقات نقدية تشغيلية موجبة.")
    if current_ratio>=1.2: strengths.append("نسبة التداول مقبولة.")
    if leverage<=1.5: strengths.append("الرافعة المالية الحالية ضمن مستوى متحفظ نسبياً.")
    if d["repayment_score"]>=80 and d["bureau_regular"]: strengths.append("سجل السداد والاستعلام الائتماني داعمان.")
    if coll_coverage>=1.2 and d["collateral_legal"]: strengths.append("تغطية الضمان بعد التحفظ جيدة مع قابلية تنفيذ مثبتة.")
    if d["years_business"]>=10: strengths.append("خبرة تشغيلية طويلة في النشاط.")
    if not strengths: strengths=["لا توجد نقاط قوة كافية مثبتة بالبيانات المدخلة."]

    covenants=[
        "الحفاظ على DSCR لا يقل عن 1.25x طوال مدة التسهيل.",
        "عدم تجاوز إجمالي الالتزامات إلى حقوق الملكية 3.0x دون موافقة البنك."
    ]
    if d["facility_type"]=="REVOLVING":
        covenants.append("ربط استخدام السقف بمستندات شراء/مخزون والتحقق الدوري من دورة رأس المال العامل.")
    if d["fx_exposure"]>20:
        covenants.append("إدارة مخاطر العملة وربط التمويل بتدفقات أو أصول بالعملة ذاتها قدر الإمكان.")
    if not d["insurance"]:
        covenants.append("استكمال التأمين المناسب على المخزون والأصول القابلة للتعرض للخسارة.")
    if not d["ar_aging"] or not d["inventory_aging"]:
        covenants.append("تقديم تقارير شهرية/ربع سنوية لأعمار الذمم والمخزون.")
    covenants += [
        "تقديم قوائم مالية سنوية مدققة ومعلومات إدارية دورية مع حق البنك في إعادة التسعير/المراجعة.",
        "عدم زيادة مديونية جوهرية لدى جهات أخرى أو توزيع مبالغ استثنائية للملاك دون إخطار/موافقة حسب السياسة."
    ]

    return {
        "metrics":metrics,"qualitative":q,"financial_scores":f_scores,"financial_total":f_total,
        "study_score":study_style_score,"prudential_score":prudential_overlay,"score":final_score,
        "grade":grade,"code":code,"label":label,"risk":risk,"decision":decision,"decision_class":decision_class,
        "exceptions":exceptions,"severe":severe,"data_quality":data_quality,"recommended_limit":recommended_limit,
        "cashflow_limit":cashflow_limit,"wc_limit":wc_limit,"collateral_limit":collateral_limit,"leverage_limit":leverage_limit,
        "stage":stage,"stage_ar":stage_ar,"pd12":pd12,"weighted_pd":weighted_pd,"lgd":lgd,"ead":proposed_ead,"ecl":ecl,
        "scenarios":scenarios,"strengths":strengths,"covenants":covenants
    }

STYLE = '''
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:#f3f6fb;color:#142033;font-family:system-ui,-apple-system,'Segoe UI',Arial,sans-serif}
header{position:sticky;top:0;z-index:20;background:linear-gradient(135deg,#07152c,#153a68);color:#fff;border-bottom:1px solid #ffffff20}
.top,.wrap{max-width:1180px;margin:auto}.top{padding:15px 14px;display:flex;align-items:center;justify-content:space-between;gap:10px}.brand{font-weight:950;font-size:19px}.brand small{display:block;font-weight:600;font-size:10px;color:#bfccdd;margin-top:2px}.version{background:#ffffff14;border:1px solid #ffffff25;padding:7px 10px;border-radius:999px;font-size:11px}
.wrap{padding:20px 13px 50px}.card{background:#fff;border:1px solid #e2e8f0;border-radius:18px;box-shadow:0 10px 32px #07152c0b}.hero{padding:24px;background:linear-gradient(135deg,#fff 58%,#eafaf7);margin-bottom:14px}.eyebrow{font-size:11px;font-weight:900;color:#0f8f83;letter-spacing:.7px}.hero h1{font-size:28px;margin:8px 0 6px}.hero p{color:#657188;line-height:1.8;margin:0}.banner{margin-top:12px;padding:11px 13px;border:1px solid #f0dca8;background:#fff9e9;color:#765a14;border-radius:12px;font-size:12px;line-height:1.7}
.steps{display:flex;gap:7px;overflow:auto;padding:3px 0 11px;scrollbar-width:none}.step{white-space:nowrap;border:1px solid #dce3ec;background:#fff;color:#526077;padding:9px 11px;border-radius:11px;font-size:12px;font-weight:850}.step.on{background:#102444;color:#fff;border-color:#102444}
.form{padding:19px}.sec{display:none}.sec.on{display:block}.section-title{display:flex;justify-content:space-between;align-items:end;gap:8px;margin-bottom:14px}.section-title h2{font-size:20px;margin:0}.section-title span{font-size:11px;color:#7c8799}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.grid3{grid-template-columns:repeat(3,minmax(0,1fr))}
.f label{display:block;font-size:12px;font-weight:800;color:#4a566a}.f input,.f select{width:100%;margin-top:6px;border:1px solid #d7dee8;border-radius:11px;padding:12px 11px;font-size:15px;background:#fff;color:#172033}.f input:focus,.f select:focus{outline:2px solid #0f93872c;border-color:#0f9387}.hint{font-size:10px;color:#8490a1;margin-top:4px}
.matrix{overflow:auto;border:1px solid #e3e8ef;border-radius:13px}.matrix table{min-width:720px;width:100%;border-collapse:collapse}.matrix th,.matrix td{padding:9px;border-bottom:1px solid #edf0f4;text-align:right;font-size:12px}.matrix th{background:#f8fafc;color:#455269}.matrix input{width:100%;min-width:125px;padding:9px;border:1px solid #dce2ea;border-radius:8px;font-size:14px}
.checks{display:grid;grid-template-columns:1fr 1fr;gap:8px}.check{display:flex;align-items:center;gap:8px;border:1px solid #e2e8f0;border-radius:11px;padding:10px;font-size:12px}.check input{width:18px;height:18px}
.act{display:flex;justify-content:space-between;gap:8px;margin-top:18px}.btn{border:0;border-radius:11px;padding:12px 16px;font-weight:900;cursor:pointer}.pri{background:#102444;color:#fff}.alt{background:#edf2f7;color:#26354a}.go{background:#0b8f82;color:#fff}
.result-top{display:grid;grid-template-columns:.8fr 1.2fr;gap:14px}.scorebox{padding:22px;text-align:center;color:#fff;background:linear-gradient(145deg,#07152c,#19416f)}.scorebox .num{font-size:48px;font-weight:950}.scorebox small{color:#cad7e8}.ring{width:165px;height:165px;border-radius:50%;margin:12px auto;display:grid;place-items:center;background:conic-gradient(#2dd4bf calc(var(--s)*1%),#ffffff19 0);border:11px solid #ffffff10}.decision{padding:22px}.pill{display:inline-block;padding:7px 11px;border-radius:999px;font-size:11px;font-weight:900}.approve{background:#e5f8f2;color:#08725f}.review{background:#fff3d8;color:#8a5e00}.decline{background:#fde8ea;color:#a52635}.kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:9px;margin-top:15px}.kpi{border:1px solid #e4e9f0;border-radius:12px;padding:11px}.kpi small{display:block;color:#758195;font-size:10px}.kpi b{display:block;margin-top:4px;font-size:17px}
.two{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:14px}.panel{padding:19px}.panel h3{margin:0 0 12px;font-size:17px}.metric{margin:11px 0}.mh{display:flex;justify-content:space-between;gap:10px;font-size:11px;font-weight:800}.bar{height:7px;background:#edf1f5;border-radius:99px;overflow:hidden;margin-top:5px}.bar i{height:100%;display:block;background:#0f9387}.tablewrap{overflow:auto}.table{width:100%;border-collapse:collapse;min-width:520px}.table td,.table th{padding:9px;border-bottom:1px solid #e8edf3;text-align:right;font-size:12px}.table th{color:#5c687b;background:#f8fafc}
.flags{padding:0;margin:0;list-style:none}.flags li{padding:9px 10px;border-radius:9px;background:#fff8ea;border:1px solid #f2e1b7;margin:7px 0;font-size:12px;line-height:1.6}.flags.severe li{background:#fff0f1;border-color:#f5cfd4;color:#8f2632}.good li{background:#eefaf6;border-color:#ceeede;color:#14614e}
.memo{margin-top:14px;padding:20px;line-height:1.85}.actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}a.btn{text-decoration:none;display:inline-block}.small{font-size:11px;color:#728096;line-height:1.7}.tag{display:inline-block;padding:5px 8px;border-radius:8px;background:#eef3f8;font-size:10px;font-weight:800;margin:2px}
.gates{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}.gate{padding:10px;border:1px solid #e4e9f0;border-radius:11px}.gate small{font-size:10px;color:#718096}.gate b{display:block;margin-top:3px;font-size:15px}
@media(max-width:760px){.grid,.grid3,.result-top,.two{grid-template-columns:1fr}.checks{grid-template-columns:1fr}.kpis,.gates{grid-template-columns:1fr 1fr}.hero h1{font-size:23px}.wrap{padding-left:9px;padding-right:9px}.form{padding:15px}}
@media print{header,.steps,.actions{display:none}body{background:#fff}.card{box-shadow:none}.wrap{max-width:none}.result-top,.two{break-inside:avoid}}
'''

def field(name,label,value,typ="number",hint="",step="any",minv=None,maxv=None):
    attrs=f'name="{name}" value="{value}" type="{typ}" step="{step}"'
    if minv is not None: attrs+=f' min="{minv}"'
    if maxv is not None: attrs+=f' max="{maxv}"'
    return f'<div class="f"><label>{label}<input {attrs} required></label><div class="hint">{hint}</div></div>'

def select(name,label,options,selected=None,hint=""):
    opts="".join(f'<option value="{v}" {"selected" if v==selected else ""}>{t}</option>' for v,t in options)
    return f'<div class="f"><label>{label}<select name="{name}">{opts}</select></label><div class="hint">{hint}</div></div>'

def checkbox(name,label,checked=False):
    return f'<label class="check"><input type="checkbox" name="{name}" value="yes" {"checked" if checked else ""}>{label}</label>'

@app.get("/", response_class=HTMLResponse)
def home():
    yr = '''
    <div class="matrix"><table>
    <tr><th>البند المالي</th><th>السنة السابقة</th><th>آخر سنة مالية</th></tr>
    <tr><td>الإيرادات</td><td><input name="revenue_prev" type="number" value="8000000"></td><td><input name="revenue" type="number" value="10000000"></td></tr>
    <tr><td>مجمل الربح</td><td><input name="gross_profit_prev" type="number" value="900000"></td><td><input name="gross_profit" type="number" value="1200000"></td></tr>
    <tr><td>صافي الربح</td><td><input name="net_income_prev" type="number" value="300000"></td><td><input name="net_income" type="number" value="450000"></td></tr>
    <tr><td>EBITDA</td><td><input name="ebitda_prev" type="number" value="520000"></td><td><input name="ebitda" type="number" value="700000"></td></tr>
    <tr><td>النقد</td><td><input name="cash_prev" type="number" value="300000"></td><td><input name="cash" type="number" value="350000"></td></tr>
    <tr><td>الذمم المدينة</td><td><input name="receivables_prev" type="number" value="450000"></td><td><input name="receivables" type="number" value="500000"></td></tr>
    <tr><td>المخزون</td><td><input name="inventory_prev" type="number" value="2200000"></td><td><input name="inventory" type="number" value="2500000"></td></tr>
    <tr><td>الأصول المتداولة</td><td><input name="current_assets_prev" type="number" value="3500000"></td><td><input name="current_assets" type="number" value="4000000"></td></tr>
    <tr><td>إجمالي الأصول</td><td><input name="total_assets_prev" type="number" value="5200000"></td><td><input name="total_assets" type="number" value="6000000"></td></tr>
    <tr><td>الذمم الدائنة</td><td><input name="payables_prev" type="number" value="1200000"></td><td><input name="payables" type="number" value="1300000"></td></tr>
    <tr><td>الالتزامات المتداولة</td><td><input name="current_liabilities_prev" type="number" value="2400000"></td><td><input name="current_liabilities" type="number" value="2600000"></td></tr>
    <tr><td>إجمالي الالتزامات</td><td><input name="total_liabilities_prev" type="number" value="3000000"></td><td><input name="total_liabilities" type="number" value="3400000"></td></tr>
    <tr><td>حقوق الملكية</td><td><input name="equity_prev" type="number" value="2200000"></td><td><input name="equity" type="number" value="2600000"></td></tr>
    <tr><td>التدفق النقدي التشغيلي CFO</td><td><input name="cfo_prev" type="number" value="600000"></td><td><input name="cfo" type="number" value="850000"></td></tr>
    </table></div>
    '''
    s1 = field("borrower_name","اسم العميل/الشركة","شركة نموذجية","text") + \
         select("legal_form","الشكل القانوني",[("sole","منشأة فردية"),("llc","شركة ذات مسؤولية محدودة"),("corp","شركة مساهمة/مؤسسية"),("other","أخرى")],"llc") + \
         field("sector","القطاع/النشاط","تجارة واستيراد","text") + \
         field("years_business","سنوات الخبرة في النشاط",12,step="1",minv=0) + \
         field("relationship_years","سنوات العلاقة مع البنك",2,step="0.1",minv=0) + \
         select("base_currency","عملة القوائم",[("YER","ريال يمني"),("SAR","ريال سعودي"),("USD","دولار أمريكي"),("OTHER","عملة أخرى")],"YER")
    s3 = field("capex","الإنفاق الرأسمالي السنوي",120000) + field("interest_expense","تكلفة/أرباح التمويل الحالية",120000) + \
         field("existing_debt_service","خدمة الدين القائمة سنوياً (أصل + أرباح)",200000) + \
         field("repayment_score","سجل السداد 0–100",85,step="1",minv=0,maxv=100)
    s4 = select("facility_type","نوع التسهيل",[("REVOLVING","سقف دوار / رأس مال عامل"),("TERM","تمويل لأجل"),("OTHER","أخرى")],"REVOLVING") + \
         field("requested_amount","مبلغ التمويل المطلوب بعملة التسهيل",1500000) + \
         select("facility_currency","عملة التسهيل",[("BASE","نفس عملة القوائم"),("USD","دولار أمريكي"),("SAR","ريال سعودي"),("OTHER","عملة أجنبية أخرى")],"BASE") + \
         field("fx_rate","سعر الصرف إلى عملة القوائم",1,step="0.0001",minv=0.0001) + \
         field("profit_rate","نسبة الربح/الفائدة السنوية",0.07,step="0.001",minv=0,maxv=1,hint="مثال 0.07 = 7%") + \
         field("tenor_months","المدة بالأشهر",12,step="1",minv=1) + \
         field("utilization_pct","نسبة السحب المتوقعة %",100,step="1",minv=0,maxv=100) + \
         field("fx_exposure","التعرض للعملات الأجنبية %",35,step="1",minv=0,maxv=100) + \
         field("fx_hedged_pct","نسبة التعرض المغطاة/المتحوطة %",10,step="1",minv=0,maxv=100)
    s5 = field("collateral_market","القيمة السوقية للضمان",2200000) + \
         field("collateral_haircut","نسبة التحفظ/الحسم %",30,step="1",minv=0,maxv=95) + \
         field("valuation_age_months","عمر آخر تقييم للضمان بالأشهر",4,step="1",minv=0) + \
         select("collateral_liquidity","سيولة الضمان",[(1,"ضعيفة جدًا"),(2,"ضعيفة"),(3,"متوسطة"),(4,"جيدة"),(5,"عالية")],3)
    s6 = select("market_position","الوضع التنافسي",[(1,"ضعيف جدًا"),(2,"ضعيف"),(3,"متوسط"),(4,"قوي"),(5,"قوي جدًا")],3) + \
         select("market_outlook","جاذبية/اتجاه القطاع",[(1,"انكماش حاد"),(2,"ضعيف"),(3,"مستقر"),(4,"نمو"),(5,"نمو قوي")],4) + \
         field("customer_concentration","حصة أكبر 3 عملاء %",25,step="1",minv=0,maxv=100) + \
         field("supplier_concentration","حصة أكبر 3 موردين %",40,step="1",minv=0,maxv=100) + \
         field("import_dependency","نسبة الاعتماد على الاستيراد %",70,step="1",minv=0,maxv=100) + \
         select("inventory_liquidity","قابلية تصريف المخزون",[(1,"ضعيفة جدًا"),(2,"ضعيفة"),(3,"متوسطة"),(4,"جيدة"),(5,"عالية")],4) + \
         select("banking_capacity","القدرة على الوصول للتمويل المصرفي",[(1,"ضعيفة"),(2,"محدودة"),(3,"متوسطة"),(4,"جيدة"),(5,"قوية")],3) + \
         select("owner_support","ملاءة/دعم الملاك",[(1,"ضعيف"),(2,"محدود"),(3,"متوسط"),(4,"جيد"),(5,"قوي")],4) + \
         select("asset_quality","جودة وتنوع الأصول",[(1,"ضعيفة"),(2,"محدودة"),(3,"متوسطة"),(4,"جيدة"),(5,"قوية")],3) + \
         field("external_debt_concentration","الاعتماد على أكبر بنك/ممّول %",25,step="1",minv=0,maxv=100)
    s7 = select("management_quality","كفاءة واستقرار الإدارة",[(1,"ضعيف جدًا"),(2,"ضعيف"),(3,"متوسط"),(4,"جيد"),(5,"ممتاز")],4) + \
         select("governance","الحوكمة والفصل بين الملكية والإدارة",[(1,"ضعيفة جدًا"),(2,"ضعيفة"),(3,"متوسطة"),(4,"جيدة"),(5,"قوية")],3) + \
         select("succession","خطة التعاقب الإداري",[(1,"غير موجودة"),(2,"ضعيفة"),(3,"متوسطة"),(4,"جيدة"),(5,"مكتملة")],3) + \
         select("integrity","النزاهة والسمعة",[(1,"ضعيفة"),(2,"محدودة"),(3,"مقبولة"),(4,"جيدة"),(5,"ممتازة")],4) + \
         select("transparency","جودة وشفافية المعلومات",[(1,"ضعيفة"),(2,"محدودة"),(3,"مقبولة"),(4,"جيدة"),(5,"ممتازة")],4) + \
         field("days_past_due","أقصى أيام تأخر حالية",0,step="1",minv=0)

    checks = "".join([
        checkbox("audited_fs","قوائم مالية مدققة من مراجع مستقل",True),
        checkbox("ar_aging","جدول أعمار الذمم المدينة متوفر",True),
        checkbox("inventory_aging","تحليل أعمار/ركود المخزون متوفر",True),
        checkbox("insurance","تأمين مناسب على الأصول/المخزون",True),
        checkbox("bureau_checked","تم التحقق من مركزية المخاطر/الائتمان",True),
        checkbox("bureau_regular","نتيجة الاستعلام منتظمة",True),
        checkbox("collateral_legal","قابلية تنفيذ الضمان قانونياً مثبتة",True),
        checkbox("sicr_flag","توجد مؤشرات زيادة جوهرية في مخاطر الائتمان (SICR)",False),
        checkbox("default_flag","توجد مؤشرات تعثر/Default",False),
        checkbox("legal_cases","توجد قضايا جوهرية قائمة",False),
    ])
    step_buttons="".join(
        f'<button class="step {"on" if i==0 else ""}" type="button">{i+1}. {t}</button>'
        for i,t in enumerate(["العميل","القوائم","التدفقات","التسهيل","الضمان","السوق","الحوكمة"])
    )
    return f'''<!doctype html><html lang="ar" dir="rtl"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>AI Credit Analysis V3</title><style>{STYLE}</style>
    <header><div class="top"><div class="brand">AI Credit Analysis<small>Corporate Credit Intelligence & Decision Support</small></div><div class="version">V3 • Bank-Grade</div></div></header>
    <main class="wrap"><div class="card hero"><div class="eyebrow">EXPLAINABLE CREDIT UNDERWRITING</div><h1>تحليل ائتماني مؤسسي من الطلب إلى مذكرة اللجنة</h1>
    <p>نسخة مطوّرة مستفيدة من هيكل الدراسة البنكية: النشاط، رأس المال العامل، هيكل رأس المال، الإدارة والسلوك، التحليل المالي، الضمانات، مخاطر الطلب والتوصية.</p>
    <div class="banner">المنصة أداة دعم قرار. نماذج PD/LGD/ECL والحدود الائتمانية هنا إرشادية وتحتاج معايرة واعتماداً مستقلاً ومواءمة مع سياسة البنك والجهة الرقابية المحلية قبل الاستخدام الإنتاجي.</div></div>
    <div class="steps">{step_buttons}</div>
    <form class="card form" method="post" action="/analyze">
    <section class="sec on"><div class="section-title"><h2>هوية العميل</h2><span>Borrower Profile</span></div><div class="grid">{s1}</div><div class="act"><span></span><button class="btn pri next" type="button">التالي</button></div></section>
    <section class="sec"><div class="section-title"><h2>القوائم المالية</h2><span>Trend & Structure</span></div>{yr}<div class="act"><button class="btn alt prev" type="button">السابق</button><button class="btn pri next" type="button">التالي</button></div></section>
    <section class="sec"><div class="section-title"><h2>التدفقات وخدمة الدين</h2><span>Cash Flow First</span></div><div class="grid">{s3}</div><div class="act"><button class="btn alt prev" type="button">السابق</button><button class="btn pri next" type="button">التالي</button></div></section>
    <section class="sec"><div class="section-title"><h2>هيكل التسهيل</h2><span>Facility Structure</span></div><div class="grid">{s4}</div><div class="act"><button class="btn alt prev" type="button">السابق</button><button class="btn pri next" type="button">التالي</button></div></section>
    <section class="sec"><div class="section-title"><h2>الضمانات</h2><span>Collateral & Legal Enforceability</span></div><div class="grid">{s5}</div><div class="act"><button class="btn alt prev" type="button">السابق</button><button class="btn pri next" type="button">التالي</button></div></section>
    <section class="sec"><div class="section-title"><h2>السوق ورأس المال العامل</h2><span>Business & Concentration Risk</span></div><div class="grid">{s6}</div><div class="act"><button class="btn alt prev" type="button">السابق</button><button class="btn pri next" type="button">التالي</button></div></section>
    <section class="sec"><div class="section-title"><h2>الحوكمة والسلوك وجودة البيانات</h2><span>Governance, Behaviour & Data</span></div><div class="grid">{s7}</div><h3 style="margin-top:18px">مستندات ومؤشرات تحقق</h3><div class="checks">{checks}</div>
    <div class="act"><button class="btn alt prev" type="button">السابق</button><button class="btn go" type="submit">إصدار التحليل الائتماني V3</button></div></section>
    </form></main>
    <script>
    const secs=[...document.querySelectorAll('.sec')], steps=[...document.querySelectorAll('.step')];let p=0;
    function show(n){{p=Math.max(0,Math.min(secs.length-1,n));secs.forEach((x,i)=>x.classList.toggle('on',i===p));steps.forEach((x,i)=>x.classList.toggle('on',i===p));window.scrollTo({{top:0,behavior:'smooth'}})}}
    document.querySelectorAll('.next').forEach(x=>x.onclick=()=>show(p+1));document.querySelectorAll('.prev').forEach(x=>x.onclick=()=>show(p-1));steps.forEach((x,i)=>x.onclick=()=>show(i));
    </script></html>'''

@app.get("/health")
def health():
    return {"status":"ok","version":"3.0.0","engine":"credit-underwriting-v3"}

def parse_form(form):
    return {
        "borrower_name":str(form.get("borrower_name","عميل")),
        "legal_form":str(form.get("legal_form","other")),
        "sector":str(form.get("sector","")),
        "base_currency":str(form.get("base_currency","YER")),
        "years_business":as_float(form,"years_business",0),
        "relationship_years":as_float(form,"relationship_years",0),

        "revenue_prev":as_float(form,"revenue_prev"),"revenue":as_float(form,"revenue"),
        "gross_profit_prev":as_float(form,"gross_profit_prev"),"gross_profit":as_float(form,"gross_profit"),
        "net_income_prev":as_float(form,"net_income_prev"),"net_income":as_float(form,"net_income"),
        "ebitda_prev":as_float(form,"ebitda_prev"),"ebitda":as_float(form,"ebitda"),
        "cash_prev":as_float(form,"cash_prev"),"cash":as_float(form,"cash"),
        "receivables_prev":as_float(form,"receivables_prev"),"receivables":as_float(form,"receivables"),
        "inventory_prev":as_float(form,"inventory_prev"),"inventory":as_float(form,"inventory"),
        "current_assets_prev":as_float(form,"current_assets_prev"),"current_assets":as_float(form,"current_assets"),
        "total_assets_prev":as_float(form,"total_assets_prev"),"total_assets":as_float(form,"total_assets"),
        "payables_prev":as_float(form,"payables_prev"),"payables":as_float(form,"payables"),
        "current_liabilities_prev":as_float(form,"current_liabilities_prev"),"current_liabilities":as_float(form,"current_liabilities"),
        "total_liabilities_prev":as_float(form,"total_liabilities_prev"),"total_liabilities":as_float(form,"total_liabilities"),
        "equity_prev":as_float(form,"equity_prev"),"equity":as_float(form,"equity"),
        "cfo_prev":as_float(form,"cfo_prev"),"cfo":as_float(form,"cfo"),
        "capex":as_float(form,"capex"),"interest_expense":as_float(form,"interest_expense"),
        "existing_debt_service":as_float(form,"existing_debt_service"),
        "repayment_score":as_float(form,"repayment_score",50),

        "facility_type":str(form.get("facility_type","REVOLVING")),
        "requested_amount":as_float(form,"requested_amount"),
        "facility_currency":str(form.get("facility_currency","BASE")),
        "fx_rate":as_float(form,"fx_rate",1),
        "profit_rate":as_float(form,"profit_rate",0),
        "tenor_months":as_float(form,"tenor_months",12),
        "utilization_pct":as_float(form,"utilization_pct",100),
        "fx_exposure":as_float(form,"fx_exposure",0),
        "fx_hedged_pct":as_float(form,"fx_hedged_pct",0),

        "collateral_market":as_float(form,"collateral_market",0),
        "collateral_haircut":as_float(form,"collateral_haircut",0),
        "valuation_age_months":as_float(form,"valuation_age_months",0),
        "collateral_liquidity":as_float(form,"collateral_liquidity",3),

        "market_position":as_float(form,"market_position",3),
        "market_outlook":as_float(form,"market_outlook",3),
        "customer_concentration":as_float(form,"customer_concentration",0),
        "supplier_concentration":as_float(form,"supplier_concentration",0),
        "import_dependency":as_float(form,"import_dependency",0),
        "inventory_liquidity":as_float(form,"inventory_liquidity",3),
        "banking_capacity":as_float(form,"banking_capacity",3),
        "owner_support":as_float(form,"owner_support",3),
        "asset_quality":as_float(form,"asset_quality",3),
        "external_debt_concentration":as_float(form,"external_debt_concentration",0),

        "management_quality":as_float(form,"management_quality",3),
        "governance":as_float(form,"governance",3),
        "succession":as_float(form,"succession",3),
        "integrity":as_float(form,"integrity",3),
        "transparency":as_float(form,"transparency",3),
        "days_past_due":as_int(form,"days_past_due",0),
        "audited_fs":yes(form,"audited_fs"),"ar_aging":yes(form,"ar_aging"),
        "inventory_aging":yes(form,"inventory_aging"),"insurance":yes(form,"insurance"),
        "bureau_checked":yes(form,"bureau_checked"),"bureau_regular":yes(form,"bureau_regular"),
        "collateral_legal":yes(form,"collateral_legal"),"sicr_flag":yes(form,"sicr_flag"),
        "default_flag":yes(form,"default_flag"),"legal_cases":yes(form,"legal_cases"),
    }

@app.post("/api/analyze")
async def api_analyze(request: Request):
    form=await request.form()
    d=parse_form(form)
    return JSONResponse(evaluate(d))

@app.post("/analyze", response_class=HTMLResponse)
async def analyze_page(request: Request):
    form=await request.form()
    d=parse_form(form)
    if min(d["revenue"],d["total_assets"],d["equity"],d["requested_amount"])<=0:
        return HTMLResponse('<h3 dir="rtl">تحقق من الإيرادات والأصول وحقوق الملكية ومبلغ التمويل.</h3>',400)
    r=evaluate(d); m=r["metrics"]; name=html.escape(d["borrower_name"]); sector=html.escape(d["sector"])

    qbars="".join(
        f'<div class="metric"><div class="mh"><span>{k}</span><b>{v:.0f}/100</b></div><div class="bar"><i style="width:{clamp(v)}%"></i></div></div>'
        for k,v in r["qualitative"].items() if k!="total"
    )
    fbars="".join(
        f'<div class="metric"><div class="mh"><span>{k}</span><b>{v:.0f}/100</b></div><div class="bar"><i style="width:{clamp(v)}%"></i></div></div>'
        for k,v in r["financial_scores"].items()
    )
    ratio_rows=[
        ("نمو المبيعات",pct(m["sales_growth"])),("هامش مجمل الربح",pct(m["gross_margin"])),
        ("هامش صافي الربح",pct(m["net_margin"])),("هامش EBITDA",pct(m["ebitda_margin"])),
        ("نسبة التداول",ratio(m["current_ratio"])),("السيولة السريعة",ratio(m["quick_ratio"])),
        ("الالتزامات / حقوق الملكية",ratio(m["leverage"])),("الرافعة بعد التمويل",ratio(m["proforma_leverage"])),
        ("تغطية الفوائد",ratio(m["interest_cover"])),("DSCR بعد التمويل",ratio(m["proforma_dscr"])),
        ("أيام الذمم المدينة",f'{m["dso"]:.1f} يوم'),("أيام المخزون",f'{m["dio"]:.1f} يوم'),
        ("أيام الموردين",f'{m["dpo"]:.1f} يوم'),("دورة رأس المال العامل",f'{m["wc_gap_days"]:.1f} يوم'),
        ("صافي رأس المال العامل",money(m["nwc"])),("الاحتياج الخارجي لرأس المال العامل",money(m["external_wc_need"])),
        ("التدفق النقدي الحر",money(m["fcf"])),("تغطية الضمان بعد التحفظ",ratio(m["coll_coverage"])),
    ]
    ratios="".join(f"<tr><td>{a}</td><td><b>{b}</b></td></tr>" for a,b in ratio_rows)
    exceptions="".join(f"<li>{html.escape(x)}</li>" for x in r["exceptions"]) or "<li>لا توجد استثناءات رئيسية آلية.</li>"
    severe="".join(f"<li>{html.escape(x)}</li>" for x in r["severe"])
    strengths="".join(f"<li>{html.escape(x)}</li>" for x in r["strengths"])
    covenants="".join(f"<li>{html.escape(x)}</li>" for x in r["covenants"])
    stress="".join(
        f'<tr><td>{s["name"]}</td><td>{s["weight"]*100:.0f}%</td><td>{money(s["rev"])}</td><td>{money(s["cfo"])}</td><td>{s["dscr"]:.2f}x</td><td>{money(s["wc"])}</td><td><b>{s["status"]}</b></td></tr>'
        for s in r["scenarios"]
    )
    gates=f'''<div class="gates">
      <div class="gate"><small>حد التدفق النقدي</small><b>{money(r["cashflow_limit"])}</b></div>
      <div class="gate"><small>حد احتياج رأس المال العامل</small><b>{money(r["wc_limit"])}</b></div>
      <div class="gate"><small>حد الضمان بعد التحفظ</small><b>{money(r["collateral_limit"])}</b></div>
      <div class="gate"><small>حد الرافعة المالية</small><b>{money(r["leverage_limit"])}</b></div>
    </div>'''
    severe_block=f'<ul class="flags severe">{severe}</ul>' if severe else ''
    return f'''<!doctype html><html lang="ar" dir="rtl"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>Credit Memo V3</title><style>{STYLE}</style>
    <header><div class="top"><div class="brand">AI Credit Analysis<small>Explainable Credit Memo</small></div><div class="version">V3.0</div></div></header>
    <main class="wrap">
    <div class="result-top"><div class="card scorebox"><div>الدرجة النهائية</div><div class="ring" style="--s:{r["score"]}"><div><div class="num">{r["score"]}</div><small>من 100</small></div></div><h2>{r["code"]} • درجة مخاطر {r["grade"]}</h2><div>{r["label"]} — مخاطر {r["risk"]}</div></div>
    <div class="card decision"><span class="pill {r["decision_class"]}">{r["decision"]}</span><h1>{name}</h1><p class="small">{sector} • تحليل نقدي وائتماني وقطاعي وسلوكي مع بوابات سياسة مستقلة عن الدرجة.</p>
    <div class="kpis"><div class="kpi"><small>الحد المقترح</small><b>{money(r["recommended_limit"])}</b></div><div class="kpi"><small>الطلب بالعملة الأساسية</small><b>{money(m["req_local"])}</b></div><div class="kpi"><small>DSCR بعد التمويل</small><b>{m["proforma_dscr"]:.2f}x</b></div><div class="kpi"><small>جودة البيانات</small><b>{r["data_quality"]:.0f}/100</b></div></div>
    <div style="margin-top:12px">{gates}</div></div></div>

    <div class="two"><div class="card panel"><h3>التقييم النوعي — هيكل الدراسة البنكية</h3>{qbars}<div class="small">إجمالي النوعي: <b>{r["qualitative"]["total"]:.1f}/100</b></div></div>
    <div class="card panel"><h3>بطاقة التقييم المالي المطورة</h3>{fbars}<div class="small">إجمالي المالي: <b>{r["financial_total"]:.1f}/100</b></div></div></div>

    <div class="two"><div class="card panel"><h3>المؤشرات الرئيسية</h3><div class="tablewrap"><table class="table">{ratios}</table></div></div>
    <div class="card panel"><h3>IFRS 9 / ECL — تقدير إرشادي</h3>
      <div class="kpis"><div class="kpi"><small>Stage</small><b>{r["stage"]}</b></div><div class="kpi"><small>PD 12M Proxy</small><b>{r["pd12"]*100:.1f}%</b></div><div class="kpi"><small>LGD Proxy</small><b>{r["lgd"]*100:.1f}%</b></div><div class="kpi"><small>EAD</small><b>{money(r["ead"])}</b></div></div>
      <p><b>{r["stage_ar"]}</b></p><div class="kpi"><small>ECL إرشادية موزونة بالسيناريوهات</small><b>{money(r["ecl"])}</b></div>
      <p class="small">PD/LGD/ECL ليست معايرة على بيانات تاريخية للبنك ولا تمثل حساباً رقابياً نهائياً. يلزم اعتماد تعريف التعثر، SICR، CCF، LGD والسيناريوهات وفق منهجية البنك.</p>
    </div></div>

    <div class="two"><div class="card panel"><h3>نقاط القوة</h3><ul class="flags good">{strengths}</ul></div>
    <div class="card panel"><h3>استثناءات السياسة / Red Flags</h3>{severe_block}<ul class="flags">{exceptions}</ul></div></div>

    <div class="card panel" style="margin-top:14px"><h3>اختبارات الضغط متعددة العوامل</h3><div class="tablewrap"><table class="table"><tr><th>السيناريو</th><th>الوزن</th><th>الإيرادات</th><th>CFO</th><th>DSCR</th><th>احتياج WC</th><th>الحالة</th></tr>{stress}</table></div></div>

    <div class="two"><div class="card panel"><h3>شروط وضوابط مقترحة</h3><ul class="flags">{covenants}</ul></div>
    <div class="card panel"><h3>منطق القرار</h3>
      <p class="small">درجة الدراسة المرجعية: <b>{r["study_score"]:.1f}</b> • التقييم التحوطي: <b>{r["prudential_score"]:.1f}</b> • النتيجة النهائية: <b>{r["score"]:.1f}</b>.</p>
      <p class="small">القرار لا يعتمد على الدرجة وحدها. التعثر، عدم كفاية DSCR، الرفع المالي، عدم ثبوت الاحتياج، ضعف المعلومات والضمان غير القابل للتنفيذ قد تمنع الموافقة أو تستوجب إعادة هيكلة الطلب.</p>
    </div></div>

    <div class="card memo"><h3>مذكرة ائتمانية تنفيذية</h3>
      <p>يبلغ التقييم النهائي للعميل <b>{r["score"]}/100</b> بتصنيف <b>{r["code"]}</b> ودرجة مخاطر <b>{r["grade"]}</b>. الطلب يعادل <b>{m["request_assets"]*100:.1f}%</b> من إجمالي الأصول، وتصبح الرافعة المالية المتوقعة <b>{m["proforma_leverage"]:.2f}x</b>. قدرة خدمة الدين بعد التمويل تقدر عند <b>{m["proforma_dscr"]:.2f}x</b>. احتياج رأس المال العامل الخارجي المحسوب وفق دورة التشغيل يقارب <b>{money(m["external_wc_need"])}</b>. وعليه فإن الحد الإرشادي القائم على أضعف قيد بين التدفق النقدي، الاحتياج، الرافعة والضمان هو <b>{money(r["recommended_limit"])}</b>.</p>
      <p><b>التوصية:</b> {r["decision"]}. ينبغي قبل أي قرار ملزم استكمال العناية الواجبة، التحقق القانوني للضمانات، صحة البيانات، السياسة الائتمانية الداخلية، حدود الصلاحيات، ومتطلبات الجهة الرقابية.</p>
      <div class="actions"><a class="btn alt" href="/">تحليل جديد</a><button class="btn pri" onclick="window.print()">طباعة / حفظ PDF</button></div>
    </div>
    </main></html>'''

if __name__=="__main__":
    import uvicorn
    uvicorn.run(app,host="0.0.0.0",port=int(os.getenv("PORT","8080")))
