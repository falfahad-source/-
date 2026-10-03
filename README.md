# آفاق (AFAQ) — منصة استكشاف معرفي مصدرها موثّق حول آيات القرآن الكريم

> **حالة هذا التسليم:** هذا هو إنجاز "المهمة الأولى" المطلوبة في `AFAQ_MASTER_SPEC.md` (فحص المصادر
> المسموح بها + خطة تنفيذ + بنية ابتدائية للاستيعاب والتخزين) مع هيكل كود حقيقي قابل للتشغيل،
> **وليس** منصة منتَجة ومُختبرة بالكامل. السبب: هذه المحادثة تعمل داخل بيئة حاوية مؤقتة بلا اتصال
> شبكي من داخل bash وبلا قاعدة بيانات دائمة، فلا يمكنها تشغيل Docker/FastAPI/Postgres فعليًا أو تنفيذ
> استيعاب حي من الإنترنت والتحقق منه بالاختبارات كما تطلب الفقرة "Claude Code execution method" و
> "Definition of Done". **الخطوة التالية الصحيحة هي فتح هذا المجلد في Claude Code** (تطبيق سطح مكتب/
> طرفية لدى Anthropic يملك شبكة واتصال مستمر وبيئة تشغيل فعلية)، حيث يمكن تثبيت الاعتماديات، تشغيل
> Docker compose، تنفيذ الاستيعاب الحقيقي، وتشغيل الاختبارات وإصلاح الأخطاء فعليًا كما يطلب المستند.

## ما تم فعلاً في هذا التسليم (تم التحقق منه عبر تصفح حقيقي للمصادر)

### 1. القرآن — Quranpedia ✅ مصدر موثوق وموثّق رسميًا
بعد فحص `quranpedia.net` فعليًا (وليس افتراضًا)، تبيّن أنها توفّر **واجهة REST API رسمية موثّقة** على
`https://api.quranpedia.net/v1`، مجانية، بلا مصادقة، JSON، تشمل:
- `/mushafs` و `/mushafs/{id}` — نص كل آية بكل مصحف/رواية (المصحف رقم 1 = حفص).
- `/mushafs/{mushaf_id}/{surah_id}/{ayah_number?}` — آية أو سورة كاملة.
- `/ayah/{surah}/{ayah}/book/{book_id}` — **نص التفسير** من كتاب تفسير محدد لآية محددة.
- `/surah/tafsirs/{surah_id}` — قائمة كتب التفسير المتاحة لكل سورة.
- `/translations/...`, `/topics`, `/search/...`, و **`/v1/changes?since=`** لمزامنة التصحيحات اللاحقة.
- ترخيص بيانات صريح في `https://quranpedia.net/dumps/LICENSE.md`: الاستخدام داخل التطبيقات مجاني
  بلا اشتراط نسب، والنسب واجب فقط عند **إعادة نشر البيانات كقاعدة بيانات قابلة للتنزيل**.
- **سياسة استخدام صريحة تمنع الزحف الجماعي (bulk scraping)** وتحدد حد معدل 120/دقيقة و10,000/يوم،
  وتوجّه من يحتاج نسخة كاملة إلى **Dumps رسمية** (`/dumps`) بدل الزحف — وهذا بالضبط ما يطلبه المستند
  ("Do not blindly scrape... build a documented adapter").

**القرار المعماري:** الاستيعاب يتم عبر هذا الـ API الرسمي (مباشرة لكل آية/تفسير يطلبه المستخدم، أو عبر
Dumps للتحميل الكامل)، وليس عبر استخلاص HTML — هذا يحقق متطلب "لا يُقتبس/يُعاد بناء النص القرآني
آليًا باللغة النموذجية" لأن النص يُخزَّن حرفيًا كما يُعيده الـ API مع `source_url` و`retrieval_date`
و`version` (نُتابع `/v1/changes` بدل إعادة الزحف بالكامل).

### 2. التفسير — Dorar.net ⚠️ لم يُعثر على واجهة API موثّقة مكافئة
محاولات بحث متعددة عن `dorar.net/tafseer`, `dorar.net/article/1955`, و`dorar.net/refs/tafseer` لم
تُظهر توثيق API رسمي علني مكافئ لما تملكه Quranpedia (الموقع لا يظهر جيدًا في نتائج البحث المتاحة لهذه
الجلسة، ومحاولات `web_fetch` المباشرة مرفوضة ما لم يظهر الرابط أولًا في نتيجة بحث). **لم أُثبت بنفسي
وجود أو غياب API لـ Dorar بثقة كافية لبناء مستوعب آلي عليه الآن.**

