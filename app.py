from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse
import os

app = FastAPI(title="AI Credit Analysis", version="0.2.0")

HTML = """
<!doctype html><html lang="ar" dir="rtl"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI Credit Analysis</title>
<style>
body{font-family:system-ui;background:#f5f7fa;color:#172033;margin:0}.w{max-width:760px;margin:auto;padding:14px}
.c{background:#fff;padding:16px;border-radius:16px;margin:14px 0;box-shadow:0 2px 14px #0001}
.g{display:grid;grid-template-columns:1fr 1fr;gap:10px}label{font-size:13px;color:#475467}
input{width:100%;box-sizing:border-box;padding:12px;margin-top:5px;border:1px solid #ccc;border-radius:10px;font-size:16px}
button,a.btn{width:100%;box-sizing:border-box;padding:14px;background:#172033;color:#fff;border:0;border-radius:11px;font-size:17px;font-weight:700;margin-top:12px;text-decoration:none;display:block;text-align:center}
.score{text-align:center;font-size:54px;font-weight:800}@media(max-width:620px){.g{grid-template-columns:1fr}}
</style></head><body><div class="w"><div class="c"><h1>AI Credit Analysis</h1>
<p>تحليل ائتماني أولي قابل للمراجعة</p>
<form method="post" action="/analyze"><div class="g">
<label>اسم العميل<input name="borrower_name" value="شركة تجريبية" required></label>
<label>الإيرادات<input name="revenue" type="number" step="any" value="1000000" required></label>
<label>صافي الربح<input name="net_income" type="number" step="any" value="120000" required></label>
<label>إجمالي الأصول<input name="total_assets" type="number" step="any" value="900000" required></label>
<label>الأصول المتداولة<input name="current_assets" type="number" step="any" value="400000" required></label>
<label>الالتزامات المتداولة<input name="current_liabilities" type="number" step="any" value="180000" required></label>
<label>إجمالي الدين<input name="total_debt" type="number" step="any" value="250000" required></label>
<label>حقوق الملكية<input name="equity" type="number" step="any" value="500000" required></label>
<label>التدفق النقدي التشغيلي<input name="operating_cash_flow" type="number" step="any" value="180000" required></label>
<label>خدمة الدين السنوية<input name="annual_debt_service" type="number" step="any" value="90000" required></label>
<label>مبلغ التمويل المطلوب<input name="requested_amount" type="number" step="any" value="150000" required></label>
<label>سجل السداد 0-100<input name="repayment_history_score" type="number" step="any" min="0" max="100" value="85" required></label>
</div><button>تحليل الائتمان</button></form>
<p style="font-size:12px;color:#667085">هذه أداة دعم قرار تجريبية وليست موافقة ائتمانية آلية.</p>
</div></div></body></html>
"""

def div(a,b): return 0 if b == 0 else a/b
def clamp(x): return max(0,min(100,x))
def s(v,bad,good,up=True):
    if good == bad: return 50
    return clamp(((v-bad)/(good-bad)*100) if up else ((bad-v)/(bad-good)*100))

@app.get("/", response_class=HTMLResponse)
def home(): return HTML

@app.get("/health")
def health(): return {"status":"ok","version":"0.2.0"}

