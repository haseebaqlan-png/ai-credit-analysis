from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse
import os, math, html

app = FastAPI(title='AI Credit Analysis', version='2.0.0')

def div(a,b,d=0): return d if b == 0 else a/b
def clamp(x,a=0,b=100): return max(a,min(b,x))
def score(v,bad,good,up=True):
    if good == bad: return 50
    return clamp((v-bad)/(good-bad)*100 if up else (bad-v)/(bad-good)*100)

def grade(s):
    bands=[(90,'AAA','ممتاز','منخفضة جدًا'),(82,'AA','قوي جدًا','منخفضة'),(74,'A','قوي','متوسطة-منخفضة'),(66,'BBB','جيد','متوسطة'),(58,'BB','مقبول بحذر','متوسطة-مرتفعة'),(50,'B','ضعيف نسبيًا','مرتفعة'),(40,'CCC','ضعيف','مرتفعة جدًا'),(0,'CC','حرج','حرجة')]
    for floor,g,l,r in bands:
        if s >= floor: return g,l,r

def money(x): return f'{float(x):,.0f}'

def analyze(d):
    rev=d['revenue']; ni=d['net_income']; ta=d['total_assets']; ca=d['current_assets']; cl=d['current_liabilities']
    td=d['total_debt']; eq=d['equity']; ocf=d['operating_cash_flow']; ds=d['annual_debt_service']; req=d['requested_amount']; hist=clamp(d['repayment_history_score'])
    cr=div(ca,cl,99 if ca>0 else 0); de=div(td,eq,99 if td>0 else 0); da=div(td,ta); nm=div(ni,rev); roa=div(ni,ta); dscr=div(ocf,ds,99 if ocf>0 else 0); reqa=div(req,ta); om=div(ocf,rev)
    liquidity=.7*score(cr,.75,2)+.3*score(om,0,.18)
    leverage=.55*score(de,3,.5,False)+.45*score(da,.8,.25,False)
    profit=.6*score(nm,0,.15)+.4*score(roa,0,.12)
    cash=.75*score(dscr,.8,2)+.25*(100 if ocf>0 else 0)
    capacity=.65*cash+.35*profit
    capital=.7*leverage+.3*score(eq/max(ta,1),.1,.6)
    conditions=.55*score(reqa,.75,.1,False)+.45*profit
    collateral=.6*score((ta-td)/max(req,1),.25,3)+.4*capital
    total=round(clamp(capacity*.28+capital*.18+liquidity*.14+profit*.12+hist*.14+conditions*.07+collateral*.07),1)
    g,label,risk=grade(total)
    pd=round(clamp(45*math.exp(-.045*total),.3,45),1)
    cap_ds=max(0,ocf/1.35); inc=max(0,cap_ds-ds); implied=max(0,min(req,inc*3,ta*.25))
    mult=.8 if total>=82 else .65 if total>=74 else .45 if total>=66 else .25 if total>=58 else 0
    limit=min(req,max(implied,req*mult))
    if total>=78 and dscr>=1.35 and cr>=1.2: decision,cls='مؤهل للانتقال إلى الموافقة الائتمانية','approve'
    elif total>=58 and dscr>=1: decision,cls='مراجعة ائتمانية مشروطة','review'
    else: decision,cls='مخاطر مرتفعة — لا يوصى بالموافقة حاليًا','decline'
    strengths=[]; warnings=[]
    if dscr>=1.5: strengths.append('تغطية خدمة الدين قوية.')
    if cr>=1.5: strengths.append('السيولة قصيرة الأجل مريحة.')
    if nm>=.10: strengths.append('هامش صافي الربح جيد.')
    if ocf>0 and om>=.08: strengths.append('التدفق النقدي التشغيلي موجب وملائم.')
    if de<=1: strengths.append('هيكل المديونية متحفظ.')
    if hist>=80: strengths.append('سجل السداد قوي.')
    if dscr<1: warnings.append('التدفق النقدي لا يغطي خدمة الدين.')
    elif dscr<1.25: warnings.append('هامش تغطية خدمة الدين محدود.')
    if cr<1: warnings.append('الالتزامات المتداولة تتجاوز الأصول المتداولة.')
    if de>2: warnings.append('مستوى المديونية مرتفع.')
    if nm<.03: warnings.append('هامش الربحية ضعيف.')
    if reqa>.35: warnings.append('حجم التمويل المطلوب مرتفع مقارنة بالأصول.')
    if hist<60: warnings.append('سجل السداد يحتاج إلى تحقق أعمق.')
    if not strengths: strengths=['لا توجد نقاط قوة بارزة وفق البيانات الحالية.']
    if not warnings: warnings=['لا توجد إشارات تحذير جوهرية وفق البيانات الحالية.']
    scenarios=[]
    for name,rs,os in [('أساسي',0,0),('ضغط متوسط',-.15,-.25),('ضغط شديد',-.30,-.45)]:
        x=div(ocf*(1+os),ds,99)
        scenarios.append((name,rev*(1+rs),ocf*(1+os),x,'مريح' if x>=1.35 else 'حساس' if x>=1 else 'غير مغطى'))
    return dict(score=total,grade=g,label=label,risk=risk,pd=pd,decision=decision,cls=cls,limit=limit,strengths=strengths,warnings=warnings,
        five={'القدرة Capacity':capacity,'رأس المال Capital':capital,'السمعة Character':hist,'الضمان Collateral':collateral,'الظروف Conditions':conditions},
        ratios={'نسبة التداول':cr,'الدين / حقوق الملكية':de,'الدين / الأصول':da,'هامش صافي الربح':nm,'العائد على الأصول':roa,'DSCR':dscr,'التدفق التشغيلي / الإيرادات':om},scenarios=scenarios)

