"""
KOBİ Rapor Sistemi - Gerçekçi Türk KOBİ Veri Üreteci
Senaryo: Yılmaz Makine Ltd. - İstanbul merkezli makine imalat/satış firması
- 18 aylık geçmiş veri (mevsimsel dalgalanmalar dahil)
- Geciken alacaklar ve kritik stok alarmları
- Türkçe isimler, gerçekçi vergi no, fatura no formatı
"""

import random
import psycopg2
from faker import Faker
from datetime import date, timedelta
from decimal import Decimal

fake = Faker("tr_TR")
random.seed(42)

DB = dict(
    host="localhost", port=5433,
    dbname="kobi_db", user="kobi", password="kobi123"
)

# ── Sabit veriler ──────────────────────────────────────────────────────────────

MUSTERILER_DATA = [
    ("MUS001", "Ankara Çelik San. A.Ş.",      "Demir-Çelik",     "Ankara",   "02124450001", "info@ankaraçelik.com.tr",  "3840011234", 250_000),
    ("MUS002", "Bursa Otomotiv Ltd.",           "Otomotiv",        "Bursa",    "02244450002", "muhasebe@bursaoto.com.tr", "1620021234", 180_000),
    ("MUS003", "İzmir Tekstil A.Ş.",            "Tekstil",         "İzmir",    "02324450003", "finans@izmirteks.com.tr",  "2340031234", 120_000),
    ("MUS004", "Konya Gıda San. Ltd.",          "Gıda",            "Konya",    "03324450004", "konya@gıdasan.com.tr",     "4200041234",  80_000),
    ("MUS005", "Gaziantep Plastik Ltd.",        "Plastik",         "Gaziantep","03424450005", "info@gaziplastik.com.tr",  "2720051234",  95_000),
    ("MUS006", "Kocaeli Kimya A.Ş.",            "Kimya",           "Kocaeli",  "02624450006", "kocaeli@kimyaas.com.tr",   "4140061234", 320_000),
    ("MUS007", "Adana Tarım Mak. Ltd.",         "Tarım Mak.",      "Adana",    "03224450007", "adana@tarimmak.com.tr",    "0130071234",  60_000),
    ("MUS008", "Eskişehir Pres San. A.Ş.",      "Metal",           "Eskişehir","02224450008", "pres@eskipres.com.tr",     "2600081234", 150_000),
    ("MUS009", "Mersin Liman Lojistik Ltd.",    "Lojistik",        "Mersin",   "03244450009", "mersin@limanlog.com.tr",   "3300091234",  70_000),
    ("MUS010", "Samsun Deniz Araçları A.Ş.",    "Denizcilik",      "Samsun",   "03624450010", "samsun@denizarac.com.tr",  "5500101234", 200_000),
    ("MUS011", "Trabzon İnşaat Mak. Ltd.",      "İnşaat Mak.",     "Trabzon",  "04624450011", "trabzon@insaatmak.com.tr", "6100111234",  55_000),
    ("MUS012", "Antalya Turizm Ekip. A.Ş.",     "Turizm Ekip.",    "Antalya",  "02424450012", "antalya@turizmekip.com.tr","0700121234", 110_000),
    ("MUS013", "Diyarbakır Metal San. Ltd.",    "Metal",           "Diyarbakır","04124450013","diyarbakir@metalsan.com.tr","2100131234",  45_000),
    ("MUS014", "Kayseri Taş-Ocak Ltd.",         "Maden",           "Kayseri",  "03524450014", "kayseri@tasocak.com.tr",   "3800141234",  85_000),
    ("MUS015", "Hatay Boru Sistemleri A.Ş.",    "Boru/Vana",       "Hatay",    "03264450015", "hatay@borusist.com.tr",    "3100151234", 130_000),
]

