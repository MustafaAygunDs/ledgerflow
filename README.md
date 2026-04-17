LedgerFlow — Automated SMB Business Intelligence System

Automated nightly BI reporting system for Turkish SMEs with accounting software integration and morning email delivery.

Demo Scenario: Yılmaz Makine Ltd. — Istanbul-based machinery manufacturing and sales company

Features

Nightly automated ETL (Airflow): Updates overdue invoices and calculates KPIs
7:00 AM email report: Cash position, receivables tracking, and stock alerts in HTML format
4 Metabase Dashboards: Cash Position, Sales Summary, Receivables Tracking, Executive Summary
Realistic demo data: 18 months of seasonal sales fluctuation, 208 overdue receivables, 8 critical stock items
Docker Compose: Single command to spin up the entire stack


Architecture
┌─────────────────────────────────────────────────────────────────┐
│                          Docker Network                         │
│                                                                 │
│  ┌─────────────────┐   reads/writes   ┌──────────────────────┐  │
│  │                 │◄────────────────►│       Airflow        │  │
│  │   PostgreSQL    │                  │        :8080         │──┼──► Email Reports
│  │     :5433       │◄────────reads────│   Nightly ETL        │  │
│  │                 │                  │     02:00 UTC+3      │  │
│  │   kobi_db       │                  └──────────────────────┘  │
│  │   airflow_db    │                                            │
│  │   metabase_db   │◄────────reads────┌──────────────────────┐  │
│  │                 │                  │      Metabase        │  │
│  └─────────────────┘                  │        :3000         │  │
│                                       │    4 Dashboards      │  │
│                                       └──────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
Data flow:

Airflow reads from kobi_db, updates overdue statuses, and writes KPI snapshots back
Metabase reads from kobi_db to render live dashboards
Airflow sends HTML email reports via SMTP

Database Schema
customers (15 records)
    ├── invoices (632 records, 38.7M TRY)
    │       └── payments (406 payments, 23.6M TRY collected)
    └── (views: overdue_receivables, critical_stock)

inventory (48 items)

Quick Start
Prerequisites

Docker & Docker Compose
Python 3.10+ (for seed and setup scripts)
pip install faker psycopg2-binary requests

Setup
bash# 1. Clone the repository
git clone https://github.com/MustafaAygunDs/ledgerflow.git
cd ledgerflow

# 2. Configure email settings (optional)
cp .env.example .env
# Edit .env with your SMTP credentials

# 3. Start all services
docker compose up -d

# 4. Create the database schema
docker cp scripts/01_schema.sql kobi-postgres:/tmp/
docker exec kobi-postgres psql -U kobi -d kobi_db -f /tmp/01_schema.sql

# 5. Load demo data
python3 scripts/02_seed_data.py

# 6. Configure Metabase (includes dashboard setup)
python3 scripts/03_metabase_setup.py

# 7. Run an email report test (no SMTP required)
python3 scripts/04_sabah_email.py --dry-run

Services
ServiceURLUsernamePasswordMetabasehttp://localhost:3000admin@yilmazmakine.com.trKobiRapor2024!Airflowhttp://localhost:8080adminadmin123PostgreSQLlocalhost:5433kobikobi123

Dashboards
Cash Position

Collected, pending, and overdue receivables scalar KPIs
Monthly collection trend (line chart)
Invoice status distribution (pie chart)

Sales Summary

18-month sales bar chart (seasonal fluctuation visible)
Top 10 customers ranking
Sales distribution by industry sector
Average invoice value trend

Receivables Tracking

Aging analysis: 1–30 / 31–60 / 61–90 / 91–180 / 180+ days
High-risk customers table
Overdue invoice list (top 50)

Executive Summary

Current month sales / collections / critical stock KPIs
Sales vs. Collections comparison chart
Critical stock list (items requiring reorder)
Payment method distribution


Airflow DAG — kobi_gece_rapor
Schedule: Nightly at 02:00 (Turkey time, UTC+3)
db_health_check
      │
update_overdue_status
      │
      ├── calculate_cash_position
      ├── calculate_sales_summary
      ├── track_receivables
      └── check_stock_alerts
                │
          send_email_report
TaskDescriptiondb_health_checkVerify database connectivityupdate_overdue_statusMark pending + past-due invoices as overduecalculate_cash_positionCash KPIs for the last 30 dayscalculate_sales_summarySales summary and top 5 customerstrack_receivablesOverdue receivables aging analysischeck_stock_alertsDetect items below minimum stock thresholdsend_email_reportCompile and send HTML email report

Email Report
Gmail setup:
bash# Add to .env:
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your@gmail.com
SMTP_PASS=app-password    # Gmail > Account > Security > App Passwords
REPORT_EMAIL=manager@company.com
Automated via cron (for server deployment):
bash# crontab -e
0 4 * * * cd /path/to/ledgerflow && python3 scripts/04_sabah_email.py >> /var/log/kobi_email.log 2>&1

Demo Data — Yılmaz Makine Ltd.
MetricValueCustomers15 companies (Ankara, Bursa, İzmir, Konya, etc.)Total Invoices632 invoices / 38.7 million TRYAmount Collected23.6 million TRYOverdue Receivables208 invoices / 9.6 million TRYMaximum Overdue518 daysInventory Items48 (machine parts, raw materials, consumables)Critical Stock8 items (cylinder, motor, PLC, laser nozzle)
Seasonal fluctuation: Spring (Feb–May) +15–40% | Summer −10–30% | Autumn +10–30%

Project Structure
ledgerflow/
├── docker-compose.yml          # All services
├── .env.example                # Environment variable template
├── dags/
│   └── kobi_gece_rapor.py      # Airflow ETL + email DAG
├── scripts/
│   ├── 01_schema.sql           # Database schema (tables + views)
│   ├── 02_seed_data.py         # Turkish SME demo data via Faker
│   ├── 03_metabase_setup.py    # Metabase dashboard provisioning
│   ├── 04_sabah_email.py       # Standalone morning report script
│   └── init_dbs.sh             # Docker init: metabase_db + airflow_db
└── data/                       # Dry-run HTML report output

Tech Stack
LayerTechnologyDatabasePostgreSQL 15Data VisualizationMetabase (Open Source)OrchestrationApache Airflow 2.9Data GenerationPython 3 + FakerEmail DeliveryPython smtplib (SMTP/TLS)ContainerizationDocker + Docker Compose

Real-World Integration
This system can be extended to connect directly to Turkish accounting software:

Logo Tiger / Go: Direct connection to MSSQL database
Mikro: Native PostgreSQL or MSSQL database
Paraşüt / e-Logo: REST API integration
Zirve: DBF/SQL export ingestion

Replace scripts/02_seed_data.py with the target software's database connection — the rest of the pipeline runs unchanged.

License
MIT

Mustafa Aygün — Data Engineer
