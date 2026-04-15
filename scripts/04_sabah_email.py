"""
KOBİ Rapor — Sabah 07:00 Yönetici E-posta Scripti
Kullanım:
  python3 04_sabah_email.py                   # .env'den okur
  SMTP_USER=... SMTP_PASS=... python3 04_sabah_email.py
  python3 04_sabah_email.py --dry-run         # SMTP göndermez, HTML kaydeder

Cron (Türkiye 07:00 = UTC 04:00):
  0 4 * * * cd /path/to/scripts && python3 04_sabah_email.py >> /var/log/kobi_email.log 2>&1
"""

import argparse
import os
import smtplib
import sys
from datetime import date, timedelta
from decimal import Decimal
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import psycopg2
import psycopg2.extras

# .env yükle (varsa)
env_file = Path(__file__).parent.parent / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

DB = dict(
    host=os.environ.get("KOBI_DB_HOST", "localhost"),
    port=int(os.environ.get("KOBI_DB_PORT", 5433)),
    dbname=os.environ.get("KOBI_DB_NAME", "kobi_db"),
    user=os.environ.get("KOBI_DB_USER", "kobi"),
    password=os.environ.get("KOBI_DB_PASS", "kobi123"),
)


def tl(v):
    try:
        return f"{float(v):,.0f} ₺"
    except Exception:
        return "— ₺"


def fetch_data():
    conn = psycopg2.connect(**DB)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Nakit durumu
    cur.execute("""
        SELECT
            COALESCE(SUM(CASE WHEN DATE_TRUNC('month',o.odeme_tarihi)=DATE_TRUNC('month',CURRENT_DATE)
                          THEN o.tutar END), 0)                          AS bu_ay_tahsilat,
            COALESCE(SUM(CASE WHEN o.odeme_tarihi >= CURRENT_DATE - 7
                          THEN o.tutar END), 0)                          AS son_7_gun_tahsilat,
            COALESCE(SUM(CASE WHEN f.durum IN ('beklemede','kismi_odendi')
                          THEN f.toplam_tutar END), 0)                   AS bekleyen_alacak,
            COALESCE(SUM(CASE WHEN f.durum = 'gecikti'
                          THEN f.toplam_tutar END), 0)                   AS gecikis_tutari
        FROM faturalar f
        LEFT JOIN odemeler o ON o.fatura_id = f.id
    """)
    nakit = dict(cur.fetchone())

    # Bu ay satış
    cur.execute("""
        SELECT
            COUNT(*) AS fatura_adedi,
            COALESCE(SUM(toplam_tutar),0) AS toplam_satis,
            COUNT(DISTINCT musteri_id) AS aktif_musteri
        FROM faturalar
        WHERE DATE_TRUNC('month',fatura_tarihi) = DATE_TRUNC('month',CURRENT_DATE)
          AND durum != 'iptal'
    """)
    satis = dict(cur.fetchone())

    # Dün satış
    cur.execute("""
        SELECT COALESCE(SUM(toplam_tutar),0) AS dun_satis
        FROM faturalar
        WHERE fatura_tarihi = CURRENT_DATE - 1 AND durum != 'iptal'
    """)
    satis["dun_satis"] = cur.fetchone()["dun_satis"]

    # Alacak takibi
    cur.execute("""
        SELECT
            COUNT(*) AS gecikis_adedi,
            COALESCE(SUM(kalan_tutar),0) AS toplam_gecikis,
            MAX(gecikme_gunu) AS max_gun
        FROM geciken_alacaklar
    """)
    alacak = dict(cur.fetchone())

    # Top 5 riskli müşteri
    cur.execute("""
        SELECT musteri_adi, sehir,
               COUNT(*) AS adet,
               ROUND(SUM(kalan_tutar)::numeric,2) AS toplam,
               MAX(gecikme_gunu) AS max_gun
        FROM geciken_alacaklar
        GROUP BY musteri_adi, sehir
        ORDER BY toplam DESC LIMIT 5
    """)
    riskli = [dict(r) for r in cur.fetchall()]

    # Kritik stok
    cur.execute("""
        SELECT ad, kategori, birim,
               mevcut_miktar, minimum_miktar,
               eksik_miktar,
               ROUND(tahmini_maliyet::numeric,2) AS tahmini_maliyet
        FROM kritik_stok
        ORDER BY tahmini_maliyet DESC LIMIT 10
    """)
    stok = [dict(r) for r in cur.fetchall()]

    # Bugün vade dolan (yaklaşan)
    cur.execute("""
        SELECT COUNT(*) AS adet,
               COALESCE(SUM(toplam_tutar),0) AS toplam
        FROM faturalar
        WHERE vade_tarihi BETWEEN CURRENT_DATE AND CURRENT_DATE + 7
          AND durum IN ('beklemede','kismi_odendi')
    """)
    yaklasan = dict(cur.fetchone())

    conn.close()
    return nakit, satis, alacak, riskli, stok, yaklasan