# 48 stok kalemi — makine yedek parça + hammadde
STOK_DATA = [
    # (kod, ad, kategori, birim, mevcut, minimum, maliyet, satis, tedarikci)
    ("STK001", "Çelik Mil Ø50mm",            "Hammadde",   "metre", 120, 50,   85,   110,  "Kardemir A.Ş."),
    ("STK002", "Alüminyum Profil 6063",       "Hammadde",   "kg",    850, 300,  42,    58,  "Asaş Alüminyum"),
    ("STK003", "Hidrolik Silindir 100mm",     "Yedek Parça","adet",   18,  20, 380,   520,  "Parker Hannifin"),
    ("STK004", "Rulman SKF 6205",             "Yedek Parça","adet",  210,  50,  28,    42,  "SKF Türkiye"),
    ("STK005", "Vana DN50 PN16",              "Yedek Parça","adet",   45,  30,  95,   138,  "Valtek"),
    ("STK006", "Elektrik Motoru 7.5kW",       "Elektrik",   "adet",    6,  10, 850, 1_150,  "ABB Türkiye"),
    ("STK007", "Redüktör 1/40",               "Elektrik",   "adet",   12,  10, 420,   590,  "SEW-Eurodrive"),
    ("STK008", "Frekans Konvertörü 7.5kW",    "Elektrik",   "adet",    4,   5, 620,   880,  "Siemens"),
    ("STK009", "PLC Siemens S7-1200",         "Otomasyon",  "adet",    3,   5, 980, 1_350,  "Siemens"),
    ("STK010", "Sensör Endüktif M18",         "Otomasyon",  "adet",   85,  40,  32,    52,  "Sick AG"),
    ("STK011", "Kablo NHXMH 3x2.5mm",        "Elektrik",   "metre", 400, 200,  4.8,   7.2, "Prysmian"),
    ("STK012", "Pnömatik Silindir Ø63",       "Pnömatik",   "adet",   28,  20, 145,   195,  "Festo"),
    ("STK013", "Kompresör Filtresi",          "Pnömatik",   "adet",   35,  15,  48,    72,  "SMC"),
    ("STK014", "Kaynak Elektrodu E6013 3.2",  "Sarf",       "kg",    180,  80,   6.5,   9.5,"Gedik Kaynak"),
    ("STK015", "Kesme Diski 230mm",           "Sarf",       "adet",  320, 100,   8,    12,  "Tyrolit"),
    ("STK016", "Hidrolik Yağ ISO VG46",       "Sarf",       "litre", 250, 100,  12,    18,  "Shell Türkiye"),
    ("STK017", "Rulman FAG 6308",             "Yedek Parça","adet",   42,  25,  65,    95,  "FAG"),
    ("STK018", "Dişli Çark M3 Z=40",         "Makine Parçası","adet",  9,  15, 210,   290,  "Yılmaz Redüktör"),
    ("STK019", "Zincir 1/2x5/16 ASA40",      "Makine Parçası","metre", 55,  30,  18,    28,  "Çelik Zincir"),
    ("STK020", "O-Ring Contası Ø50",         "Sarf",        "adet", 500, 200,   1.2,   2.1, "Trelleborg"),
    ("STK021", "Kaplin Elastik 1008",         "Makine Parçası","adet", 16,  10, 125,   175,  "Rexnord"),
    ("STK022", "Basınç Manometresi 10 bar",   "Enstrüman",   "adet",  22,  10,  85,   130,  "Wika"),
    ("STK023", "Termometre Bimetal 200°C",    "Enstrüman",   "adet",  14,  10,  72,   110,  "Wika"),
    ("STK024", "Bant Konveyör Lastiği 500mm", "Hammadde",    "metre", 40,  30, 220,   310,  "Goodyear"),
    ("STK025", "Profil Demir HEA 120",        "Hammadde",    "metre", 68,  40,  52,    75,  "Kardemir A.Ş."),
    ("STK026", "CNC Frez Takımı Ø10",        "Kesici Takım","adet",  35,  20,  95,   145,  "Sandvik"),
    ("STK027", "Matkap Ucu HSS 8mm",         "Kesici Takım","adet",  90,  30,  12,    19,  "Dormer"),
    ("STK028", "Lazer Kesim Nozul Ø1.5",     "Yedek Parça", "adet",   7,  10, 280,   410,  "Trumpf"),
    ("STK029", "Plazma Elektrodu 80A",        "Sarf",        "adet", 120,  50,  18,    28,  "Hypertherm"),
    ("STK030", "Yağ Nipeli M8",              "Sarf",        "adet", 350, 100,   0.9,   1.8, "Tecalemit"),
    ("STK031", "Hidrolik Pompa Gear 16cc",    "Yedek Parça", "adet",   5,   8, 680,   950,  "Bosch Rexroth"),
    ("STK032", "Selenoid Valf 24VDC",        "Elektrik",    "adet",  18,  10, 185,   265,  "Asco"),
    ("STK033", "Güç Kaynağı 24V 10A",        "Elektrik",    "adet",   9,   8, 240,   340,  "Phoenix Contact"),
    ("STK034", "Dönüştürücü 4-20mA",         "Otomasyon",   "adet",  11,   5, 320,   460,  "ABB"),
    ("STK035", "Flanş DN80 PN10",            "Bağlantı",    "adet",  28,  20,  42,    65,  "DIN Flanş"),
    ("STK036", "Cıvata M12x50 8.8",          "Bağlantı",    "adet", 600, 200,   0.8,   1.4, "Norm Civata"),
    ("STK037", "Kenet Klips Ø25",            "Bağlantı",    "adet", 280, 100,   2.5,   4.0, "Stauff"),
    ("STK038", "Emniyet Valfi 1/2\" 6 bar",  "Pnömatik",    "adet",  24,  10, 115,   165,  "SMC"),
    ("STK039", "Boya Epoksi Gri 10L",        "Sarf",        "teneke", 14,  8,  320,   460,  "Jotun"),
    ("STK040", "Köpük Conta 10mm",           "Sarf",        "metre", 200, 80,   3.2,   5.5, "Armacell"),
    ("STK041", "Taşlama Diski 125mm",        "Sarf",        "adet", 410, 150,   5.5,   8.5, "Bosch"),
    ("STK042", "Kapasitif Sensör M30",       "Otomasyon",   "adet",  16,  10,  48,    75,  "Balluff"),
    ("STK043", "Encoder 1024 ppr",           "Otomasyon",   "adet",   4,   5, 450,   650,  "Heidenhain"),
    ("STK044", "Yağlama Pompası Manual",     "Yedek Parça", "adet",   7,   5, 195,   280,  "Lincoln"),
    ("STK045", "Sızdırmazlık Keçesi 60x80",  "Yedek Parça", "adet",  45,  20,  22,    35,  "SKF"),
    ("STK046", "Alüminyum Döküm Gövde",      "Hammadde",    "adet",  30,  25, 850, 1_150,  "Dökümhane A.Ş."),
    ("STK047", "Paslanmaz Boru 50x2mm",      "Hammadde",    "metre",  55,  30, 145,   210,  "Akyapı Paslanmaz"),
    ("STK048", "İzolasyon Bandı Silikon",    "Sarf",        "rulo", 180,  60,   8.5,  13.5, "3M Türkiye"),
]


