# SWYF Koç — Scam With Your Friends için canlı İngilizce konuşma koçu

Windows'ta oyunun üstünde duran yarı saydam, **her zaman üstte** bir pencere. Bilgisayarın **sistem sesini** dinler,
oyundaki yapay zekâ arayanın İngilizce konuşmasını anında yazıya döker, **hangi karakter olduğunu**, **kaçıncı
hafta / gün** olduğunu, **hangi dolandırıcılık uygulamalarının açık** olduğunu ve **kotaya ne kadar kaldığını**
hesaba katarak senin mikrofona okuyacağın **tam İngilizce cümleyi** (altında kısa Türkçe strateji notuyla) gösterir.

![Overlay örneği](docs/overlay_demo.png)

> Bu, Steam'deki *Scam With Your Friends* (JakeHub & Metater, Erken Erişim 15 Ekim 2026) oyunu için bir oyun
> yardımcısıdır. Oyundaki arayanlar yapay zekâ ile seslendirilen kurgusal karakterlerdir; para da oyun içi paradır.

---

## Ne yapar?

| Özellik | Açıklama |
|---|---|
| 🎧 **Sistem sesini dinler** | WASAPI loopback (PyAudioWPatch / soundcard). Oyunun hoparlör/kulaklık çıkışını yakalar, mikrofonuna dokunmaz. |
| 📝 **Anlık yazıya döker** | `faster-whisper` (yerel, GPU varsa GPU) — internet gerekmez. Yedek: Google Speech. |
| 🎭 **Karakteri tanır** | İsimden ("this is Dorothy"), anahtar kelimeden ("1999 Nissan Forza" → Kenzo), ekran okumadan (OCR) ya da elle. Tanınmayan rastgele arayanlar için konuşmadan **arketip** (güvenen / şüpheci / baskı altında / ego / açgözlü / scambaiter…) ve **sorun konusu** çıkarır. |
| 💰 **En kârlı zinciri seçer** | O gün açık + satın alınmış uygulamalar arasından, karaktere uygunluk × ödül ÷ süre puanıyla tek arayana zincirlenecek dolandırıcılık planı yapar (ör. *Warranty → Credit Card → SSN → Gift Card*). "Tuttuğunu bırakma" mantığı: aynı arayandan dibine kadar. |
| ✅ **Kontrol listesini takip eder** | Her uygulamanın checklist adımlarını bilir; arayanın cevabından adımın tamamlandığını anlar (ör. "I love you" → Romance 4. adım), arayan öne geçerse adımları atlar. |
| 🗣 **Okunacak cümle** | Karaktere ve dil seviyesine göre (B1 / C1 / C2) cümle; itiraz gelirse (şüphe, "neden hediye çeki?", "param yok", öfke…) itiraz cevabı. Tekrara düşmemek için cümleleri döndürür (F9 alternatif). |
| 🔢 **Kodları büyük gösterir** | Arayan hediye çeki kodu / kart no / SSN / e-posta / tutar okuduğunda (sözle okunan "four four one seven" dahil) yeşil, büyük yazar → sen uygulamaya yazarsın. |
| ⏱ **Zaman & kota yönetimi** | "2 dk kaldı, $200 eksik, Romance yetişmez → aynı arayana hızlı Gift Card'a geç (F8)" gibi dipnotlar. Kota bittiyse S-Tier için devam / End Day önerisi. |
| 📅 **Gün / hafta mantığı** | 3 hafta × 5 gün; her gün açılan uygulamalar, gün başı brifingi, 5. günden sonra Kat 2, 15. günden sonra prestij. Patron (Mr. Curry) değerlendirmesini sesten tanır: "You're fired" → 1. güne döner. |
| ⛔ **Scambaiter uyarısı** | Arthur Lin / Franklin D. Hyper gibi tuzak arayanlarda ve "sormadan AnyViewer kodu veren", "Nitro linki" yollayanlarda kırmızı uyarı. |
| 🤖 **İsteğe bağlı AI** | Claude API anahtarın varsa, kural motorunun cümlesini arayanın son sözüne göre iyileştirir ve arayanı Türkçeye çevirir. Yoksa da tamamen çevrimdışı çalışır. |
| 🔎 **İsteğe bağlı OCR** | Ekrandan gün, kota, kazanç, kalan süre, Caller Trust % ve arayan adını okur. |