STYLE = '''
*{box-sizing:border-box}body{margin:0;font-family:system-ui;background:#f4f7fb;color:#172033}header{background:linear-gradient(135deg,#0b1630,#15325e);color:#fff;padding:18px;position:sticky;top:0;z-index:5}.top,.wrap{max-width:1100px;margin:auto}.top{display:flex;justify-content:space-between;align-items:center}.brand{font-weight:900;font-size:19px}.sub{font-size:11px;color:#cbd7e8}.wrap{padding:22px 14px 45px}.card{background:#fff;border:1px solid #e5eaf0;border-radius:20px;box-shadow:0 10px 30px #0b16300b}.hero{padding:24px;background:linear-gradient(135deg,#fff 60%,#edf9f7);margin-bottom:16px}.hero b{color:#0d9488;font-size:12px}.hero h1{font-size:30px;margin:7px 0}.hero p{color:#667085;line-height:1.8}.steps{display:flex;gap:8px;overflow:auto;margin:12px 0}.step{white-space:nowrap;padding:10px 13px;border-radius:12px;border:1px solid #e5eaf0;background:#fff;font-weight:800;color:#475467}.step.on{background:#0b1630;color:#fff}.form{padding:20px}.sec{display:none}.sec.on{display:block}.grid{display:grid;grid-template-columns:1fr 1fr;gap:13px}.f label{font-size:12px;font-weight:800;color:#475467}.f input{width:100%;padding:13px;margin-top:6px;border:1px solid #d7dde7;border-radius:12px;font-size:16px}.act{display:flex;justify-content:space-between;margin-top:18px;gap:8px}.btn{padding:13px 17px;border:0;border-radius:12px;font-weight:900}.pri{background:#0b1630;color:#fff}.secbtn{background:#edf2f7}.go{background:#0d9488;color:#fff}.note{font-size:11px;color:#737d8c;line-height:1.7;margin-top:12px}.result{display:grid;grid-template-columns:.8fr 1.2fr;gap:16px}.scorebox{padding:24px;text-align:center;background:linear-gradient(145deg,#0b1630,#183866);color:#fff}.ring{width:165px;height:165px;border-radius:50%;margin:10px auto;display:grid;place-items:center;background:conic-gradient(#2dd4bf calc(var(--s)*1%),#ffffff1c 0);border:12px solid #ffffff0d}.num{font-size:44px;font-weight:950}.decision{padding:24px}.pill{display:inline-block;padding:8px 12px;border-radius:999px;font-size:12px;font-weight:900}.approve{background:#e8f8f2;color:#137657}.review{background:#fff4db;color:#8c6200}.decline{background:#fdebed;color:#a42e39}.kpis{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:16px}.kpi{padding:13px;border:1px solid #e5eaf0;border-radius:14px}.kpi small{display:block;color:#667085}.kpi b{font-size:19px}.two{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:16px}.panel{padding:20px}.metric{margin:12px 0}.mh{display:flex;justify-content:space-between;font-size:12px;font-weight:800}.bar{height:8px;background:#edf1f4;border-radius:99px;overflow:hidden;margin-top:6px}.bar i{display:block;height:100%;background:#0d9488}.table{width:100%;border-collapse:collapse;font-size:13px}.table td,.table th{padding:10px;border-bottom:1px solid #e8ebef;text-align:right}.report{margin-top:16px;padding:20px}.actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}a.btn{text-decoration:none;display:inline-block}@media(max-width:720px){.grid,.result,.two{grid-template-columns:1fr}.kpis{grid-template-columns:1fr 1fr}.hero h1{font-size:24px}}@media print{header,.actions,.steps{display:none}body{background:#fff}.card{box-shadow:none}}
'''

