"""
Metabase Dashboard Kurulum Scripti
4 dashboard oluşturur:
  1. Nakit Durumu
  2. Satış Özeti
  3. Alacak Takibi
  4. Yönetici Özeti
"""

import requests
import json
import sys

BASE = "http://localhost:3000"
EMAIL = "admin@yilmazmakine.com.tr"
PASS  = "KobiRapor2024!"

# Tablo ID'leri (önceki adımda alındı)
T = {
    "faturalar":           12,
    "geciken_alacaklar":    9,
    "kritik_stok":         14,
    "musteriler":          11,
    "odemeler":            10,
    "stok":                13,
}
DB_ID = 2


def login():
    r = requests.post(f"{BASE}/api/session",
                      json={"username": EMAIL, "password": PASS})
    return r.json()["id"]


def headers(token):
    return {"X-Metabase-Session": token, "Content-Type": "application/json"}


def create_question(h, name, query_type, dataset_query, display="table",
                    visualization_settings=None, collection_id=None):
    payload = {
        "name": name,
        "dataset_query": dataset_query,
        "display": display,
        "visualization_settings": visualization_settings or {},
        "collection_id": collection_id,
    }
    r = requests.post(f"{BASE}/api/card", json=payload, headers=h)
    if r.status_code not in (200, 202):
        print(f"  HATA [{r.status_code}]: {r.text[:200]}")
        return None
    return r.json()["id"]


def create_dashboard(h, name, description="", collection_id=None):
    r = requests.post(f"{BASE}/api/dashboard",
                      json={"name": name, "description": description,
                            "collection_id": collection_id},
                      headers=h)
    return r.json()["id"]


def add_card_to_dashboard(h, dash_id, card_id, row, col, size_x=8, size_y=6):
    payload = {
        "cardId": card_id,
        "row": row, "col": col,
        "size_x": size_x, "size_y": size_y,
    }
    r = requests.post(f"{BASE}/api/dashboard/{dash_id}/cards",
                      json=payload, headers=h)
    return r.status_code in (200, 202)


def native_query(sql):
    return {
        "type": "native",
        "database": DB_ID,
        "native": {"query": sql},
    }


def table_query(table_id, aggregations=None, breakouts=None, filters=None, order_by=None, limit=None):
    q = {
        "type": "query",
        "database": DB_ID,
        "query": {"source-table": table_id},
    }
    if aggregations: q["query"]["aggregation"]  = aggregations
    if breakouts:    q["query"]["breakout"]     = breakouts
    if filters:      q["query"]["filter"]       = filters
    if order_by:     q["query"]["order-by"]     = order_by
    if limit:        q["query"]["limit"]        = limit
    return q


