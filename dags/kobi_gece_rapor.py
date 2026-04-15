"""
KOBİ Rapor Sistemi — Gece ETL + Sabah E-posta DAG'ı
Çalışma zamanı: Her gece 02:00 (Türkiye saati UTC+3 → UTC 23:00)
Görevler:
  1. kobi_db health check
  2. Gecikmiş faturaların durumunu güncelle (beklemede → gecikti)
  3. Nakit durumu snapshot'ı hesapla
  4. Satış özeti hesapla
  5. Alacak takibi hesapla
  6. Stok alarm kontrolü
  7. Sabah 07:00'de özet e-posta gönder (UTC 04:00)
"""

from __future__ import annotations

import os
import smtplib
import logging
from datetime import date, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import psycopg2
import psycopg2.extras

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.utils.dates import days_ago

log = logging.getLogger(__name__)

# ── Bağlantı ──────────────────────────────────────────────────────────────────
def get_conn():
    return psycopg2.connect(
        host=os.environ.get("KOBI_DB_HOST", "postgres"),
        port=int(os.environ.get("KOBI_DB_PORT", 5432)),
        dbname=os.environ.get("KOBI_DB_NAME", "kobi_db"),
        user=os.environ.get("KOBI_DB_USER", "kobi"),
        password=os.environ.get("KOBI_DB_PASS", "kobi123"),
    )


# ── Task 1: DB health check ───────────────────────────────────────────────────
def db_health_check(**ctx):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM faturalar")
    count = cur.fetchone()[0]
    conn.close()
    log.info(f"DB sağlıklı. Fatura sayısı: {count}")
    return count


# ── Task 2: Gecikmiş faturaları güncelle ──────────────────────────────────────
def guncelle_gecikis(**ctx):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        UPDATE faturalar
        SET durum = 'gecikti'
        WHERE durum = 'beklemede'
          AND vade_tarihi < CURRENT_DATE
    """)
    guncellenen = cur.rowcount
    conn.commit()
    conn.close()
    log.info(f"{guncellenen} fatura 'gecikti' olarak işaretlendi.")
    return guncellenen


# ── Task 3: Nakit durumu snapshot ────────────────────────────────────────────
def nakit_durumu_hesapla(**ctx):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT
            SUM(CASE WHEN durum='odendi' THEN toplam_tutar ELSE 0 END)            AS tahsil_edilen,
            SUM(CASE WHEN durum IN ('beklemede','kismi_odendi') THEN toplam_tutar ELSE 0 END) AS bekleyen_alacak,
            SUM(CASE WHEN durum='gecikti'  THEN toplam_tutar ELSE 0 END)           AS gecikis_tutari,
            SUM(CASE WHEN durum IN ('kismi_odendi') THEN
                    toplam_tutar - COALESCE((
                        SELECT SUM(o.tutar) FROM odemeler o WHERE o.fatura_id = faturalar.id
                    ),0)
                ELSE 0 END)                                                        AS kismi_kalan
        FROM faturalar
        WHERE fatura_tarihi >= CURRENT_DATE - INTERVAL '30 days'
    """)
    r = cur.fetchone()
    conn.close()

    ozet = {k: float(v or 0) for k, v in r.items()}
    log.info(f"Nakit durumu: {ozet}")
    ctx["ti"].xcom_push(key="nakit", value=ozet)
    return ozet


# ── Task 4: Satış özeti ───────────────────────────────────────────────────────
def satis_ozeti_hesapla(**ctx):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT
            COUNT(*)                                    AS fatura_adedi,
            SUM(toplam_tutar)                           AS toplam_satis,
            AVG(toplam_tutar)                           AS ortalama_fatura,
            MAX(toplam_tutar)                           AS en_buyuk_fatura,
            COUNT(DISTINCT musteri_id)                  AS aktif_musteri
        FROM faturalar
        WHERE fatura_tarihi >= CURRENT_DATE - INTERVAL '30 days'
          AND durum != 'iptal'
    """)
    r = cur.fetchone()

    cur.execute("""
        SELECT m.ad, SUM(f.toplam_tutar) AS toplam
        FROM faturalar f
        JOIN musteriler m ON f.musteri_id = m.id
        WHERE f.fatura_tarihi >= CURRENT_DATE - INTERVAL '30 days'
          AND f.durum != 'iptal'
        GROUP BY m.ad
        ORDER BY toplam DESC
        LIMIT 5
    """)
    top5 = cur.fetchall()

    conn.close()
    ozet = {k: float(v or 0) for k, v in r.items()}
    ozet["top5_musteri"] = [(row["ad"], float(row["toplam"])) for row in top5]
    log.info(f"Satış özeti: {ozet}")
    ctx["ti"].xcom_push(key="satis", value=ozet)
    return ozet


# ── Task 5: Alacak takibi ─────────────────────────────────────────────────────
def alacak_takibi(**ctx):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT
            COUNT(*)             AS gecikis_adedi,
            SUM(kalan_tutar)     AS toplam_gecikis,
            MAX(gecikme_gunu)    AS max_gecikme_gunu,
            AVG(gecikme_gunu)    AS ort_gecikme_gunu
        FROM geciken_alacaklar
    """)
    r = cur.fetchone()

    cur.execute("""
        SELECT musteri_adi, SUM(kalan_tutar) AS toplam, MAX(gecikme_gunu) AS max_gun
        FROM geciken_alacaklar
        GROUP BY musteri_adi
        ORDER BY toplam DESC
        LIMIT 5
    """)
    riskli = cur.fetchall()

    conn.close()
    ozet = {k: float(v or 0) for k, v in r.items()}
    ozet["riskli_musteriler"] = [
        (row["musteri_adi"], float(row["toplam"]), int(row["max_gun"]))
        for row in riskli
    ]
    log.info(f"Alacak takibi: {ozet}")
    ctx["ti"].xcom_push(key="alacak", value=ozet)
    return ozet