def mevsim_carpani(fatura_tarihi: date) -> float:
    """Makine sektöründe yaz sonu/başı (Şubat-Mayıs) ve Eylül-Kasım yoğun."""
    ay = fatura_tarihi.month
    if ay in (2, 3, 4, 5):    return random.uniform(1.15, 1.40)  # ilkbahar sezonu
    if ay in (9, 10, 11):      return random.uniform(1.10, 1.30)  # sonbahar sezonu
    if ay in (7, 8):           return random.uniform(0.70, 0.90)  # yaz durgunluğu
    return random.uniform(0.90, 1.10)


def random_date_in_range(start: date, end: date) -> date:
    delta = (end - start).days
    return start + timedelta(days=random.randint(0, delta))


def fatura_no_olustur(idx: int, yil: int, ay: int) -> str:
    return f"FAT{yil}{ay:02d}{idx:04d}"


def insert_musteriler(cur):
    print("  → Müşteriler yükleniyor...")
    for row in MUSTERILER_DATA:
        kod, ad, sektor, sehir, tel, email, vergi, limit = row
        cur.execute("""
            INSERT INTO musteriler
              (kod,ad,sektor,sehir,telefon,email,vergi_no,kredi_limiti,aktif,olusturma_tarihi)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,TRUE,%s)
            ON CONFLICT (kod) DO NOTHING
        """, (kod, ad, sektor, sehir, tel, email, vergi, limit,
              date(2024, 1, 1)))
    print(f"    {len(MUSTERILER_DATA)} müşteri eklendi.")


def insert_stok(cur):
    print("  → Stok kalemleri yükleniyor...")
    for row in STOK_DATA:
        kod, ad, kategori, birim, mevcut, minimum, maliyet, satis, tedarikci = row
        cur.execute("""
            INSERT INTO stok
              (kod,ad,kategori,birim,mevcut_miktar,minimum_miktar,
               birim_maliyet,birim_satis,tedarikci,son_guncelleme)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (kod) DO NOTHING
        """, (kod, ad, kategori, birim, mevcut, minimum, maliyet, satis,
              tedarikci, date.today()))
    print(f"    {len(STOK_DATA)} stok kalemi eklendi.")