def main():
    print("Metabase dashboard kurulumu başlıyor...")
    token = login()
    h = headers(token)
    print(f"  Giriş başarılı.")

    # ── Collection ──────────────────────────────────────────────────────────
    r = requests.post(f"{BASE}/api/collection",
                      json={"name": "KOBİ Raporları", "color": "#1a365d"},
                      headers=h)
    col_id = r.json()["id"]
    print(f"  Collection oluşturuldu: KOBİ Raporları (id={col_id})")

    # ════════════════════════════════════════════════════════════════════════
    # DASHBOARD 1: Nakit Durumu
    # ════════════════════════════════════════════════════════════════════════
    print("\n[1/4] Nakit Durumu Dashboard...")
    d1 = create_dashboard(h, "💰 Nakit Durumu",
                          "Tahsilat, bekleyen ve gecikmiş alacak özeti",
                          collection_id=col_id)

    q1a = create_question(h, "Toplam Tahsilat (Son 30 Gün)",
        "native", native_query("""
            SELECT ROUND(SUM(o.tutar)::numeric,2) AS tahsilat_tl
            FROM odemeler o
            JOIN faturalar f ON f.id = o.fatura_id
            WHERE o.odeme_tarihi >= CURRENT_DATE - 30
        """), display="scalar", collection_id=col_id)

    q1b = create_question(h, "Gecikmiş Alacak Toplamı",
        "native", native_query("""
            SELECT ROUND(SUM(kalan_tutar)::numeric,2) AS gecikis_tl
            FROM geciken_alacaklar
        """), display="scalar", collection_id=col_id)

    q1c = create_question(h, "Bekleyen Alacak Toplamı",
        "native", native_query("""
            SELECT ROUND(SUM(toplam_tutar)::numeric,2) AS bekleyen_tl
            FROM faturalar
            WHERE durum IN ('beklemede','kismi_odendi')
        """), display="scalar", collection_id=col_id)

    q1d = create_question(h, "Aylık Tahsilat Trendi",
        "native", native_query("""
            SELECT
                TO_CHAR(DATE_TRUNC('month', o.odeme_tarihi),'YYYY-MM') AS ay,
                ROUND(SUM(o.tutar)::numeric,2) AS tahsilat
            FROM odemeler o
            WHERE o.odeme_tarihi >= CURRENT_DATE - INTERVAL '12 months'
            GROUP BY 1 ORDER BY 1
        """), display="line",
        visualization_settings={
            "graph.x_axis.title_text": "Ay",
            "graph.y_axis.title_text": "Tahsilat (TL)",
        },
        collection_id=col_id)

    q1e = create_question(h, "Fatura Durum Dağılımı",
        "native", native_query("""
            SELECT durum, COUNT(*) AS adet,
                   ROUND(SUM(toplam_tutar)::numeric,2) AS toplam_tl
            FROM faturalar
            GROUP BY durum ORDER BY toplam_tl DESC
        """), display="pie", collection_id=col_id)

    for cid, row, col in [(q1a, 0, 0), (q1b, 0, 8), (q1c, 0, 16),
                           (q1d, 6, 0), (q1e, 6, 14)]:
        if cid:
            sx = 8 if row == 0 else 14
            sy = 4 if row == 0 else 8
            add_card_to_dashboard(h, d1, cid, row, col, sx, sy)
    print(f"   Dashboard 1 oluşturuldu (id={d1})")

    # ════════════════════════════════════════════════════════════════════════
    # DASHBOARD 2: Satış Özeti
    # ════════════════════════════════════════════════════════════════════════
    print("[2/4] Satış Özeti Dashboard...")
    d2 = create_dashboard(h, "📊 Satış Özeti",
                          "Aylık satışlar, müşteri analizi ve mevsimsel trend",
                          collection_id=col_id)

    q2a = create_question(h, "Aylık Satış Tutarı",
        "native", native_query("""
            SELECT
                TO_CHAR(DATE_TRUNC('month', fatura_tarihi),'YYYY-MM') AS ay,
                ROUND(SUM(toplam_tutar)::numeric,2) AS satis_tl,
                COUNT(*) AS fatura_adedi
            FROM faturalar
            WHERE durum != 'iptal'
              AND fatura_tarihi >= CURRENT_DATE - INTERVAL '18 months'
            GROUP BY 1 ORDER BY 1
        """), display="bar",
        visualization_settings={
            "graph.x_axis.title_text": "Ay",
            "graph.y_axis.title_text": "Satış (TL)",
        },
        collection_id=col_id)

    q2b = create_question(h, "En Çok Satış Yapılan Müşteriler (Top 10)",
        "native", native_query("""
            SELECT m.ad AS musteri, m.sektor,
                   COUNT(f.id) AS fatura_adedi,
                   ROUND(SUM(f.toplam_tutar)::numeric,2) AS toplam_satis
            FROM faturalar f
            JOIN musteriler m ON m.id = f.musteri_id
            WHERE f.durum != 'iptal'
            GROUP BY m.ad, m.sektor
            ORDER BY toplam_satis DESC LIMIT 10
        """), display="bar",
        visualization_settings={
            "graph.x_axis.title_text": "Müşteri",
            "graph.y_axis.title_text": "Toplam Satış (TL)",
        },
        collection_id=col_id)

    q2c = create_question(h, "Sektöre Göre Satış Dağılımı",
        "native", native_query("""
            SELECT m.sektor,
                   ROUND(SUM(f.toplam_tutar)::numeric,2) AS toplam_tl
            FROM faturalar f
            JOIN musteriler m ON m.id = f.musteri_id
            WHERE f.durum != 'iptal'
            GROUP BY m.sektor ORDER BY toplam_tl DESC
        """), display="pie", collection_id=col_id)

    q2d = create_question(h, "Ortalama Fatura Tutarı (Aylık)",
        "native", native_query("""
            SELECT
                TO_CHAR(DATE_TRUNC('month', fatura_tarihi),'YYYY-MM') AS ay,
                ROUND(AVG(toplam_tutar)::numeric,2) AS ort_fatura
            FROM faturalar
            WHERE durum != 'iptal'
              AND fatura_tarihi >= CURRENT_DATE - INTERVAL '12 months'
            GROUP BY 1 ORDER BY 1
        """), display="line", collection_id=col_id)

    for cid, row, col, sx, sy in [
        (q2a, 0, 0, 24, 8), (q2b, 8, 0, 16, 8),
        (q2c, 8, 16, 8, 8), (q2d, 16, 0, 24, 6)
    ]:
        if cid:
            add_card_to_dashboard(h, d2, cid, row, col, sx, sy)
    print(f"   Dashboard 2 oluşturuldu (id={d2})")

    # ════════════════════════════════════════════════════════════════════════
    # DASHBOARD 3: Alacak Takibi
    # ════════════════════════════════════════════════════════════════════════
    print("[3/4] Alacak Takibi Dashboard...")
    d3 = create_dashboard(h, "⚠️ Alacak Takibi",
                          "Gecikmiş alacaklar, riskli müşteriler, yaşlandırma analizi",
                          collection_id=col_id)

    q3a = create_question(h, "Gecikmiş Alacak Yaşlandırma",
        "native", native_query("""
            SELECT
                CASE
                    WHEN gecikme_gunu BETWEEN 1  AND 30  THEN '1-30 Gün'
                    WHEN gecikme_gunu BETWEEN 31 AND 60  THEN '31-60 Gün'
                    WHEN gecikme_gunu BETWEEN 61 AND 90  THEN '61-90 Gün'
                    WHEN gecikme_gunu BETWEEN 91 AND 180 THEN '91-180 Gün'
                    ELSE '180+ Gün'
                END AS kategori,
                COUNT(*) AS fatura_adedi,
                ROUND(SUM(kalan_tutar)::numeric,2) AS toplam_tl
            FROM geciken_alacaklar
            GROUP BY 1
            ORDER BY MIN(gecikme_gunu)
        """), display="bar",
        visualization_settings={
            "graph.x_axis.title_text": "Gecikme Kategorisi",
            "graph.y_axis.title_text": "Tutar (TL)",
        },
        collection_id=col_id)

    q3b = create_question(h, "Riskli Müşteriler (En Yüksek Gecikmiş Borç)",
        "native", native_query("""
            SELECT musteri_adi, sehir,
                   COUNT(*) AS gecikis_adedi,
                   ROUND(SUM(kalan_tutar)::numeric,2) AS toplam_gecikis,
                   MAX(gecikme_gunu) AS max_gun
            FROM geciken_alacaklar
            GROUP BY musteri_adi, sehir
            ORDER BY toplam_gecikis DESC LIMIT 10
        """), display="table", collection_id=col_id)

    q3c = create_question(h, "Gecikmiş Fatura Listesi",
        "native", native_query("""
            SELECT fatura_no, musteri_adi, fatura_tarihi, vade_tarihi,
                   ROUND(toplam_tutar::numeric,2) AS toplam,
                   ROUND(kalan_tutar::numeric,2) AS kalan,
                   gecikme_gunu
            FROM geciken_alacaklar
            ORDER BY gecikme_gunu DESC LIMIT 50
        """), display="table", collection_id=col_id)

    q3d = create_question(h, "Toplam Gecikmiş Alacak",
        "native", native_query("""
            SELECT ROUND(SUM(kalan_tutar)::numeric,2) AS gecikis_tl
            FROM geciken_alacaklar
        """), display="scalar", collection_id=col_id)

    q3e = create_question(h, "Gecikmiş Fatura Sayısı",
        "native", native_query("""
            SELECT COUNT(*) AS gecikis_adedi FROM geciken_alacaklar
        """), display="scalar", collection_id=col_id)

    for cid, row, col, sx, sy in [
        (q3d,  0,  0,  8, 4), (q3e,  0, 8,  8, 4),
        (q3a,  4,  0, 14, 8), (q3b,  4, 14, 10, 8),
        (q3c, 12,  0, 24, 8),
    ]:
        if cid:
            add_card_to_dashboard(h, d3, cid, row, col, sx, sy)
    print(f"   Dashboard 3 oluşturuldu (id={d3})")

    # ════════════════════════════════════════════════════════════════════════
    # DASHBOARD 4: Yönetici Özeti
    # ════════════════════════════════════════════════════════════════════════
    print("[4/4] Yönetici Özeti Dashboard...")
    d4 = create_dashboard(h, "🏭 Yönetici Özeti",
                          "KPI'lar, stok alarmları ve genel tablo",
                          collection_id=col_id)

    q4a = create_question(h, "Bu Ay Satış",
        "native", native_query("""
            SELECT ROUND(SUM(toplam_tutar)::numeric,2) AS bu_ay_satis
            FROM faturalar
            WHERE DATE_TRUNC('month', fatura_tarihi) = DATE_TRUNC('month', CURRENT_DATE)
              AND durum != 'iptal'
        """), display="scalar", collection_id=col_id)

    q4b = create_question(h, "Bu Ay Tahsilat",
        "native", native_query("""
            SELECT ROUND(SUM(tutar)::numeric,2) AS bu_ay_tahsilat
            FROM odemeler
            WHERE DATE_TRUNC('month', odeme_tarihi) = DATE_TRUNC('month', CURRENT_DATE)
        """), display="scalar", collection_id=col_id)

    q4c = create_question(h, "Kritik Stok Kalemi",
        "native", native_query("""
            SELECT COUNT(*) AS kritik_stok FROM kritik_stok
        """), display="scalar", collection_id=col_id)

    q4d = create_question(h, "Kritik Stok Listesi",
        "native", native_query("""
            SELECT ad, kategori, birim,
                   mevcut_miktar AS mevcut,
                   minimum_miktar AS minimum,
                   eksik_miktar AS eksik,
                   ROUND(tahmini_maliyet::numeric,2) AS tahmini_maliyet_tl
            FROM kritik_stok
            ORDER BY tahmini_maliyet DESC
        """), display="table", collection_id=col_id)

    q4e = create_question(h, "Son 6 Ay Satış vs Tahsilat",
        "native", native_query("""
            SELECT ay,
                   MAX(satis) AS satis_tl,
                   MAX(tahsilat) AS tahsilat_tl
            FROM (
                SELECT TO_CHAR(DATE_TRUNC('month',fatura_tarihi),'YYYY-MM') AS ay,
                       SUM(toplam_tutar) AS satis, 0 AS tahsilat
                FROM faturalar
                WHERE durum != 'iptal'
                  AND fatura_tarihi >= CURRENT_DATE - INTERVAL '6 months'
                GROUP BY 1
              UNION ALL
                SELECT TO_CHAR(DATE_TRUNC('month',odeme_tarihi),'YYYY-MM') AS ay,
                       0 AS satis, SUM(tutar) AS tahsilat
                FROM odemeler
                WHERE odeme_tarihi >= CURRENT_DATE - INTERVAL '6 months'
                GROUP BY 1
            ) t
            GROUP BY ay ORDER BY ay
        """), display="combo",
        visualization_settings={
            "graph.x_axis.title_text": "Ay",
            "graph.y_axis.title_text": "TL",
        },
        collection_id=col_id)

    q4f = create_question(h, "Ödeme Yöntemine Göre Dağılım",
        "native", native_query("""
            SELECT odeme_yontemi,
                   COUNT(*) AS adet,
                   ROUND(SUM(tutar)::numeric,2) AS toplam_tl
            FROM odemeler
            GROUP BY odeme_yontemi ORDER BY toplam_tl DESC
        """), display="pie", collection_id=col_id)

    for cid, row, col, sx, sy in [
        (q4a,  0,  0,  8, 4), (q4b,  0,  8,  8, 4), (q4c, 0, 16, 8, 4),
        (q4e,  4,  0, 14, 8), (q4f,  4, 14, 10, 8),
        (q4d, 12,  0, 24, 8),
    ]:
        if cid:
            add_card_to_dashboard(h, d4, cid, row, col, sx, sy)
    print(f"   Dashboard 4 oluşturuldu (id={d4})")

    print(f"""
╔══════════════════════════════════════════════════════╗
║  Metabase Dashboard Kurulumu Tamamlandı!             ║
╠══════════════════════════════════════════════════════╣
║  URL: http://localhost:3000                          ║
║  E-posta: admin@yilmazmakine.com.tr                  ║
║  Şifre:   KobiRapor2024!                             ║
╠══════════════════════════════════════════════════════╣
║  Dashboard 1: 💰 Nakit Durumu      (id={d1})
║  Dashboard 2: 📊 Satış Özeti       (id={d2})
║  Dashboard 3: ⚠️  Alacak Takibi    (id={d3})
║  Dashboard 4: 🏭 Yönetici Özeti    (id={d4})
╚══════════════════════════════════════════════════════╝
""")


if __name__ == "__main__":
    main()