@app.get('/', response_class=HTMLResponse)
def home():
    return f'''<!doctype html><html lang="ar" dir="rtl"><meta name="viewport" content="width=device-width,initial-scale=1"><meta charset="utf-8"><title>AI Credit Analysis V2</title><style>{STYLE}</style><header><div class="top"><div><div class="brand">AI Credit Analysis</div><div class="sub">Credit Intelligence & Risk Decisioning Platform</div></div><div>V2.0</div></div></header><main class="wrap"><div class="card hero"><b>CREDIT INTELLIGENCE PLATFORM</b><h1>تحليل ائتماني مؤسسي قابل للتفسير</h1><p>درجة ائتمانية، 5Cs، مؤشرات مالية، قدرة خدمة الدين، حد تمويل مقترح واختبارات ضغط في مذكرة قرار واحدة.</p></div><div class="steps"><button class="step on">1. العميل</button><button class="step">2. المركز المالي</button><button class="step">3. التمويل</button><button class="step">4. السلوك</button></div><form class="card form" method="post" action="/analyze"><section class="sec on"><h3>بيانات العميل والربحية</h3><div class="grid"><div class="f"><label>اسم العميل<input name="borrower_name" value="شركة تجريبية" required></label></div><div class="f"><label>الإيرادات<input name="revenue" type="number" value="1000000" required></label></div><div class="f"><label>صافي الربح<input name="net_income" type="number" value="120000" required></label></div><div class="f"><label>إجمالي الأصول<input name="total_assets" type="number" value="900000" required></label></div></div><div class="act"><span></span><button type="button" class="btn pri next">التالي</button></div></section><section class="sec"><h3>المركز المالي والسيولة</h3><div class="grid"><div class="f"><label>الأصول المتداولة<input name="current_assets" type="number" value="400000" required></label></div><div class="f"><label>الالتزامات المتداولة<input name="current_liabilities" type="number" value="180000" required></label></div><div class="f"><label>إجمالي الدين<input name="total_debt" type="number" value="250000" required></label></div><div class="f"><label>حقوق الملكية<input name="equity" type="number" value="500000" required></label></div></div><div class="act"><button type="button" class="btn secbtn prev">السابق</button><button type="button" class="btn pri next">التالي</button></div></section><section class="sec"><h3>خدمة الدين والتمويل</h3><div class="grid"><div class="f"><label>التدفق النقدي التشغيلي<input name="operating_cash_flow" type="number" value="180000" required></label></div><div class="f"><label>خدمة الدين السنوية<input name="annual_debt_service" type="number" value="90000" required></label></div><div class="f"><label>مبلغ التمويل المطلوب<input name="requested_amount" type="number" value="150000" required></label></div></div><div class="act"><button type="button" class="btn secbtn prev">السابق</button><button type="button" class="btn pri next">التالي</button></div></section><section class="sec"><h3>السلوك الائتماني</h3><div class="grid"><div class="f"><label>سجل السداد 0–100<input name="repayment_history_score" type="number" min="0" max="100" value="85" required></label></div></div><div class="note">هذه نسخة دعم قرار تفسيري غير معايرة رقابيًا، ولا تستبدل المراجعة الائتمانية البشرية.</div><div class="act"><button type="button" class="btn secbtn prev">السابق</button><button class="btn go">تشغيل التحليل الائتماني</button></div></section></form></main><script>const s=[...document.querySelectorAll('.sec')],b=[...document.querySelectorAll('.step')];let i=0;function sh(n){{i=Math.max(0,Math.min(3,n));s.forEach((x,j)=>x.classList.toggle('on',j==i));b.forEach((x,j)=>x.classList.toggle('on',j==i));}}document.querySelectorAll('.next').forEach(x=>x.onclick=()=>sh(i+1));document.querySelectorAll('.prev').forEach(x=>x.onclick=()=>sh(i-1));b.forEach((x,j)=>x.onclick=()=>sh(j));</script></html>'''

@app.get('/health')
def health(): return {'status':'ok','version':'2.0.0'}