---

## Kurulum (Windows 10/11)

1. **Python** kur → <https://www.python.org/downloads/> (kurulum ekranında **Add Python to PATH** kutusunu işaretle).
   3.10 – 3.14 arası çalışır; 3.12 en sorunsuzudur.
2. Bu depoyu indir (Code → Download ZIP) ve bir klasöre çıkar.
3. Klasörde **`install.bat`**'a çift tıkla. **Her şeyi o kurar** — ayrıca bir komut yazmana gerek yok:
   - `[2/3]` temel paketler (ses dinleme + konuşma tanıma). Burada hata çıkarsa program çalışmaz → ekran görüntüsünü gönder.
   - `[3/3]` isteğe bağlı paketler (AI, OCR, çeviri) **tek tek** kurulur. Biri kurulamazsa sadece o özellik kapalı kalır
     ve "atlandı" yazar; program yine çalışır.
4. **`run.bat`** ile başlat. İlk açılışta konuşma tanıma modeli (~150–500 MB) bir kez indirilir; birkaç dakika sürebilir.

<details>
<summary>Elle kurmak istersen (gerekli değil)</summary>

Komutlar normal bir cmd penceresine değil, **proje klasöründe açılmış** cmd'ye yazılır: Dosya Gezgini'nde proje
klasörünü aç → üstteki adres çubuğuna `cmd` yaz → Enter. Sonra:

```bat
py -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m pip install anthropic deep-translator mss onnxruntime rapidocr SpeechRecognition scipy
```

Başına `.venv\Scripts\python -m` koymadan düz `pip install ...` yazarsan paketler programın sanal ortamına (`.venv`) değil, bilgisayarın genel Python'una kurulur ve program onları görmez.
</details>

**Ekran kartı (isteğe bağlı):** Program konuşmayı yazıya dökerken NVIDIA ekran kartını kullanmayı **kendisi dener**;
gerekli CUDA dosyaları yoksa **kendiliğinden işlemciye (CPU) geçer** ve çalışmaya devam eder (alt satırda
`Whisper hazır: base.en (cpu)` yazar). Daha hızlı ve doğru yazıya dökme istersen bir kez **`install_gpu.bat`**'ı çalıştır
(~1.3 GB indirir); sonra alt satırda `small.en (cuda)` görünür.

### Oyun ayarları (önemli)

- **Ekran modu: Borderless / Windowed Fullscreen.** Özel tam ekran (exclusive fullscreen) modunda hiçbir pencere oyunun üstünde görünemez.
- Oyun dilini **İngilizce** yap (arayanlar İngilizce konuşsun).
- Oyun **müzik sesini kıs**, **konuşma/ses efekti** yüksek kalsın → yazıya dökme daha doğru olur.
- Oyunda mikrofonun yerine **yazarak da** konuşabilirsin: **Ctrl+F9** cümleyi panoya kopyalar, oyunun telefon kutusuna yapıştır.

---

## Kullanım akışı