@app.post("/analyze", response_class=HTMLResponse)
def analyze(
    borrower_name:str=Form(...), revenue:float=Form(...), net_income:float=Form(...),
    total_assets:float=Form(...), current_assets:float=Form(...),
    current_liabilities:float=Form(...), total_debt:float=Form(...), equity:float=Form(...),
    operating_cash_flow:float=Form(...), annual_debt_service:float=Form(...),
    requested_amount:float=Form(...), repayment_history_score:float=Form(...)
):
    if min(revenue,total_assets,equity,requested_amount) <= 0:
        return HTMLResponse("<h3 dir='rtl'>تحقق من القيم الأساسية؛ يجب أن تكون أكبر من صفر.</h3><a href='/'>رجوع</a>",400)
    cr=div(current_assets,current_liabilities)
    de=div(total_debt,equity)
    dr=div(total_debt,total_assets)
    margin=div(net_income,revenue)
    roa=div(net_income,total_assets)
    dscr=div(operating_cash_flow,annual_debt_service)
    req=div(requested_amount,total_assets)

    financial=s(roa,0,.12)*.6+s(req,.75,.10,False)*.4
    leverage=s(de,3,.5,False)*.55+s(dr,.8,.25,False)*.45
    liquidity=s(cr,.8,2)
    profitability=s(margin,0,.15)*.55+s(roa,0,.12)*.45
    cashflow=s(dscr,.8,2)*.75+(100 if operating_cash_flow>0 else 0)*.25
    score=round(financial*.25+leverage*.20+liquidity*.15+profitability*.15+cashflow*.15+repayment_history_score*.10,2)

    if score>=90: grade,risk="AAA","مخاطر منخفضة جدًا"
    elif score>=80: grade,risk="AA","مخاطر منخفضة"
    elif score>=70: grade,risk="A","مخاطر متوسطة-منخفضة"
    elif score>=60: grade,risk="BBB","مخاطر متوسطة"
    elif score>=50: grade,risk="BB","مخاطر مرتفعة نسبيًا"
    elif score>=40: grade,risk="B","مخاطر مرتفعة"
    else: grade,risk="CCC","مخاطر مرتفعة جدًا"

    strengths=[]; warnings=[]
    if dscr>=1.5: strengths.append("تغطية خدمة الدين قوية")
    if cr>=1.5: strengths.append("السيولة الجارية جيدة")
    if margin>=.10: strengths.append("هامش صافي الربح جيد")
    if operating_cash_flow>0: strengths.append("التدفق النقدي التشغيلي موجب")
    if dscr<1: warnings.append("تغطية خدمة الدين أقل من 1.0")
    if de>2: warnings.append("المديونية مرتفعة مقارنة بحقوق الملكية")
    if cr<1: warnings.append("الالتزامات المتداولة تتجاوز الأصول المتداولة")
    if net_income<0: warnings.append("العميل يحقق خسارة صافية")

    rec="الانتقال إلى المراجعة الائتمانية البشرية" if score>=70 else ("مراجعة موسعة وضمانات إضافية مطلوبة" if score>=50 else "مخاطر مرتفعة؛ لا يُنصح بالموافقة دون مبررات استثنائية موثقة")
    st="".join(f"<li>{x}</li>" for x in strengths) or "<li>لا توجد نقاط محددة</li>"
    wa="".join(f"<li>{x}</li>" for x in warnings) or "<li>لا توجد تحذيرات محددة</li>"
    return f"""<!doctype html><html lang='ar' dir='rtl'><meta name='viewport' content='width=device-width,initial-scale=1'>
    <style>body{{font-family:system-ui;background:#f5f7fa;color:#172033}}.w{{max-width:760px;margin:auto;padding:14px}}.c{{background:#fff;padding:18px;border-radius:16px;margin:14px 0}}.score{{font-size:58px;font-weight:800;text-align:center}}a{{display:block;text-align:center;padding:13px;background:#172033;color:#fff;text-decoration:none;border-radius:10px}}</style>
    <div class='w'><div class='c'><div class='score'>{score}</div><h2 style='text-align:center'>{grade} · {risk}</h2></div>
    <div class='c'><h3>التوصية</h3><p>{rec}</p><h3>نقاط القوة</h3><ul>{st}</ul><h3>التحذيرات</h3><ul>{wa}</ul>
    <p><b>نسبة التداول:</b> {round(cr,2)}</p><p><b>الدين/حقوق الملكية:</b> {round(de,2)}</p><p><b>DSCR:</b> {round(dscr,2)}</p></div>
    <a href='/'>تحليل عميل آخر</a></div></html>"""

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app,host="0.0.0.0",port=int(os.getenv("PORT","8000")))