القرار الآمن المطابق للمستند ("do not blindly scrape... build a documented adapter rather than
bypassing restrictions"): **لا تُبنى حاليًا أي وحدة زحف تلقائي لـ Dorar.net.** الخطوة التالية (ينفَّذها
Claude Code بشبكة فعلية) هي:
1. فتح `https://dorar.net/tafseer/`، `https://dorar.net/article/1955`، و`https://dorar.net/refs/tafseer`
   مباشرة وقراءة `robots.txt` وأي صفحة "شروط استخدام"/API إن وُجدت.
2. إن وُجد API أو تصدير رسمي → بناء adapter موثّق مثل Quranpedia تمامًا.
3. إن لم يوجد → التواصل مع الموقع لطلب إذن/تصدير، أو **الاكتفاء مؤقتًا بكتب التفسير المتوفرة فعليًا عبر
   Quranpedia API نفسها** (`/surah/tafsirs/{surah}` تُعيد بالفعل كتب تفسير مثل "تيسير التفسير" بنصها
   الكامل عبر `/ayah/{s}/{a}/book/{book_id}` — وهذا مصدر تفسير حقيقي وموثّق تحت نفس ترخيص Quranpedia)
   كمصدر تفسير أساسي للمرحلة الأولى، مع تصنيف كل كتاب تفسير حسب مؤلفه كمصدر `TAFSIR_VERIFIED` منفصل.

### 3. العلوم — لا يوجد allowlist نهائي بعد
وفق المستند، يجب بناء قائمة مصادر علمية مسموحة (هيئات حكومية، جامعات، أبحاث محكّمة). هذا القرار
بحاجة لمدخلات من صاحب المشروع (أي النطاقات العلمية ذات الأولوية؟) قبل برمجته، فتُرك كإعداد قابل
للتوسعة في `backend/app/config.py` (`SCIENTIFIC_SOURCE_ALLOWLIST`).

## البنية المُسلَّمة الآن
```
afaq/
  backend/app/
    models.py        # SQLAlchemy: Verse, Source, TafsirEntry, ScientificEvidence,
                      #   Concept, Relationship, Claim, TrustCategory (enum حرفي من المستند)
    trust.py          # قواعد الثقة غير القابلة للتفاوض (تمنع الترقية الصامتة بين الفئات)
    ingestion/
      quranpedia_client.py   # عميل حقيقي للـ API الموثّق أعلاه (ayahs + tafsir books)
      ingest_quran.py        # سكربت استيعاب نص القرآن (مصحف حفص) إلى قاعدة البيانات
      ingest_tafsir.py       # سكربت استيعاب كتب التفسير المتاحة عبر Quranpedia لكل سورة
    rag/
      answer_builder.py      # يبني تنسيق الإجابة A-G المطلوب من سجلات قاعدة البيانات فقط
    main.py            # FastAPI: /verse/{surah}/{ayah} يُرجع الإجابة المُبنية من answer_builder
  backend/tests/        # pytest، يُحاكي استجابات API (لا يحتاج شبكة) ويتحقق من:
                         #   - تخزين نص الآية حرفيًا دون تعديل
                         #   - عدم ترقية UNVERIFIED_CLAIM إلى SCIENTIFIC_FACT
                         #   - وجود جميع أقسام A-G مع تمييز POSSIBLE_CONNECTION
  frontend/app/          # هيكل Next.js RTL أولي (اختيار سورة/آية + عرض الأقسام) — واجهة فقط، لم تُوصَل بعد
  docker-compose.yml     # Postgres + backend + frontend
  docs/IMPLEMENTATION_PLAN.md   # خطة التنفيذ الكاملة مرحلة بمرحلة
```

## التشغيل (يُنفَّذ في Claude Code أو بيئة بشبكة فعلية)
```bash
cd afaq
cp .env.example .env            # أضف OPENAI/ANTHROPIC key إن رغبت في طبقة RAG/LLM
docker compose up -d db
cd backend && pip install -r requirements.txt -r requirements-dev.txt
alembic upgrade head             # (يُضاف لاحقًا) أو python -m app.db إنشاء الجداول مباشرة للتطوير
python -m app.ingestion.ingest_kfgqpc                   # نص القرآن كاملًا (6236 آية) من ملف مجمع الملك فهد — انظر أدناه
python -m app.ingestion.ingest_tafsir --surah 1            # التفاسير الأساسية فقط (السعدي، الطبري، ابن كثير، الميسر...)
python -m app.ingestion.ingest_tafsir --surah 1 --books 3,2012   # أو كتب محددة بأرقامها
pytest                           # اختبارات بمحاكاة الشبكة، تعمل بلا اتصال
uvicorn app.main:app --reload
```