def build_html(nakit, satis, alacak, riskli, stok, yaklasan):
    bugun = date.today().strftime("%d %B %Y, %A")
    # Türkçe gün/ay
    tr_gunler = {"Monday":"Pazartesi","Tuesday":"Salı","Wednesday":"Çarşamba",
                 "Thursday":"Perşembe","Friday":"Cuma","Saturday":"Cumartesi","Sunday":"Pazar"}
    tr_aylar  = {"January":"Ocak","February":"Şubat","March":"Mart","April":"Nisan",
                 "May":"Mayıs","June":"Haziran","July":"Temmuz","August":"Ağustos",
                 "September":"Eylül","October":"Ekim","November":"Kasım","December":"Aralık"}
    for en, tr in {**tr_gunler, **tr_aylar}.items():
        bugun = bugun.replace(en, tr)

    # KPI renk: gecikmiş yüksekse kırmızı
    gecikis_oran = (float(alacak["toplam_gecikis"] or 0) /
                    max(float(nakit["bekleyen_alacak"] or 1), 1)) * 100

    def kpi(label, value, color="#1a365d", note=""):
        return f"""
        <div style="background:white;border-left:4px solid {color};padding:15px 20px;
                    border-radius:6px;box-shadow:0 2px 4px rgba(0,0,0,.08);flex:1;min-width:160px">
            <div style="font-size:.8em;color:#718096;text-transform:uppercase;letter-spacing:.05em">{label}</div>
            <div style="font-size:1.6em;font-weight:bold;color:{color};margin:4px 0">{value}</div>
            {f'<div style="font-size:.75em;color:#a0aec0">{note}</div>' if note else ''}
        </div>"""

    riskli_rows = "".join(
        f"""<tr style="background:{'#fff5f5' if i%2==0 else 'white'}">
            <td style="padding:8px">{r['musteri_adi']}</td>
            <td style="padding:8px">{r['sehir']}</td>
            <td style="padding:8px;text-align:right">{r['adet']}</td>
            <td style="padding:8px;text-align:right;color:#c53030;font-weight:bold">{tl(r['toplam'])}</td>
            <td style="padding:8px;text-align:right">{r['max_gun']} gün</td>
        </tr>"""
        for i, r in enumerate(riskli)
    )

    stok_rows = "".join(
        f"""<tr style="background:{'#fffbeb' if i%2==0 else 'white'}">
            <td style="padding:8px">{s['ad']}</td>
            <td style="padding:8px">{s['kategori']}</td>
            <td style="padding:8px;text-align:right;color:#c53030;font-weight:bold">
                {s['mevcut_miktar']} {s['birim']}</td>
            <td style="padding:8px;text-align:right">{s['minimum_miktar']} {s['birim']}</td>
            <td style="padding:8px;text-align:right">{tl(s['tahmini_maliyet'])}</td>
        </tr>"""
        for i, s in enumerate(stok)
    )

    yaklasan_info = ""
    if float(yaklasan.get("adet", 0)) > 0:
        yaklasan_info = f"""
        <div style="background:#ebf8ff;border:1px solid #bee3f8;padding:12px 16px;
                    border-radius:6px;margin-bottom:20px">
            <b>📅 Önümüzdeki 7 gün içinde vadesi dolacak:</b>
            {int(yaklasan['adet'])} fatura / {tl(yaklasan['toplam'])}
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Yılmaz Makine — Sabah Raporu</title></head>
<body style="margin:0;padding:0;background:#f7fafc;font-family:'Segoe UI',Arial,sans-serif;color:#2d3748">

<table width="100%" cellpadding="0" cellspacing="0" style="max-width:700px;margin:0 auto">
<tr><td>

<!-- HEADER -->
<div style="background:linear-gradient(135deg,#1a365d,#2b6cb0);color:white;
            padding:28px 30px;border-radius:10px 10px 0 0">
    <div style="font-size:.85em;opacity:.7;margin-bottom:4px">Otomatik Sabah Raporu</div>
    <h1 style="margin:0;font-size:1.6em">🏭 Yılmaz Makine Ltd.</h1>
    <div style="font-size:.9em;opacity:.85;margin-top:6px">{bugun}</div>
</div>

<!-- BODY -->
<div style="background:white;padding:28px 30px;border:1px solid #e2e8f0;border-top:none">

{yaklasan_info}

<!-- KPI ROW -->
<h3 style="color:#1a365d;margin-top:0;border-bottom:2px solid #e2e8f0;padding-bottom:8px">
    📊 Bugünün Özeti</h3>
<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:24px">
    {kpi("Bu Ay Satış", tl(satis['toplam_satis']), "#2b6cb0",
         f"{int(satis['fatura_adedi'])} fatura")}
    {kpi("Bu Ay Tahsilat", tl(nakit['bu_ay_tahsilat']), "#276749")}
    {kpi("Bekleyen Alacak", tl(nakit['bekleyen_alacak']), "#d69e2e")}
    {kpi("Gecikmiş Alacak", tl(alacak['toplam_gecikis']), "#c53030",
         f"{int(alacak['gecikis_adedi'])} fatura")}
</div>

<div style="display:flex;gap:12px;flex-wrap:wrap;margin-bottom:28px">
    {kpi("Dün Satış", tl(satis['dun_satis']), "#553c9a")}
    {kpi("Son 7 Gün Tahsilat", tl(nakit['son_7_gun_tahsilat']), "#2c7a7b")}
    {kpi("Aktif Müşteri", int(satis['aktif_musteri']), "#2b6cb0", "bu ay")}
    {kpi("Maks. Gecikme", f"{int(alacak.get('max_gun') or 0)} gün", "#c53030")}
</div>

{f'''
<!-- RISKLI MUSTERILER -->
<h3 style="color:#c53030;border-bottom:2px solid #fed7d7;padding-bottom:8px">
    ⚠️ Riskli Müşteriler — Gecikmiş Alacak</h3>
<table width="100%" cellpadding="0" cellspacing="0"
       style="border-collapse:collapse;font-size:.9em;margin-bottom:24px">
    <tr style="background:#c53030;color:white">
        <th style="padding:10px;text-align:left">Müşteri</th>
        <th style="padding:10px;text-align:left">Şehir</th>
        <th style="padding:10px;text-align:right">Fatura</th>
        <th style="padding:10px;text-align:right">Gecikmiş Tutar</th>
        <th style="padding:10px;text-align:right">Maks. Gecikme</th>
    </tr>
    {riskli_rows}
</table>''' if riskli else ''}

{f'''
<!-- KRITIK STOK -->
<h3 style="color:#d69e2e;border-bottom:2px solid #fefcbf;padding-bottom:8px">
    📦 Kritik Stok Uyarısı</h3>
<table width="100%" cellpadding="0" cellspacing="0"
       style="border-collapse:collapse;font-size:.9em;margin-bottom:24px">
    <tr style="background:#d69e2e;color:white">
        <th style="padding:10px;text-align:left">Ürün</th>
        <th style="padding:10px;text-align:left">Kategori</th>
        <th style="padding:10px;text-align:right">Mevcut</th>
        <th style="padding:10px;text-align:right">Minimum</th>
        <th style="padding:10px;text-align:right">Tahmini Maliyet</th>
    </tr>
    {stok_rows}
</table>''' if stok else ''}

<!-- HIZLI ERISIM -->
<div style="background:#f7fafc;border:1px solid #e2e8f0;border-radius:6px;padding:16px">
    <b>🔗 Hızlı Erişim</b><br>
    <a href="http://localhost:3000" style="color:#2b6cb0">Metabase Dashboard</a> &nbsp;|&nbsp;
    <a href="http://localhost:8080" style="color:#2b6cb0">Airflow</a>
</div>

</div>

<!-- FOOTER -->
<div style="background:#718096;color:white;padding:12px 20px;text-align:center;
            font-size:.8em;border-radius:0 0 10px 10px">
    Yılmaz Makine Ltd. &nbsp;|&nbsp; Otomatik Raporlama Sistemi &nbsp;|&nbsp;
    Bu e-posta {date.today().strftime('%d.%m.%Y')} tarihinde otomatik oluşturulmuştur.
</div>

</td></tr></table>
</body></html>"""


