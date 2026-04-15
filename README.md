# KOBİ Otomatik Muhasebe Raporlama Sistemi

> Türk KOBİ'ler için muhasebe yazılımı entegrasyonlu, otomatik sabah raporu gönderen BI sistemi.

**Demo Senaryosu:** Yılmaz Makine Ltd. — İstanbul merkezli makine imalat/satış firması

---

## Özellikler

- **Her gece otomatik ETL** (Airflow): Gecikmiş faturaları güncelle, KPI'ları hesapla
- **Sabah 07:00 e-posta raporu**: HTML formatında nakit durumu, alacak takibi, stok alarmı
- **4 Metabase Dashboard**: Nakit Durumu, Satış Özeti, Alacak Takibi, Yönetici Özeti
- **Gerçekçi demo verisi**: 18 aylık mevsimsel satış dalgalanması, 208 gecikmiş alacak, 8 kritik stok
- **Docker Compose**: Tek komutla ayağa kalkar

---

## Mimari

```
┌─────────────────────────────────────────────────────────┐
│                     Docker Network                       │
│                                                         │
│  ┌──────────────┐    ┌──────────────┐  ┌─────────────┐ │
│  │   PostgreSQL  │    │   Airflow    │  │  Metabase   │ │
│  │   :5433      │◄───│   :8080      │  │   :3000     │ │
│  │              │    │              │  │             │ │
│  │  kobi_db     │    │  Gece 02:00  │  │  4 Dashboard│ │
│  │  airflow_db  │    │  ETL + Email │  │  KPI + Grafik│ │
│  │  metabase_db │    │              │  │             │ │
│  └──────────────┘    └──────────────┘  └─────────────┘ │
└─────────────────────────────────────────────────────────┘
```

### Veritabanı Şeması

```
musteriler (15 kayıt)
    ├── faturalar (632 kayıt, 38.7M TL)
    │       └── odemeler (406 ödeme, 23.6M TL tahsil)
    └── (görünümler: geciken_alacaklar, kritik_stok)

stok (48 kalem)
```

---

## Hızlı Başlangıç

### Ön Koşullar

- Docker & Docker Compose
- Python 3.10+ (seed ve setup scriptleri için)
- `pip install faker psycopg2-binary requests`

### Kurulum

```bash
# 1. Repoyu klonla
git clone https://github.com/KULLANICI/kobi-rapor.git
cd kobi-rapor

# 2. E-posta ayarlarını yap (opsiyonel)
cp .env.example .env
# .env dosyasını düzenle

# 3. Tüm servisleri başlat
docker compose up -d

# 4. Veritabanı şemasını oluştur
docker cp scripts/01_schema.sql kobi-postgres:/tmp/
docker exec kobi-postgres psql -U kobi -d kobi_db -f /tmp/01_schema.sql

# 5. Demo verisini yükle
python3 scripts/02_seed_data.py

# 6. Metabase'i yapılandır (dashboard'lar dahil)
python3 scripts/03_metabase_setup.py

# 7. E-posta testini çalıştır (SMTP gerektirmez)
python3 scripts/04_sabah_email.py --dry-run
```

---

## Servisler

| Servis | URL | Kullanıcı | Şifre |
|--------|-----|-----------|-------|
| Metabase | http://localhost:3000 | admin@yilmazmakine.com.tr | KobiRapor2024! |
| Airflow | http://localhost:8080 | admin | admin123 |
| PostgreSQL | localhost:5433 | kobi | kobi123 |

---

## Dashboard'lar

### 💰 Nakit Durumu
- Tahsilat, bekleyen ve gecikmiş alacak scalar'ları
- Aylık tahsilat trendi (line chart)
- Fatura durum dağılımı (pie chart)

### 📊 Satış Özeti
- 18 aylık satış bar chart (mevsimsel dalgalanma görünür)
- Top 10 müşteri sıralaması
- Sektöre göre satış dağılımı
- Ortalama fatura tutarı trendi

### ⚠️ Alacak Takibi
- Yaşlandırma analizi: 1-30 / 31-60 / 61-90 / 91-180 / 180+ gün
- Riskli müşteriler tablosu
- Gecikmiş fatura listesi (üst 50)

### 🏭 Yönetici Özeti
- Bu ay satış / tahsilat / kritik stok KPI
- Satış vs Tahsilat karşılaştırmalı grafik
- Kritik stok listesi (sipariş edilmesi gerekenler)
- Ödeme yöntemi dağılımı

