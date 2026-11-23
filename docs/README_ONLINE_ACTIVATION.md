# التفعيل عبر الإنترنت (Firebase) – خطوات التركيب

## 1) إعداد Firebase (تم إنشاؤه: المشروع maria-licenses، والقواعد منشورة)
يبقى فقط تنزيل ملف الحساب الخدمي (الخطوة 5).
1. أنشئ مشروعاً جديداً في https://console.firebase.google.com (الخطة المجانية Spark تكفي، لا حاجة لبطاقة).
2. Build ثم Firestore Database ثم Create database (اختر أي موقع، وضع Production).
3. Firestore ثم Rules: الصق محتوى الملف firebase/firestore.rules ثم Publish.
4. Project settings ثم General: انسخ Project ID و Web API Key.
5. Project settings ثم Service accounts ثم Generate new private key: احفظ الملف في
   `%USERPROFILE%\MariaKeys\firebase_service_account.json` (سري، لا يُرفع إلى GitHub).

## 2) تعديل البرنامج (نسخة MFD)
- انسخ الملفات التالية إلى مجلد app في المستودع (استبدل الموجود):
  online_activation.py, online_config.py, main.py, licensing.py, i18n.py
- ملف app/online_config.py معبّأ مسبقاً بـ Project ID و Web API Key.
- ابنِ المثبّت من جديد (GitHub Actions).

## 3) توليد الرموز للأقراص
```
pip install firebase-admin
python tools/serial_batch.py --count 50 --batch "Disc batch 1"
```
يُنشئ ملف serial_codes_*.csv فيه الرموز لطباعتها (مثل MFD-ABCDE-FGHIJ-KLMNO-PQRST).

## كيف يعمل
- الرمز غير مستخدم: يُربط بجهاز الزبون ويُقبل (ثم يعمل البرنامج دون إنترنت).
- نفس الجهاز يعيد التثبيت: يُقبل.
- جهاز آخر: تظهر رسالة أن الرمز مستخدم.
- الطريقة القديمة (سيريال طويل من رقم الجهاز عبر واتساب) تبقى تعمل كاحتياط.