def insert_faturalar_odemeler(cur):
    """18 aylık fatura + ödeme verisi üret."""
    print("  → Fatura ve ödeme verisi üretiliyor (18 ay)...")

    bugun = date.today()
    baslangic = date(bugun.year - 1, bugun.month, 1) - timedelta(days=180)

    musteri_ids = list(range(1, len(MUSTERILER_DATA) + 1))
    fatura_sayac = 0
    odeme_sayac = 0

    # Her ay ~25-40 fatura
    gun = baslangic
    ay_basi = date(baslangic.year, baslangic.month, 1)

    while ay_basi <= bugun:
        sonraki_ay = date(ay_basi.year + (ay_basi.month // 12),
                          (ay_basi.month % 12) + 1, 1)
        ay_sonu = sonraki_ay - timedelta(days=1)

        carpan = mevsim_carpani(ay_basi)
        aylik_fatura = int(random.randint(22, 38) * carpan)

        for i in range(aylik_fatura):
            fatura_tarihi = random_date_in_range(ay_basi, min(ay_sonu, bugun))
            vade_gun = random.choice([30, 45, 60, 90])
            vade_tarihi = fatura_tarihi + timedelta(days=vade_gun)

            musteri_id = random.choice(musteri_ids)
            tutar = Decimal(str(round(random.uniform(5_000, 85_000) * carpan, 2)))
            kdv = round(tutar * Decimal("0.20"), 2)
            toplam = tutar + kdv

            fatura_sayac += 1
            fn = fatura_no_olustur(fatura_sayac, fatura_tarihi.year, fatura_tarihi.month)

            # Durum belirleme
            if vade_tarihi < bugun:
                r = random.random()
                if r < 0.60:    durum = "odendi"
                elif r < 0.80:  durum = "gecikti"
                elif r < 0.92:  durum = "kismi_odendi"
                else:           durum = "beklemede"
            else:
                r = random.random()
                if r < 0.15:    durum = "odendi"
                elif r < 0.30:  durum = "kismi_odendi"
                else:           durum = "beklemede"

            cur.execute("""
                INSERT INTO faturalar
                  (fatura_no,musteri_id,fatura_tarihi,vade_tarihi,
                   tutar,kdv_tutari,toplam_tutar,durum)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (fatura_no) DO NOTHING
                RETURNING id
            """, (fn, musteri_id, fatura_tarihi, vade_tarihi,
                  tutar, kdv, toplam, durum))

            row = cur.fetchone()
            if not row:
                continue
            fatura_id = row[0]

            # Ödeme ekle
            if durum == "odendi":
                odeme_tarihi = vade_tarihi - timedelta(days=random.randint(0, 10))
                if odeme_tarihi > bugun:
                    odeme_tarihi = bugun
                cur.execute("""
                    INSERT INTO odemeler
                      (fatura_id,odeme_tarihi,tutar,odeme_yontemi,referans_no)
                    VALUES (%s,%s,%s,%s,%s)
                """, (fatura_id, odeme_tarihi, toplam,
                      random.choice(["havale","havale","kredi_karti","nakit"]),
                      f"REF{fake.numerify('########')}"))
                odeme_sayac += 1

            elif durum == "kismi_odendi":
                kismi = round(toplam * Decimal(str(random.uniform(0.3, 0.75))), 2)
                odeme_tarihi = fatura_tarihi + timedelta(days=random.randint(5, 25))
                if odeme_tarihi > bugun:
                    odeme_tarihi = bugun
                cur.execute("""
                    INSERT INTO odemeler
                      (fatura_id,odeme_tarihi,tutar,odeme_yontemi,referans_no)
                    VALUES (%s,%s,%s,%s,%s)
                """, (fatura_id, odeme_tarihi, kismi,
                      random.choice(["havale","cek","senet"]),
                      f"REF{fake.numerify('########')}"))
                odeme_sayac += 1

        ay_basi = sonraki_ay

    print(f"    {fatura_sayac} fatura, {odeme_sayac} ödeme eklendi.")


def main():
    print("KOBİ Rapor — Veri yükleme başlıyor...")
    conn = psycopg2.connect(**DB)
    conn.autocommit = False
    cur = conn.cursor()

    try:
        insert_musteriler(cur)
        insert_stok(cur)
        insert_faturalar_odemeler(cur)
        conn.commit()
        print("\nTüm veriler başarıyla yüklendi!")

        # Özet
        cur.execute("SELECT COUNT(*) FROM musteriler")
        print(f"  Müşteri: {cur.fetchone()[0]}")
        cur.execute("SELECT COUNT(*), SUM(toplam_tutar) FROM faturalar")
        r = cur.fetchone()
        print(f"  Fatura:  {r[0]} adet / {r[1]:,.0f} TL toplam")
        cur.execute("SELECT COUNT(*), SUM(tutar) FROM odemeler")
        r = cur.fetchone()
        print(f"  Ödeme:   {r[0]} adet / {r[1]:,.0f} TL toplam")
        cur.execute("SELECT COUNT(*) FROM geciken_alacaklar")
        print(f"  Geciken alacak: {cur.fetchone()[0]} fatura")
        cur.execute("SELECT COUNT(*) FROM kritik_stok")
        print(f"  Kritik stok: {cur.fetchone()[0]} kalem")

    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