---

## Airflow DAG — `kobi_gece_rapor`

**Zamanlama:** Her gece 02:00 (Türkiye saati)

```
db_health_check
      │
guncelle_gecikis
      │
      ├── nakit_durumu_hesapla
      ├── satis_ozeti_hesapla
      ├── alacak_takibi
      └── stok_alarm_kontrol
                │
          email_rapor_gonder
```

| Task | Açıklama |
|------|----------|
| `db_health_check` | Veritabanı bağlantı testi |
| `guncelle_gecikis` | `beklemede` + vade geçmiş → `gecikti` |
| `nakit_durumu_hesapla` | Son 30 günlük nakit KPI'ları |
| `satis_ozeti_hesapla` | Satış özeti + top 5 müşteri |
| `alacak_takibi` | Gecikmiş alacak analizi |
| `stok_alarm_kontrol` | Min. altı stok tespiti |
| `email_rapor_gonder` | HTML e-posta gönderimi |

---

## E-posta Raporu

Gmail ile kurulum:

```bash
# .env dosyasına ekle:
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=senin@gmail.com
SMTP_PASS=uygulama-sifresi    # Gmail > Hesap > Güvenlik > Uygulama Şifreleri
REPORT_EMAIL=yonetici@sirket.com.tr
```

Cron ile otomatik (sunucu kurulumu için):

```bash
# crontab -e
0 4 * * * cd /path/to/kobi-rapor && python3 scripts/04_sabah_email.py >> /var/log/kobi_email.log 2>&1
```

---

## Demo Verisi — Yılmaz Makine Ltd.

| Metrik | Değer |
|--------|-------|
| Müşteri | 15 firma (Ankara, Bursa, İzmir, Konya, vs.) |
| Toplam Fatura | 632 adet / 38.7 milyon TL |
| Tahsil Edilen | 23.6 milyon TL |
| Gecikmiş Alacak | **208 fatura / 9.6 milyon TL** |
| Maks. Gecikme | 518 gün |
| Stok Kalemi | 48 (makine parçası, hammadde, sarf) |
| Kritik Stok | **8 kalem** (silindir, motor, PLC, lazer nozul) |

**Mevsimsel dalgalanma:** İlkbahar (Şubat-Mayıs) +%15-40 | Yaz -%10-30 | Sonbahar +%10-30

---

## Proje Yapısı

```
kobi-rapor/
├── docker-compose.yml          # Tüm servisler
├── .env.example                # Ortam değişkenleri şablonu
├── dags/
│   └── kobi_gece_rapor.py      # Airflow ETL + e-posta DAG'ı
├── scripts/
│   ├── 01_schema.sql           # Veritabanı şeması (tablolar + view'lar)
│   ├── 02_seed_data.py         # Faker ile Türk KOBİ demo verisi
│   ├── 03_metabase_setup.py    # Metabase dashboard kurulumu
│   ├── 04_sabah_email.py       # Standalone sabah raporu
│   └── init_dbs.sh             # Docker init: metabase_db + airflow_db
└── data/                       # Dry-run HTML raporları
```

---

## Teknoloji Stack'i

| Katman | Teknoloji |
|--------|-----------|
| Veritabanı | PostgreSQL 15 |
| Veri Görselleştirme | Metabase (Open Source) |
| Orkestrasyon | Apache Airflow 2.9 |
| Veri Üretimi | Python 3 + Faker |
| E-posta | Python smtplib (SMTP/TLS) |
| Konteyner | Docker + Docker Compose |

---

## Gerçek Müşteri Entegrasyonu

Bu sistem aşağıdaki muhasebe yazılımlarına bağlanacak şekilde genişletilebilir:

- **Logo Tiger / Go**: MSSQL veritabanına doğrudan bağlantı
- **Mikro**: Kendi PostgreSQL veya MSSQL veritabanı
- **Paraşüt / e-Logo**: REST API entegrasyonu
- **Zirve**: DBF/SQL exportları

`scripts/02_seed_data.py` yerine ilgili yazılımın DB bağlantısı tanımlanır,
geri kalan pipeline aynı şekilde çalışır.

---

## Lisans

MIT

---

*Mustafa Aygün — Veri Mühendisi*