def send_email(html: str, dry_run: bool = False) -> bool:
    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", 587))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")
    to_email  = os.environ.get("REPORT_EMAIL", smtp_user)

    bugun = date.today().strftime("%d.%m.%Y")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[Yılmaz Makine] Sabah Raporu — {bugun}"
    msg["From"]    = smtp_user or "noreply@yilmazmakine.com.tr"
    msg["To"]      = to_email or "yonetici@yilmazmakine.com.tr"
    msg.attach(MIMEText(html, "html", "utf-8"))

    if dry_run:
        out = Path(__file__).parent.parent / "data" / f"rapor_{bugun}.html"
        out.parent.mkdir(exist_ok=True)
        out.write_text(html, encoding="utf-8")
        print(f"[DRY-RUN] HTML rapor kaydedildi: {out}")
        return True

    if not smtp_user or not smtp_pass:
        print("UYARI: SMTP_USER / SMTP_PASS eksik. Lütfen .env dosyasını ayarlayın.")
        print("       .env örneği: scripts/.env.example")
        return False

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
            server.ehlo()
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, to_email, msg.as_string())
        print(f"E-posta gönderildi → {to_email}")
        return True
    except Exception as e:
        print(f"E-posta HATASI: {e}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(description="KOBİ Sabah E-posta Raporu")
    parser.add_argument("--dry-run", action="store_true",
                        help="E-posta göndermez, HTML dosyaya kaydeder")
    args = parser.parse_args()

    print(f"[{date.today()}] Veri çekiliyor...")
    try:
        nakit, satis, alacak, riskli, stok, yaklasan = fetch_data()
    except Exception as e:
        print(f"VERİTABANI HATASI: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"  Gecikmiş: {alacak['gecikis_adedi']} fatura / {tl(alacak['toplam_gecikis'])}")
    print(f"  Kritik stok: {len(stok)} kalem")

    html = build_html(nakit, satis, alacak, riskli, stok, yaklasan)
    success = send_email(html, dry_run=args.dry_run)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
