# نتائج فحص المصادر (First task, items 3-5 من AFAQ_MASTER_SPEC.md)

تم هذا الفحص فعليًا عبر أدوات بحث وجلب ويب حقيقية في هذه الجلسة بتاريخ 2026-10-03، وليس استنتاجًا
من الذاكرة. الروابط والاقتباسات أدناه حقيقية.

## Quranpedia.net — ✅ آلية وصول مسموحة وموثّقة بوضوح

- **التوثيق الكامل:** `https://quranpedia.net/api-docs` — واجهة REST عامة بلا مصادقة، قاعدتها
  `https://api.quranpedia.net/v1`.
- **الترخيص:** `https://quranpedia.net/dumps/LICENSE.md` — استخدام حي داخل التطبيقات مجاني بلا
  اشتراط نسب؛ النسب واجب فقط عند نشر البيانات نفسها كمجموعة بيانات قابلة للتنزيل.
- **سياسة الاستخدام (مهمة جدًا لالتزام المستند بعدم الزحف الأعمى):** النص الحرفي من الصفحة:
  "Do not bulk-scrape and republish... This API is not a download service... Need the full dataset?
  Don't scrape — download the official versioned dumps (gzipped JSON with SHA-256 checksums), then
  stay current with the changes endpoint." وحدّ المعدل: 120 طلب/دقيقة و10,000/يوم.
- **أهم المسارات المستخدَمة في هذا المشروع:**
  - `GET /mushafs/{mushaf_id}/{surah_id}` و `/{ayah_number}` — نص الآيات (المصحف 1 = حفص).
  - `GET /surah/tafsirs/{surah_id}` — كتب التفسير المتاحة لسورة.
  - `GET /ayah/{surah}/{ayah}/book/{book_id}` — نص التفسير الفعلي من كتاب محدد لآية محددة،
    بما يشمل المؤلف واسم الكتاب (provenance جاهزة).
  - `GET /changes?since=` — مزامنة التصحيحات بدل إعادة الزحف الكامل.
- **القرار:** هذا المصدر كافٍ لتغطية "نص القرآن" وجزء كبير من "التفسير" في المرحلة الأولى بآلية
  وصول رسمية موثّقة بالكامل، مطابقة تمامًا لما يطلبه المستند ("prefer official APIs... do not
  blindly mirror entire copyrighted sites").

## Dorar.net — ⚠️ لم يُثبَت وجود (أو غياب) آلية وصول آلية مكافئة بعد

- تم تنفيذ عدة عمليات بحث عن `dorar.net/tafseer/`, `dorar.net/article/1955`,
  و`dorar.net/refs/tafseer` تحديدًا، ولم تُظهر نتائج البحث المتاحة لهذه الجلسة صفحات Dorar.net نفسها
  (ظهرت مواقع أخرى تحمل اسمًا مشابهًا مثل "الدرر السنية — dorar.net/en" في سياق مختلف تمامًا وهو
  اتحاد الدرر السنية — **لم يتم التحقق مما إذا كان هذا هو نفس الموقع المقصود في المواصفة أو موقع
  مختلف يحمل نطاقًا شبيهًا**؛ هذا بحد ذاته أمر يجب توضيحه قبل أي استيعاب).
- أداة `web_fetch` المتاحة هنا لا تفتح رابطًا لم يظهر أولًا في نتيجة بحث، فلم يكن ممكنًا فتح
  `dorar.net/article/1955` مباشرة للتحقق من منهجية الموقع كما يطلب المستند بالضبط.
- **لم يُبنَ أي مستوعب آلي لـ Dorar.net بناءً على ذلك** — التزامًا الحرفي بالمستند: "do not blindly
  scrape... build a documented adapter rather than bypassing restrictions."

### الإجراء المطلوب من Claude Code (بشبكة فعلية) قبل أي استيعاب من Dorar
1. تأكيد الرابط الصحيح والمقصود فعليًا (هل هو dorar.net كما هو، أم نطاق فرعي/خدمة تفسير محددة؟).
2. فتح `/robots.txt` وقراءته.
3. فتح `/tafseer/`, `/article/1955`, `/refs/tafseer` وتوثيق: هل توجد API؟ هل توجد صفحة شروط استخدام؟
   هل يوجد تصدير بيانات رسمي؟
4. توثيق القرار في هذا الملف قبل كتابة أي كود استيعاب.

## ما يترتب على ذلك معماريًا
نموذج `Source` في `models.py` عام بما يكفي لإضافة Dorar (أو أي مصدر تفسير آخر) لاحقًا دون أي تعديل
بنيوي — فقط عميل جديد شبيه بـ `quranpedia_client.py` ونموذج استيعاب موازٍ لـ `ingest_tafsir.py`. هذا
يحقق صراحة بند "new sources can be added without redesigning the entire system" في تعريف الإنجاز.