# ── Task 6: Stok alarm ────────────────────────────────────────────────────────
def stok_alarm_kontrol(**ctx):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT ad, kategori, birim, mevcut_miktar, minimum_miktar,
               eksik_miktar, tahmini_maliyet
        FROM kritik_stok
        ORDER BY tahmini_maliyet DESC
    """)
    kritikler = cur.fetchall()
    conn.close()

    alarm_listesi = [dict(r) for r in kritikler]
    log.info(f"{len(alarm_listesi)} kritik stok kalemi tespit edildi.")
    ctx["ti"].xcom_push(key="stok_alarm", value=alarm_listesi)
    return alarm_listesi


# ── Task 7: E-posta raporu ────────────────────────────────────────────────────
def email_rapor_gonder(**ctx):
    ti = ctx["ti"]
    nakit   = ti.xcom_pull(key="nakit",       task_ids="nakit_durumu_hesapla") or {}
    satis   = ti.xcom_pull(key="satis",        task_ids="satis_ozeti_hesapla") or {}
    alacak  = ti.xcom_pull(key="alacak",       task_ids="alacak_takibi")       or {}
    stoklar = ti.xcom_pull(key="stok_alarm",   task_ids="stok_alarm_kontrol")  or []

    bugun = date.today().strftime("%d.%m.%Y")

    def tl(v): return f"{v:,.0f} ₺"

    # Top 5 müşteri satır HTML
    top5_html = "".join(
        f"<tr><td>{i+1}. {ad}</td><td style='text-align:right'>{tl(tutar)}</td></tr>"
        for i, (ad, tutar) in enumerate(satis.get("top5_musteri", []))
    )

    # Riskli müşteriler HTML
    riskli_html = "".join(
        f"<tr><td>{ad}</td><td style='text-align:right'>{tl(tutar)}</td><td style='text-align:right'>{gun} gün</td></tr>"
        for ad, tutar, gun in alacak.get("riskli_musteriler", [])
    )

    # Kritik stok HTML
    stok_html = "".join(
        f"<tr><td>{s['ad']}</td><td>{s['mevcut_miktar']} {s['birim']}</td>"
        f"<td>{s['minimum_miktar']} {s['birim']}</td><td style='text-align:right'>{tl(s['tahmini_maliyet'])}</td></tr>"
        for s in stoklar[:8]
    )

    html = f"""
    <html><body style="font-family:Arial,sans-serif;color:#333;max-width:700px">
    <div style="background:#1a365d;color:white;padding:20px;border-radius:8px 8px 0 0">
        <h2 style="margin:0">🏭 Yılmaz Makine Ltd. — Yönetici Raporu</h2>
        <p style="margin:5px 0 0;opacity:.8">{bugun} | Otomatik Sabah Raporu</p>
    </div>

    <div style="background:#f8fafc;padding:20px;border:1px solid #e2e8f0">

    <!-- Nakit Durumu -->
    <h3 style="color:#1a365d;border-bottom:2px solid #3182ce;padding-bottom:5px">💰 Nakit Durumu (Son 30 Gün)</h3>
    <table width="100%" cellpadding="8" style="border-collapse:collapse">
        <tr style="background:#ebf8ff"><td><b>Tahsil Edilen</b></td>
            <td align="right" style="color:#276749;font-size:1.1em"><b>{tl(nakit.get('tahsil_edilen',0))}</b></td></tr>
        <tr><td>Bekleyen Alacak</td><td align="right">{tl(nakit.get('bekleyen_alacak',0))}</td></tr>
        <tr style="background:#fff5f5"><td><b>Gecikmiş Alacak</b></td>
            <td align="right" style="color:#c53030"><b>{tl(nakit.get('gecikis_tutari',0))}</b></td></tr>
    </table>

    <!-- Satış Özeti -->
    <h3 style="color:#1a365d;border-bottom:2px solid #3182ce;padding-bottom:5px;margin-top:25px">📊 Satış Özeti (Son 30 Gün)</h3>
    <table width="100%" cellpadding="8" style="border-collapse:collapse">
        <tr style="background:#ebf8ff"><td>Toplam Satış</td>
            <td align="right"><b>{tl(satis.get('toplam_satis',0))}</b></td></tr>
        <tr><td>Fatura Adedi</td><td align="right">{int(satis.get('fatura_adedi',0))}</td></tr>
        <tr><td>Ortalama Fatura</td><td align="right">{tl(satis.get('ortalama_fatura',0))}</td></tr>
        <tr><td>Aktif Müşteri</td><td align="right">{int(satis.get('aktif_musteri',0))}</td></tr>
    </table>
    {'<h4>Top 5 Müşteri:</h4><table width="100%" cellpadding="6" style="border-collapse:collapse;font-size:.9em">' + top5_html + '</table>' if top5_html else ''}

    <!-- Alacak Takibi -->
    <h3 style="color:#1a365d;border-bottom:2px solid #e53e3e;padding-bottom:5px;margin-top:25px">⚠️ Alacak Takibi</h3>
    <table width="100%" cellpadding="8" style="border-collapse:collapse">
        <tr style="background:#fff5f5"><td>Gecikmiş Fatura</td>
            <td align="right"><b>{int(alacak.get('gecikis_adedi',0))} adet</b></td></tr>
        <tr><td>Gecikmiş Toplam</td>
            <td align="right" style="color:#c53030"><b>{tl(alacak.get('toplam_gecikis',0))}</b></td></tr>
        <tr><td>Maks. Gecikme</td><td align="right">{int(alacak.get('max_gecikme_gunu',0))} gün</td></tr>
    </table>
    {'<h4>Riskli Müşteriler:</h4><table width="100%" cellpadding="6" style="border-collapse:collapse;font-size:.9em"><tr style="background:#fed7d7"><th align="left">Müşteri</th><th>Tutar</th><th>Gecikme</th></tr>' + riskli_html + '</table>' if riskli_html else ''}

    <!-- Stok Alarmı -->
    {'<h3 style="color:#1a365d;border-bottom:2px solid #d69e2e;padding-bottom:5px;margin-top:25px">📦 Kritik Stok Uyarısı</h3><table width="100%" cellpadding="6" style="border-collapse:collapse;font-size:.9em"><tr style="background:#fefcbf"><th align="left">Ürün</th><th>Mevcut</th><th>Minimum</th><th>Tahmini Maliyet</th></tr>' + stok_html + '</table>' if stok_html else ''}

    </div>
    <div style="background:#718096;color:white;padding:10px;text-align:center;font-size:.8em;border-radius:0 0 8px 8px">
        Yılmaz Makine Ltd. | Otomatik Raporlama Sistemi | {bugun}
    </div>
    </body></html>
    """

    smtp_host = os.environ.get("SMTP_HOST", "")
    smtp_port = int(os.environ.get("SMTP_PORT", 587))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")
    to_email  = os.environ.get("REPORT_EMAIL", smtp_user)

    if not smtp_host or not smtp_user or not smtp_pass:
        log.warning("SMTP ayarları eksik — e-posta gönderilmedi. HTML rapor üretildi.")
        log.info("HTML RAPOR:\n" + html[:500] + "...")
        return "SMTP_SKIP"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[Yılmaz Makine] Yönetici Raporu — {bugun}"
    msg["From"]    = smtp_user
    msg["To"]      = to_email
    msg.attach(MIMEText(html, "html", "utf-8"))

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_user, to_email, msg.as_string())

    log.info(f"E-posta gönderildi → {to_email}")
    return to_email


# ── DAG Tanımı ────────────────────────────────────────────────────────────────
default_args = {
    "owner": "kobi",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": False,
}

with DAG(
    dag_id="kobi_gece_rapor",
    description="KOBİ gece ETL ve sabah yönetici e-posta raporu",
    schedule_interval="0 23 * * *",   # UTC 23:00 = Türkiye 02:00
    start_date=days_ago(1),
    catchup=False,
    default_args=default_args,
    tags=["kobi", "rapor", "etl"],
) as dag:

    t1 = PythonOperator(task_id="db_health_check",        python_callable=db_health_check)
    t2 = PythonOperator(task_id="guncelle_gecikis",       python_callable=guncelle_gecikis)
    t3 = PythonOperator(task_id="nakit_durumu_hesapla",   python_callable=nakit_durumu_hesapla)
    t4 = PythonOperator(task_id="satis_ozeti_hesapla",    python_callable=satis_ozeti_hesapla)
    t5 = PythonOperator(task_id="alacak_takibi",          python_callable=alacak_takibi)
    t6 = PythonOperator(task_id="stok_alarm_kontrol",     python_callable=stok_alarm_kontrol)
    t7 = PythonOperator(task_id="email_rapor_gonder",     python_callable=email_rapor_gonder)

    t1 >> t2 >> [t3, t4, t5, t6] >> t7
