# AI Credit Analysis V3 — Bank-Grade Decision Support

الإصدار الثالث يطوّر المشروع من نموذج scoring بسيط إلى مسار اكتتاب ائتماني مؤسسي قابل للتفسير.

## ما الذي تغير في V3؟
- هيكل تحليلي مستفاد من دراسة ائتمانية بنكية فعلية: النشاط، رأس المال العامل، هيكل رأس المال، الإدارة/السلوك، التحليل المالي، الضمانات، المخاطر والتوصية.
- فصل **الدرجة الائتمانية** عن **بوابات السياسة** حتى لا تؤدي الضمانات أو الدرجة المرتفعة إلى تجاوز ضعف قدرة السداد.
- تحليل دورة رأس المال العامل: DSO / DIO / DPO / Financing Gap / External Working Capital Need.
- تحليل Pro-forma بعد التمويل: DSCR والرافعة وحجم الطلب إلى الأصول.
- Loan sizing بأضعف قيد: cash-flow capacity، working-capital need، leverage limit، collateral-adjusted limit.
- Collateral module: haircut، legal enforceability، valuation age، adjusted coverage.
- Qualitative scorecard: السوق، التركز، FX، الإدارة، الحوكمة، التعاقب، السلوك، مركزية المخاطر.
- Data Quality score واستثناءات سياسة تلقائية.
- Stress testing بثلاثة سيناريوهات.
- IFRS 9-style staging وPD/LGD/EAD/ECL **كمؤشرات إرشادية غير معايرة**.
- Credit memo قابل للطباعة / الحفظ PDF.
- JSON API: `POST /api/analyze`.
- Health endpoint: `/health`.

## مبادئ دولية مرجعية
- Basel Committee, Principles for the Management of Credit Risk (30 Apr 2025):
  https://www.bis.org/bcbs/publ/d595.htm
- Basel Framework — Credit Risk Mitigation:
  https://www.bis.org/basel_framework/chapter/CRE/22.htm
- Basel Framework — IRB risk components PD/LGD/EAD/M:
  https://www.bis.org/basel_framework/chapter/CRE/32.htm
- IFRS 9 Financial Instruments:
  https://www.ifrs.org/issued-standards/list-of-standards/ifrs-9-financial-instruments/
- IFRS 9 implementation support:
  https://www.ifrs.org/supporting-implementation/supporting-materials-by-ifrs-standards/ifrs-9/

## تنبيه منهجي مهم
هذا النظام **دعم قرار** وليس نظام تصنيف رقابي معتمداً. PD/LGD/ECL والحدود والعتبات تحتاج:
1. معايرة على بيانات التعثر والتحصيل التاريخية للبنك.
2. Validation مستقلة وBack-testing.
3. اعتماد Credit Policy / Model Risk / Compliance.
4. مواءمة مع تعليمات البنك المركزي والجهة الرقابية المختصة.
5. Governance للتحكم بالإصدارات، overrides، audit trail، والصلاحيات.

## Railway
نفس إعدادات الإصدار السابق تكفي. وجود Dockerfile يجعل Railway يبني التطبيق تلقائياً، والتطبيق يستمع على `$PORT`.
