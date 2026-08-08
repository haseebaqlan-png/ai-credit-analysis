# AI Credit Analysis MVP 1.0 — Mobile Upload Edition

هذه النسخة مخصصة للرفع من الهاتف. لا ترفع أي مجلدات.

## ارفع هذه الملفات الخمسة فقط إلى جذر GitHub
- main.py
- Dockerfile
- requirements.txt
- README.md
- SECURITY.md

`main.py` يحتوي داخله على قاعدة التطبيق، الواجهة، قوالب HTML، CSS، محرك الاستخراج، محرك التحليل الائتماني وإخراج PDF. عند التشغيل ينشئ المجلدات التشغيلية تلقائياً.

## وظائف MVP
تسجيل مستخدم، العملاء، طلبات التمويل، رفع القوائم، استخراج البيانات، Verification، أكثر من 20 نسبة مالية، Trend Analysis، Credit Score، Risk Analysis، Credit Memo، PDF، بنية API Cost، Dashboard.

## Railway
أضف متغيراً واحداً على الأقل:
`APP_SECRET=<قيمة عشوائية طويلة>`

لا يحتاج `OPENAI_API_KEY`.

ملاحظة: SQLite والتخزين المحلي مناسبان لمرحلة الاختبار. قبل الإنتاج سننقل PostgreSQL والتخزين الدائم.