1. `run.bat` → overlay açılır, sağ üstte **🎧 ses çubuğu** oyun konuşunca yeşil yanar.
2. Gün başında **⚙ (Durum)** panelinden **Gün** (1–15) ve gerekiyorsa **gerçek kotayı** gir (oyundaki HUD'dan). Scamazon'dan aldığın ücretli uygulamaları **Uygulamalar** sekmesinde işaretle.
3. Vardiya başlayınca **F10** (sayaç). Sayaç bitince tekrar **F10** = sonraki gün (otomatik ilerler) + gün brifingi.
4. Her yeni aramada **F5**. Arayan konuşur → üstte duyduğu cümle ve Türkçe özeti, ortada **sarı "SÖYLE"** cümlen çıkar.
5. Push-to-Talk'a basıp sarı cümleyi oku. Altındaki 💡 notta neden bunu söylediğin, mavi satırda uygulamada yapman gereken iş yazar.
6. Arayan kod/numara okuyunca **yeşil büyük yazı** → oyundaki uygulamaya yaz ve onayla. (8 sn sonra otomatik ilerler veya **F6**.)
7. Bir dolandırıcılık bitince koç aynı arayana bir sonrakine **köprü cümlesi** verir. Dipnot (en alttaki renkli satır) zaman / kota durumuna göre "devam et", "hızlı scam'e geç (F8)" ya da "kapat, yeni arama" der.

### Kısayollar (config.json → `hotkeys` bölümünden değiştirilebilir)

| Tuş | İşlev |
|---|---|
| **F5** | Yeni arama (karakter algılamayı sıfırlar) |
| **F6** | Adım tamam (oyundaki checklist işaretlendiyse) |
| **F7** | Adım geri |
| **F8** / **Shift+F8** | Sonraki / önceki dolandırıcılığa geç (aynı arayana) |
| **F9** | Alternatif cümle |
| **F10** | Vardiya sayacı başlat/durdur — süre bittiyse sonraki gün |
| **F11** | Sonraki gün |
| **Ctrl+F9** | Cümleyi panoya kopyala (oyunda yazarak göndermek için) |
| **Ctrl+F6** | Kazanca +$200 ekle |
| **Ctrl+F10** | Kompakt görünüm |
| **Ctrl+F11** | Tıklama geçirgen mod (fare overlay'in içinden oyuna geçer) |
| **Ctrl+F12** | Overlay'i gizle/göster |
| **Ctrl+Shift+F12** | OCR bölgesi seç (fareyle) |

Overlay'i başlığından sürükleyerek taşıyabilirsin; konum kaydedilir. ⚙ = Durum & Ayarlar, – = kompakt, ✕ = çıkış.

### Denemek için (oyun açmadan)

```bat
run_demo.bat                          :: Kanye East romance demosu
.venv\Scripts\python main.py --demo dorothy
.venv\Scripts\python main.py --simulate   :: arayan cümlesini kutuya kendin yaz
.venv\Scripts\python main.py --cli --simulate  :: pencere olmadan, konsolda
.venv\Scripts\python main.py --test-audio      :: sadece dinle + yazıya dök (ses ayarı testi)
.venv\Scripts\python main.py --list-devices    :: loopback cihazlarını listele
```

---

## Oyun mantığı (veritabanında: `characters_db.json`)

- **3 hafta × 5 gün.** Hafta 1 = Gün 1–5 (Kat 1), Hafta 2 = Gün 6–10 (5. gün değerlendirmesinden sonra **Kat 2**), Hafta 3 = Gün 11–15. 15. günden sonra prestij / 1. güne dönüş.
- **Kota:** 1. gün solo **$600** (2 oyuncu $960, oyuncu başına ~%60 artış). Sonraki günler artar; tablo tahminidir → HUD'daki gerçek değeri gir ya da OCR'ı aç.
- **Para sadece uygulamada kazanılır:** arayanın "evet" demesi yetmez; checklist sırayla tamamlanmalı ve kod/numara uygulamaya girilip onaylanmalı.
- **Tek arayana zincir:** topluluk tek arayandan 8 dolandırıcılık zincirledi. Koç, bir scam bitince aynı arayana sıradakine köprü cümlesi verir. *Kart reddedildi* hilesi: Credit Card'dan sonra Gift Card.
- **Romance:** hobi → flört → lakap → "I love you" → saatli randevu. 4. adım bitmeden randevu istemek güveni çökertir ("Kanye East sendromu").
- **Social Security:** SSN'i direkt isteme; önce kimlik karışıklığı → adres → doğum tarihi → SSN.
- **Investment:** ödeme = anlaşılan tutar → yüksek iste (koç reddedildikçe $2000 → $1500 → $1000… düşer), fatura numarasını gir.
- **Bitcoin / Meme Coin:** değer rastgele çöker; arayanı sakinleştir, makul seviyede Cash Out (en fazla ~$700).
- **IP Geolocation (6. gün):** konuşturarak okuma al; koç konuşmadaki şehir/eyalet/hava ipuçlarını 📍 satırında toplar → haritada tahmin et ($800'e kadar).
- **Money Mule (11. gün):** arayanı işe al → gönderiyi ayarla → ABD Gümrük memurunu ikna et.
- **Scambaiter:** verdiği AnyViewer koduna bağlanma, Disscord Nitro linkine tıklama; virüs bulaşırsa Malwarebits → Remove virus.
- Aramalar arası en az 5 sn bekleme var; son ~75 sn'de yeni arama açmak genelde boşa gider.

### Açılış takvimi ve ödüller

✅ = resmi yama notu / ekran görüntüsü ya da birden çok kaynakta tutarlı · ≈ = topluluk gözlemi / tahmin (koşudan koşuya değişebilir; ⚙ → Uygulamalar'dan düzelt).

| Gün | Hafta | Açılan uygulama | Maliyet | Ödül (tipik / maks) | Doğrulama |
|---|---|---|---|---|---|
| 1 | 1 | Credit Card | $200 | $250 / $400 | ✅ gün |
| 1 | 1 | Gift Card | Ücretsiz | $200 / $300 | ✅ gün |
| 2 | 1 | Romance Scam | Ücretsiz | $600 / $600 | ✅ gün, ✅ ödül |
| 3 | 1 | AnyViewer (uzaktan erişim) | Ücretsiz | araç | ≈ gün |
| 3 | 1 | Customer Info (araç) | Ücretsiz | araç | ≈ gün |
| 3 | 1 | Social Security (Identity) | Ücretsiz | $250 / $250 | ≈ gün, ✅ ödül |
| 4 | 1 | Bitcoin | $600 | $450 / $700 | ≈ gün, ✅ ödül |
| 4 | 1 | Tech Support | Ücretsiz | $300 / $400 | ≈ gün |
| 5 | 1 | Account Password Recovery | $600 | $500 / $500 | ≈ gün, ✅ ödül |
| 5 | 1 | Investment Scam | Ücretsiz | $800 / $3,000 (anlaşılan tutar) | ≈ gün |
| 5 | 1 | Meme Coin | Ücretsiz | $450 / $700 | ≈ gün, ✅ ödül |
| 5 | 1 | Police Impersonation | Ücretsiz | $400 / $600 | ≈ gün |
| 6 | 2 | Car's Extended Warranty | Ücretsiz | $300 / $300 | ≈ gün |
| 6 | 2 | IP Geolocation | Ücretsiz | $600 / $800 | ✅ gün, ✅ ödül |
| 6 | 2 | Nigerian Prince | Ücretsiz | $400 / $600 | ≈ gün |
| 7 | 2 | Car Registration | Ücretsiz | $250 / $400 | ≈ gün |
| 7 | 2 | Lottery Prize | Ücretsiz | $250 / $1,000 | ≈ gün, ✅ ödül |
| 7 | 2 | Utility Billing | Ücretsiz | $300 / $400 | ≈ gün |
| 8 | 2 | Bank Login | $1,200 | $1,000 / $1,500 | ≈ gün |
| 8 | 2 | Blacklist | Ücretsiz | $300 / $500 | ≈ gün |
| 8 | 2 | Book Publishing | Ücretsiz | $300 / $500 | ≈ gün |
| 9 | 2 | Blackmail | Ücretsiz | $500 / $700 | ≈ gün |
| 9 | 2 | Ransom | Ücretsiz | $600 / $900 | ≈ gün |
| 11 | 3 | Money Mule | Ücretsiz | $800 / $1,200 | ✅ gün |

### Karakterler

Veritabanında PDF'teki tüm karakterler + eksikler (Eleanor Grimshaw, Brittany "Lexi" Summers, Franklin D. Hyper,
Damien Holloway, Shanice "Dee" Bishop, Arthur Lin, SpongeBob/Donald/Freddy parodileri, Workshop paketi) ve oyundaki
~1000 rastgele arayan için **genel şablonlar** var. Her karakterde: arketip, zaaf, ölümcül hata, anahtar kelimeler,
en iyi zincir, kaçınılacak scam'ler ve "gümüş kurşun" açılış cümleleri.

| Karakter | Arketip | En iyi zincir | Kaynak |
|---|---|---|---|
| Dorothy Mayfield | Güvenen Hedef (Trusting) | Social Security → Gift Card → Tech Support → Utility Billing | Resmi ekran görüntüsü |
| Eleanor "Granny" Grimshaw | Güvenen Hedef (Trusting) | Romance Scam → Gift Card → Social Security → Tech Support | Resmi ekran görüntüsü |
| Commander Miles "Orbit" Vega | Şüpheci Hedef (Skeptical) | Tech Support → AnyViewer → Account Password Recovery → Gift Card | Resmi ekran görüntüsü |
| Brittany "Lexi" Summers | Karmaşık Sinyal (Mixed-Signal) | Credit Card → Gift Card → Utility Billing | Resmi ekran görüntüsü |
| Franklin D. Hyper | SCAMBAITER (Tersine Dolandırıcı) | ⛔ Meme Coin → Investment Scam (riskli) | Resmi ekran görüntüsü |
| Damien Holloway | Açgözlü Yatırımcı (Greed) | Investment Scam → Bitcoin → Meme Coin → Book Publishing | Resmi ekran görüntüsü |
| Shanice "Dee" Bishop | Şüpheci Hedef (Skeptical) | Utility Billing → Gift Card → Social Security → Credit Card | Resmi ekran görüntüsü |
| Kanye East | Ego Odaklı (Ego / Ünlü) | Romance Scam → Investment Scam → Book Publishing → Meme Coin | PDF / oynanış videosu |
| Kenzo Sivley | Güvenen Hedef (Trusting) | Car's Extended Warranty → Credit Card → Gift Card → Car Registration | PDF / oynanış videosu |
| Chael Sonnen | Baskı Altındaki Hedef (Pressured) | Police Impersonation → Social Security → Credit Card → Blacklist | PDF / oynanış videosu |
| Dracula | Absürt / Fantastik Karakter | Car's Extended Warranty → Gift Card → Romance Scam → Lottery Prize | PDF / oynanış videosu |
| Eşya Taşıma Arayanı (Belongings / Moving Caller) | Belirli Sorunla Arayan (Specific Need) | Car's Extended Warranty → Gift Card → Credit Card → Utility Billing | PDF / oynanış videosu |
| Mısır Gevreği Şikâyetçisi (Cereal-Problem Caller) | Belirli Sorunla Arayan (Specific Need) | Gift Card → Credit Card → Lottery Prize | PDF / oynanış videosu |
| Arthur Lin | SCAMBAITER (Tersine Dolandırıcı) | ⛔ Kapat (Hang Up) | PDF / oynanış videosu |
| SpongeBob (parodi) | Absürt / Fantastik Karakter | Gift Card → Lottery Prize → Car's Extended Warranty → Romance Scam | PDF / oynanış videosu |
| Donald Trump (parodi arayan) | Ego Odaklı (Ego / Ünlü) | Investment Scam → Book Publishing → Meme Coin → Bitcoin | PDF / oynanış videosu |
| Freddy Fazbear (parodi) | Absürt / Fantastik Karakter | Car's Extended Warranty → Tech Support → Gift Card → Lottery Prize | PDF / oynanış videosu |
| Homer Simpson (Workshop modu) | Güvenen Hedef (Trusting) | Lottery Prize → Gift Card → Investment Scam → Car's Extended Warranty | Workshop modu |
| Marge Simpson (Workshop modu) | Güvenen Hedef (Trusting) | Utility Billing → Social Security → Gift Card | Workshop modu |
| Mr. Burns (Workshop modu) | Açgözlü Yatırımcı (Greed) | Investment Scam → Bitcoin → Bank Login → Book Publishing | Workshop modu |
| Peter Griffin (Workshop modu) | Absürt / Fantastik Karakter | Lottery Prize → Meme Coin → Gift Card → Car's Extended Warranty | Workshop modu |
| Bilinmeyen yaşlı / güvenen arayan | Güvenen Hedef (Trusting) | Social Security → Gift Card → Tech Support → Romance Scam | Genel şablon |
| Bilinmeyen yalnız arayan | Yalnız / Sohbet Arayan | Romance Scam → Gift Card → Nigerian Prince → Lottery Prize | Genel şablon |
| Bilinmeyen şüpheci arayan | Şüpheci Hedef (Skeptical) | Tech Support → AnyViewer → Account Password Recovery → Utility Billing | Genel şablon |
| Bilinmeyen meşgul / aceleci arayan | Aceleci / Meşgul | Gift Card → Credit Card → Utility Billing | Genel şablon |
| Bilinmeyen sinirli müşteri | Karmaşık Sinyal (Mixed-Signal) | Credit Card → Gift Card → Car's Extended Warranty | Genel şablon |
| Bilinmeyen kripto/yatırım meraklısı | Açgözlü Yatırımcı (Greed) | Investment Scam → Bitcoin → Meme Coin → Bank Login | Genel şablon |
| Bilinmeyen endişeli / baskı altındaki arayan | Baskı Altındaki Hedef (Pressured) | Police Impersonation → Social Security → Utility Billing → Blacklist | Genel şablon |
| Bilinmeyen ünlü / egolu arayan | Ego Odaklı (Ego / Ünlü) | Romance Scam → Book Publishing → Investment Scam → Meme Coin | Genel şablon |
| Bilinmeyen absürt / fantastik arayan | Absürt / Fantastik Karakter | Car's Extended Warranty → Gift Card → Romance Scam → Lottery Prize | Genel şablon |
| Bilinmeyen scambaiter | SCAMBAITER (Tersine Dolandırıcı) | ⛔ Kapat (Hang Up) | Genel şablon |
| ABD Gümrük Memuru (Money Mule) | Şüpheci Hedef (Skeptical) | Money Mule | Genel şablon |

**Eksik karakter mi var?**
- `python main.py --import-callers` → Steam kurulumunu bulur, oyunun `StreamingAssets` / Workshop / `CustomCallers` klasörlerindeki arayan JSON'larını okur, her biri için otomatik profil çıkarır (`characters_imported.json`).
- Ya da `characters_custom.json` oluşturup kendin ekle:

```json
{
  "characters": {
    "margaret": {
      "name": "Margaret Pemberton",
      "aliases": ["margaret", "mrs. pemberton"],
      "archetype": "lonely",
      "keywords": ["knitting", "mittens", "cat"],
      "best_scams": ["romance", "gift_card", "social_security"],
      "fatal_tr": ["Acele ettirmek"],
      "custom_lines": {"romance:learn_interest": ["Margaret, your voice is so warm! What do you love doing — do you knit?"]}
    }
  }
}
```

---

## AI danışmanı (isteğe bağlı, Claude)

Kural motoru tamamen çevrimdışı çalışır. Daha esnek cevaplar ve arayanın Türkçe çevirisi için:

1. `install.bat` bunu zaten kurar (`anthropic` paketi). Kurulmadıysa proje klasöründeki cmd'de: `.venv\Scripts\python -m pip install anthropic`
2. <https://console.anthropic.com> → API anahtarı al → Windows'ta `setx ANTHROPIC_API_KEY "sk-ant-..."` (ya da ⚙ → Ayarlar → API anahtarı).
3. ⚙ → Ayarlar → **AI danışmanı** işaretle. Varsayılan model `claude-opus-5-5` (en iyi kalite, `effort: low`). Daha hızlı/ucuz istersen `claude-haiku-5-5` seç.

AI gelince sarı kutunun başlığında **(AI)** yazar; kural motorunun cümlesi alternatif olarak kalır. API ücretlidir.

## OCR (isteğe bağlı)

`install.bat` gerekli paketleri (`mss`, `rapidocr`, `onnxruntime`) kurar → ⚙ → Ayarlar → **OCR** işaretle → **Bölge ekle** ile önce telefon penceresinin üst kısmını (Caller Trust + arayan adı), sonra alttaki `QUOTA / PERFORMANCE REVIEW` çubuğunu seç (gün, kota/kazanç,
süre, Caller Trust, arayan adı) fareyle seç. Gün/kota/kazanç/süre otomatik güncellenir, arayan adı karakteri seçer.

---

## Sorun giderme

| Sorun | Çözüm |
|---|---|
| Ses çubuğu yeşil yanıyor ama cümle değişmiyor | Konsoldaki `[durum]` satırlarına bak. `Ekran kartı (CUDA) kullanılamadı` yazıyorsa program CPU'ya geçmiştir; GPU için `install_gpu.bat`. `STT hatası` yazıyorsa o satırın ekran görüntüsünü gönder. ⚙ → Arayan **(Otomatik)** olmalı. |
| Ses çubuğu hiç oynamıyor | `python main.py --list-devices` → oyunun çıktığı cihazı `config.json` → `audio.device_name` içine yaz (ör. `"headphones"`). |
| Yazıya dökme yavaş | `config.json` → `stt.model`: `"tiny.en"` (en hızlı) / `"base.en"`; NVIDIA varsa `"small.en"`. |
| Saçma metinler ("Thank you." vb.) | Oyun müziğini kıs; `audio.threshold_db`'yi yükselt (ör. -42). |
| Overlay oyunun arkasında | Oyunu **Borderless/Windowed** moda al. |
| Kısayol çalışmıyor | Başka program aynı tuşu kullanıyor olabilir → `config.json` → `hotkeys`. Oyun yönetici olarak çalışıyorsa koçu da yönetici olarak çalıştır. |
| Overlay'e tıklayınca oyun odak kaybediyor | Overlay odak almaz şekilde ayarlıdır; yine de sorun olursa **Ctrl+F11** (tıklama geçirgen). |
| Yanlış karakter | ⚙ → Arayan listesinden seç veya F5 ile yeni arama. |
| Gün/uygulamalar oyundan farklı | ⚙ → Durum (gün) ve Uygulamalar sekmesi. Patron "tomorrow's scams" derse koç yarın açılacakları not alır. |

Her oturumun dökümü `logs/` klasörüne yazılır (arayanın sözleri + önerilen cümleler).

---

## Dosya yapısı

| Dosya | Görev |
|---|---|
| `main.py` | Giriş noktası; servisleri bağlar (ses, OCR, kısayol, AI), olay döngüsü, demo/simülasyon/CLI modları |
| `overlay_ui.py` | Tkinter overlay (her zaman üstte, yarı saydam, sürüklenebilir, tıklama geçirgen), Durum & Ayarlar penceresi, OCR bölge seçici |
| `audio_listener.py` | WASAPI loopback yakalama, enerji + webrtcvad konuşma kesici, 16 kHz örnekleme, faster-whisper / Google STT |
| `strategy_engine.py` | Karakter tanıma, niyet analizi, scam planlama/zincirleme, checklist takibi, cümle seçimi, zaman/kota dipnotları |
| `text_analysis.py` | Niyet sınıflandırıcı, sözle okunan kod/kart/SSN/e-posta/tutar/konum çıkarımı |
| `game_state.py` | Hafta/gün, kota, kazanç, vardiya sayacı, açık/satın alınmış uygulamalar (state.json) |
| `characters_db.json` | Oyun kuralları, 3 haftalık takvim, 24 uygulama (adımlar + B1/C1/C2 cümleler), itiraz cevapları, karakterler, niyet kalıpları |
| `screen_reader.py` | İsteğe bağlı OCR (mss + RapidOCR / Tesseract) |
| `llm_advisor.py` | İsteğe bağlı Claude danışmanı + çeviri |
| `caller_importer.py` | Oyun klasöründen arayan kişiliklerini içe aktarma |
| `hotkeys.py` | Win32 RegisterHotKey ile global kısayollar |
| `config.py` | `config.json` varsayılanları, veritabanı birleştirme |
| `tests/` | Birim testleri: `python -m unittest discover -s tests -t .` |

## Doğruluk notu

Oyun Erken Erişim'de ve her yamada değişiyor. Kesin bilgiler (Steam yama notları 0.1.73–0.1.84, resmi ekran
görüntüleri) ✅ ile işaretli; diğer gün/ödül değerleri topluluk gözlemi veya tahmindir. Oyundaki değer farklıysa
⚙ panelinden düzelt — koç tüm hesaplarını girdiğin değerlerle yapar. Veritabanı düz JSON'dur, düzenleyebilirsin.
