**GPT 6.1 Sol ile çevrildi.**

# Noita — GPT Tabanlı Türkçe Çeviri

Ölüm evrensel, otopsi yerel.

Noita için kuru mizahlı, gayriresmî Türkçe dil paketi. Menüler, büyüler,
yetenekler, durum etkileri, malzemeler, eşyalar, biyomlar, kitaplar ve yayın
olayları için 3.610 benzersiz metin anahtarı içerir. Bulmaca ipuçları ve
mekanik bilgiler korunur; espriler seçili açıklamalardadır.

> Yanıyorsun. Su bul! Aydınlanmanın sırası değil.

## Windows — EXE ile kurulum

[NoitaTurkceSetup-0.1.0.exe indir](https://github.com/bhctsntrk/notia-gpt-based-turkce-ceviri/releases/download/v0.1.0/NoitaTurkceSetup-0.1.0.exe).
Windows 10/11, 64 bit. Python, uv veya elle dosya kopyalama gerekmez.

1. Noita'yı kapat ve EXE'yi çift tıklayarak aç.
2. Steam kurulumu otomatik bulunur. Gerekirse **Klasör seç** ile `noita.exe`
   dosyasının bulunduğu klasörü göster.
3. Ana yama hazırdır. Kuruluysa Cheatgui ve Seed Changer eklerini de seçebilirsin.
4. **Türkçe yamayı kur** düğmesine bas. Dil ayarı varsa Türkçe otomatik seçilir;
   oyun henüz açılmadıysa oyun içinden **Options > Language > Türkçe** seç.

Kaldırmak için aynı EXE'de **Kaldır / geri yükle** düğmesini veya Windows'un
**Yüklü uygulamalar > Noita Türkçe Çeviri > Kaldır** seçeneğini kullan.
Kurulumdan önceki dosyalar ve önceki dil geri gelir. Sonradan değiştirilen ses,
görüntü ve diğer ayarlar korunur; kayıt oyunlarına dokunulmaz. Önceden elle
Türkçe yama kurduysan kaldırma o önceki yamayı geri getirir.

Paketler EXE'nin içindedir; internet bağlantısı gerekmez. Özgün modlar ayrıca
kurulu olmalı; araç onların yalnız çeviri eklerini uygular. Fontları kendi oyun
dosyalarından otomatik hazırlar, elle arşiv açmak gerekmez.

Yedekler yerel `%LOCALAPPDATA%/NoitaTurkce/Installations` klasöründe tutulur.
Windows kaldırma düğmesinin çalışması için kurulum aracı yerel olarak saklanır;
yama kaldırıldıktan sonra tekrar kullanım için kalır. Değişmiş dosya veya bozuk
yedek bulunursa mevcut dosyaları korumak için işlem durur.

EXE kod imzası taşımaz; Windows indirme/güvenlik uyarısı gösterebilir. Yalnız
bu projenin sürüm sayfasındaki dosyayı kullan; SHA-256 özeti sürüme eklenir.
Oyun klasörüne yazma izni gerekir. Kurulum aracı yönetici yetkisi istemez.

## Kaynaktan hazırlama ve elle kurulum

Tam/satın alınmış Noita sürümü, Python, [uv](https://docs.astral.sh/uv/) ve
oyunun açılmış `data/fonts` dosyaları gerekir. Dosyalar açılmamışsa oyunun
`tools_modding/READ_ME_FIRST.txt` yönergelerini izle.

```powershell
uv run --no-project --with pillow python tools/build.py --game-dir "<Noita klasörü>"
```

`dist/translation_tr_witty` klasörü oluşur. Bunu Noita'nın `mods` klasörüne
kopyala; oyun içinden **Options > Language > Türkçe** seç.
Dil paketi `is_translation="1"` mekanizmasını kullanır.

Fontlar kendi oyun kurulumundan hazırlanır. Depoda yalnız eksik `ğĞıİşŞ`
harflerinin ek glifleri bulunur. Tam font atlasları ve özgün İngilizce metin
sütunu dağıtım kaynaklarına eklenmemiştir.

İngilizceye dönmek için oyun menüsünden English seç.

## Seed Changer için isteğe bağlı ek

[Evaisa'nın Seed Changer modunu](https://steamcommunity.com/sharedfiles/filedetails/?id=2284931352)
ayrıca edin. Ayar menüsünü Türkçeleştirmek için:

```powershell
uv run --no-project python tools/seed_changer.py --mod-dir "<Seed Changer klasörü>"
```

Başlık **Kader Ayarı**, seçenekler **Dünya tohumu sabit** ve **Dünya tohumu**
olur. Araç mevcut modun yalnız metin alanlarını değiştirir ve değiştirdiği
dosyaları `dist/seed_changer_backup` altında yedekler. Atölye güncellemesi
çeviriyi kaldırırsa aracı tekrar çalıştır. `--dry-run` yalnız uyumluluğu denetler.

Seed Changer'ın kaynak kodu bu depoda dağıtılmaz. Bu ek, güncel modun
yerleşik ayar menüsünü hedefler.

## Cheatgui için isteğe bağlı ek

[Cheatgui modunu](https://steamcommunity.com/sharedfiles/filedetails/?id=1984977713)
ayrıca edin ve önce Türkçe dil paketini seç. Cheatgui **1.5.0** arayüzünü
Türkçeleştirmek için:

```powershell
uv run --no-project --with luaparser python tools/cheatgui.py --mod-dir "<Cheatgui klasörü>"
```

**Hile Tezgâhı**, asa atölyesi, ışınlanma, can/altın, mantar dönüşümü,
bilgi çubuğu ve oyun içi konsol menüsündeki 112 metin örneğini çevirir.
Büyü/eşya/malzeme listelerinde oyunun yerelleştirilmiş adlarını gösterir.
Teknik eşya kimlikleri ve hile işlevleri korunur.
Menü metinleri ve düğmeleri dil paketindeki Türkçe piksel fontuyla çizilir;
`ğĞıİşŞ` harfleri de desteklenir. Daha önce çevrilmiş bir Cheatgui kopyasına
aracı tekrar uygulamak font düzeltmesini ekler.

Araç Lua sözdizimini ve metin eşleşmelerini dosya yazmadan önce denetler.
`--dry-run` uyumluluğu kontrol eder; orijinaller `dist/cheatgui_backup`
altında saklanır. Kurulumdan sonra Noita'yı yeniden başlat. Atölye güncellemesi
çeviriyi kaldırırsa aracı yeniden çalıştır. Modun tam kaynak kodu depoya
eklenmemiştir.

## Durum ve gizlilik

İlk metin kaynağı Noita Steam build `17130612`. 3.686 dolu kaynak satırındaki
yinelenen anahtarlar son kayıtları esas alınarak 3.610 anahtara indirgenmiştir.
Sayılar, yer tutucular ve literal `\n` işaretleri kaynakla karşılaştırılmıştır.
Türkçe harfler için font önizlemesi incelenmiştir. Oyun içindeki tüm ekranlar
henüz görsel olarak doğrulanmamıştır.

Kaynaklar bilgisayar adı/yolu, kişisel kullanıcı adı, kayıt oyunları, kişisel
ayarlar, erişim anahtarları veya kullanıcı yedekleri içermez. Araçlar yolları
komut satırından alır; üretilen dosyalar ve yedekler Git dışında tutulur.
Oyun geliştiricilerinin kredi ve hak sahipliği bilgileri korunmuştur.

## Windows aracını derleme ve doğrulama

Windows üzerinde Python 3.12 ve uv ile:

```powershell
uv run --no-project --with-requirements installer/requirements-build.txt python -m installer.build_exe
uv run --no-project --with-requirements installer/requirements-build.txt python -m installer.selftest dist/installer/test-report.json
```

EXE `dist/installer` altında oluşur. Testler geçici, sentetik bir oyun kurulumunda
çalışır. Aynı kur/kaldır testlerini derlenmiş EXE'nin içinde çalıştırmak için:

```powershell
dist/installer/NoitaTurkceSetup-0.1.0.exe --self-test dist/installer/test-report.json
```

Testler yedek bütünlüğünü, ek modların byte düzeyinde geri yüklenmesini, farklı
ayarların korunmasını, WAK font okumasını, hata sonrası geri almayı, açık oyun
korumasını, işlem kilidini ve Windows kaldırma kaydını denetler. Gerçek oyun
kurulumunda uçtan uca görsel test ayrıca yapılmalıdır.

## Haklar

Noita, Nolla Games Oy'a aittir. Bu proje Nolla Games tarafından onaylanmış
resmî bir çeviri değildir. Modlama şartları ve paylaşım kapsamı için
[RIGHTS.md](RIGHTS.md) dosyasına bak.