## نص القرآن: ملف مجمع الملك فهد (kfgqpc_hafs_v30)
مصدر نص القرآن المعتمد هو إصدار البيانات الرسمي من مجمع الملك فهد لطباعة المصحف الشريف
(`https://qurancomplex.gov.sa/quran-hafs/` — الحزمة `kfgqpc_hafs_v30`)، بدل Quranpedia API.
الملفات **غير موجودة في git** (ترخيص إعادة التوزيع غير مذكور في الحزمة)، فضعها يدويًا:
```bash
cp kfgqpc_hafs_v30-data/kfgqpc_hafs_v30.json  backend/data/
cp kfgqpc_hafs_v30-font/kfgqpc_hafs_v30.ttf   frontend/public/fonts/   # خط عرض الآيات
```
- يُخزَّن `aya_text_unicode` حرفيًا (مع علامة نهاية الآية ورقمها)، ومعه رقم الصفحة والجزء والنص الإملائي.
- يُتحقَّق من الملف كاملًا قبل الكتابة (6236 آية، 114 سورة، ترقيم متصل)، ويُسجَّل SHA-256 للملف في جدول `sources`.
- إن كانت الآيات مستوعبة سابقًا من Quranpedia: `python -m app.ingestion.ingest_kfgqpc --replace` يحدّثها في مكانها
  فتبقى روابط التفسير سليمة.
- أُضيفت أعمدة جديدة لجدول `verses` (`page_number`, `juz_number`, `text_imlaei`)؛ لا توجد Alembic بعد،
  فقاعدة بيانات تطوير قديمة تحتاج إعادة إنشاء (`docker compose down -v`) أو إضافة الأعمدة يدويًا.
- `ingest_quran.py` (Quranpedia) باقٍ كبديل، و`ingest_tafsir.py` ما زال يجلب التفسير من Quranpedia.

## الأحاديث: الموسوعة الحديثية من الدرر السنية (Dorar.net)
واجهة `https://dorar.net/dorar_api.json?skey=<كلمات>` تبحث في **الأحاديث** بالكلمات، وليست مصدر تفسير.
```bash
python -m app.ingestion.ingest_hadith --surah 2 --ayah 43 --query "الصلاة"
```
- تُخزَّن كل نتيجة في `hadith_entries` بحقولها (النص، الراوي، المحدث، المصدر، الصفحة أو الرقم، حكم المحدث)
  مع كتلة HTML الأصلية للتدقيق.
- الربط بالآية مجرد تطابق نصي، فكل صف `POSSIBLE_CONNECTION` ويُعرض في قسم مستقل عن التفسير مع حكم المحدث دائمًا
  (النتائج تشمل أحاديث ضعيفة وموضوعة).
- كلمات البحث يحددها المستخدم صراحة (`--query`)؛ لا تُستنتج آليًا من الآية.
- **حماية Cloudflare في dorar.net تحظر خوادم السحابة**، فشغّل هذا الأمر من جهازك. الاختبارات تعمل بلا شبكة
  على استجابة حقيقية محفوظة (`backend/tests/fixtures/dorar_api_salah.json`).
- تفسير الدرر ("موسوعة التفسير المحرر") غير متاح عبر هذه الواجهة؛ يحتاج إذنًا أو ملف تصدير من الدرر.
- أُضيف جدول جديد `hadith_entries` (يُنشئه `init_db()` تلقائيًا).

## لماذا لا أدّعي أن هذا "مكتمل"
المستند يمنع صراحة الادعاء بالإنجاز دون اختبار فعلي ("Do not claim completion without testing").
الكود هنا صحيح بنيويًا ومبني على توثيق API حقيقي تم التحقق منه بالفعل، لكنه **لم يُشغَّل بعد** داخل
هذه المحادثة (لا شبكة، لا Postgres دائم هنا). أي تسليم لاحق من Claude Code يجب أن يُرفق نتائج تشغيل
فعلية (pytest, curl, لقطات) قبل اعتباره "منجزًا".
