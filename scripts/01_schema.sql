-- ============================================================
-- KOBİ Rapor Sistemi - Veritabanı Şeması
-- ============================================================

-- Müşteriler tablosu
CREATE TABLE IF NOT EXISTS musteriler (
    id               SERIAL PRIMARY KEY,
    kod              VARCHAR(20)  UNIQUE NOT NULL,
    ad               VARCHAR(150) NOT NULL,
    sektor           VARCHAR(80),
    sehir            VARCHAR(80),
    telefon          VARCHAR(20),
    email            VARCHAR(120),
    vergi_no         VARCHAR(11)  UNIQUE,
    kredi_limiti     NUMERIC(12,2) DEFAULT 0,
    aktif            BOOLEAN DEFAULT TRUE,
    olusturma_tarihi DATE DEFAULT CURRENT_DATE
);

-- Faturalar tablosu
CREATE TABLE IF NOT EXISTS faturalar (
    id            SERIAL PRIMARY KEY,
    fatura_no     VARCHAR(30) UNIQUE NOT NULL,
    musteri_id    INTEGER REFERENCES musteriler(id),
    fatura_tarihi DATE NOT NULL,
    vade_tarihi   DATE NOT NULL,
    tutar         NUMERIC(12,2) NOT NULL,
    kdv_tutari    NUMERIC(12,2) NOT NULL,
    toplam_tutar  NUMERIC(12,2) NOT NULL,
    durum         VARCHAR(20) DEFAULT 'beklemede'
                  CHECK (durum IN ('beklemede','kismi_odendi','odendi','gecikti','iptal')),
    aciklama      TEXT
);

-- Ödemeler tablosu
CREATE TABLE IF NOT EXISTS odemeler (
    id             SERIAL PRIMARY KEY,
    fatura_id      INTEGER REFERENCES faturalar(id),
    odeme_tarihi   DATE NOT NULL,
    tutar          NUMERIC(12,2) NOT NULL,
    odeme_yontemi  VARCHAR(30) DEFAULT 'havale'
                   CHECK (odeme_yontemi IN ('nakit','havale','kredi_karti','cek','senet')),
    referans_no    VARCHAR(50),
    notlar         TEXT
);

-- Stok tablosu
CREATE TABLE IF NOT EXISTS stok (
    id             SERIAL PRIMARY KEY,
    kod            VARCHAR(30) UNIQUE NOT NULL,
    ad             VARCHAR(150) NOT NULL,
    kategori       VARCHAR(80),
    birim          VARCHAR(20) DEFAULT 'adet',
    mevcut_miktar  NUMERIC(10,2) DEFAULT 0,
    minimum_miktar NUMERIC(10,2) DEFAULT 0,
    birim_maliyet  NUMERIC(12,2) DEFAULT 0,
    birim_satis    NUMERIC(12,2) DEFAULT 0,
    tedarikci      VARCHAR(150),
    son_guncelleme DATE DEFAULT CURRENT_DATE
);

-- View: Geciken alacaklar
CREATE OR REPLACE VIEW geciken_alacaklar AS
SELECT
    f.id,
    f.fatura_no,
    m.ad AS musteri_adi,
    m.sehir,
    f.fatura_tarihi,
    f.vade_tarihi,
    f.toplam_tutar,
    COALESCE(SUM(o.tutar), 0)                    AS odenen_tutar,
    f.toplam_tutar - COALESCE(SUM(o.tutar), 0)   AS kalan_tutar,
    CURRENT_DATE - f.vade_tarihi                  AS gecikme_gunu
FROM faturalar f
JOIN musteriler m ON f.musteri_id = m.id
LEFT JOIN odemeler o ON f.id = o.fatura_id
WHERE f.durum IN ('beklemede','kismi_odendi','gecikti')
  AND f.vade_tarihi < CURRENT_DATE
GROUP BY f.id, f.fatura_no, m.ad, m.sehir,
         f.fatura_tarihi, f.vade_tarihi, f.toplam_tutar;

-- View: Kritik stok alarmı
CREATE OR REPLACE VIEW kritik_stok AS
SELECT
    kod,
    ad,
    kategori,
    birim,
    mevcut_miktar,
    minimum_miktar,
    minimum_miktar - mevcut_miktar          AS eksik_miktar,
    birim_maliyet * minimum_miktar          AS tahmini_maliyet
FROM stok
WHERE mevcut_miktar <= minimum_miktar;