@app.post('/analyze',response_class=HTMLResponse)
def result(borrower_name:str=Form(...),revenue:float=Form(...),net_income:float=Form(...),total_assets:float=Form(...),current_assets:float=Form(...),current_liabilities:float=Form(...),total_debt:float=Form(...),equity:float=Form(...),operating_cash_flow:float=Form(...),annual_debt_service:float=Form(...),requested_amount:float=Form(...),repayment_history_score:float=Form(...)):
    if min(revenue,total_assets,equity,requested_amount)<=0: return HTMLResponse('<h3 dir="rtl">تحقق من القيم الأساسية.</h3>',400)
    d=locals().copy(); r=analyze(d); name=html.escape(borrower_name)
    five=''.join(f'<div class="metric"><div class="mh"><span>{k}</span><b>{v:.0f}/100</b></div><div class="bar"><i style="width:{v}%"></i></div></div>' for k,v in r['five'].items())
    rows=[]
    for k,v in r['ratios'].items():
        val=f'{v*100:.1f}%' if k in ['هامش صافي الربح','العائد على الأصول','التدفق التشغيلي / الإيرادات'] else f'{v:.2f}'
        rows.append(f'<tr><td>{k}</td><td><b>{val}</b></td></tr>')
    ratios=''.join(rows); strengths=''.join(f'<li>{x}</li>' for x in r['strengths']); warnings=''.join(f'<li>{x}</li>' for x in r['warnings'])
    stress=''.join(f'<tr><td>{n}</td><td>{money(rv)}</td><td>{money(o)}</td><td>{x:.2f}</td><td><b>{z}</b></td></tr>' for n,rv,o,x,z in r['scenarios'])
    return f'''<!doctype html><html lang="ar" dir="rtl"><meta name="viewport" content="width=device-width,initial-scale=1"><meta charset="utf-8"><title>نتيجة التحليل</title><style>{STYLE}</style><header><div class="top"><div class="brand">AI Credit Analysis</div><div>Credit Memo V2</div></div></header><main class="wrap"><div class="result"><div class="card scorebox"><div>الدرجة الائتمانية</div><div class="ring" style="--s:{r['score']}"><div><div class="num">{r['score']}</div><small>من 100</small></div></div><h2>{r['grade']} • {r['label']}</h2><div>المخاطر: {r['risk']}</div></div><div class="card decision"><span class="pill {r['cls']}">{r['decision']}</span><h1>{name}</h1><p>ملخص تفسيري للمركز المالي والتدفقات والرفع المالي وسجل السداد.</p><div class="kpis"><div class="kpi"><small>PD إرشادية*</small><b>{r['pd']}%</b></div><div class="kpi"><small>الحد المقترح</small><b>{money(r['limit'])}</b></div><div class="kpi"><small>الطلب</small><b>{money(requested_amount)}</b></div></div><div class="note">*تقدير داخلي إرشادي غير معاير رقابيًا.</div></div></div><div class="two"><div class="card panel"><h3>5Cs of Credit</h3>{five}</div><div class="card panel"><h3>المؤشرات المالية</h3><table class="table">{ratios}</table></div></div><div class="two"><div class="card panel"><h3>نقاط القوة</h3><ul>{strengths}</ul></div><div class="card panel"><h3>الإشارات التحذيرية</h3><ul>{warnings}</ul></div></div><div class="card panel" style="margin-top:16px"><h3>اختبار الضغط</h3><div style="overflow:auto"><table class="table"><tr><th>السيناريو</th><th>الإيرادات</th><th>التدفق</th><th>DSCR</th><th>الحالة</th></tr>{stress}</table></div></div><div class="card report"><h3>مذكرة ائتمانية مختصرة</h3><p style="line-height:1.9">العميل مصنف <b>{r['grade']}</b> بدرجة <b>{r['score']}/100</b> ومخاطر <b>{r['risk']}</b>. القرار المقترح: <b>{r['decision']}</b>. الحد التمويلي الإرشادي يقارب <b>{money(r['limit'])}</b> من طلب قدره <b>{money(requested_amount)}</b>. يجب استكمال التحقق من الضمانات والغرض من التمويل والسياسات الداخلية قبل القرار النهائي.</p><div class="actions"><a class="btn secbtn" href="/">تحليل جديد</a><button class="btn pri" onclick="window.print()">طباعة / حفظ PDF</button></div></div></main></html>'''

if __name__=='__main__':
    import uvicorn
    uvicorn.run(app,host='0.0.0.0',port=int(os.getenv('PORT','8080')))
