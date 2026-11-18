# SOURCE: investor_relations_benchmarking -> benchmarking_report + kpi_metadata

PAGE 10 / 16 17.5px

## WHAT IT IS

Structured KPI dataset: quarterly financial metrics by bank and business segment, built from financial supplements (source=SuppPack), EPM data, and calculations. The only structured-number source; no text, no vectors. Loaded as ONE csv snapshot (every row has the same filepath, 2026-10-14): treat as full-refresh.

## BENCHMARKING_REPORT: 91,208 ROWS, 21 COLUMNS

Identity: `bank` vch (short label), `bank_symbol` vch (canonical, NULL for aggregates), `Parameter` vch (metric name, 166 distinct), `Platform` vch (business segment, 48 distinct; Enterprise = whole bank), `ID` vch (series id like ID_153, 914 distinct). Period: `yr_Qtr` vch 'YYYY_Qn' NOT NULL, `fiscal_year` int, `quarter` vch.

Values (all num, nullable): `Actual` (the reported value; NULL on 3,350 rows), `QoQ`, `YoY`, `2Y`, `3Y`, `4Y`, `5Y` = precomputed % change vs prior quarter, year, and 2-5 years back.

Example: RBC Net Income Enterprise 2026_Q3: [Redacted for public repository: reported values.]

Other: `source` vch (Calculated 49k, SuppPack 19k, NULL 20k, Adjustment, EPM, ...), `Units` vch (millions 9k, % 1k, mostly NULL: use kpi_metadata.unit instead), `Report` vch (WM / CM / Yes / NULL: which report uses the row), `BPS` vch ('Yes' on 20,601 rows; likely marks rows whose change is shown in basis points: verify), `updated_at` tstz, `filepath` txt.

## GRAIN, COVERAGE, SHAPE

- Unique on (`bank`, `Parameter`, `Platform`, `yr_Qtr`): zero duplicates found.
- Rectangular: every quarter FY2020 Q1 to FY2026 Q3 has exactly 3,221 rows (FY2019 partial). Missing data = NULL Actual, not a missing row.
- 17 bank values: RBC (RY-CA), BMO, TD, CIBC (CM-CA), BNS, NBC (NA-CA), JPM, WFC, GS, BAC, Citi (C-US), MS, JEF, RBC-US, plus aggregates Big 6, Peer (ex-RY), Peer (ex-RY-US).
- Currency is not stored (Canadian banks CAD; US labels likely USD: verify). Column names are CASE-SENSITIVE and need double quotes: "Parameter", "Platform", "Actual", "2Y".

## KPI_METADATA: 138 ROWS (ONE PER METRIC)

`id` int PK, `kpi_name` txt (joins to benchmarking Parameter), `description` txt, `synonyms` txt[], `platforms` txt[] (segments where the metric exists), `unit` txt (millions 95, % 41, count 2), `higher_is_better` bool, `key_drivers` txt, `analyst_usage` txt.

### A) metric trend for one bank

```sql
SELECT "yr_Qtr", "Actual", "QoQ", "YoY"
FROM benchmarking_report
WHERE bank_symbol='RY-CA' AND "Parameter"='Net Income' AND "Platform"='Enterprise'
ORDER BY fiscal_year, quarter
```

### B) peer ranking, one quarter

```sql
SELECT bank, "Actual" FROM benchmarking_report
WHERE "Parameter"='Efficiency Ratio' AND "Platform"='Enterprise'
  AND "yr_Qtr"='2026_Q3' AND bank_symbol IS NOT NULL
ORDER BY "Actual"
```

### C) find a metric by name or synonym

```sql
SELECT kpi_name, unit, higher_is_better FROM kpi_metadata
WHERE kpi_name ILIKE '%margin%' OR 'Net Interest Margin' = ANY(synonyms)
```

## ALL 166 METRIC NAMES (PARAMETER) WITH UNIT: M=MILLIONS, %=PERCENT, N=COUNT, ?=NOT IN KPI_METADATA

```text
Total Revenue (m)
Average Loans (m)
Non Interest Expenses (m)
Non Interest Income (m)
Pre Provision Pre Tax Contribution (m)
Provisions for Credit Losses (m)
FTE (n)
Net Income (m)
Efficiency Ratio (%)
AUM (m)
Net Income Before Tax (m)
Taxes (m)
AUA (m)
Average Deposits (m)
Average Assets (m)
Provisions for Credit Losses Stage 3 Impaired (m)
Provisions for Credit Losses Stage 1 and 2 Performing (m)
Net Interest Income (TEB) (m)
Common Equity (m)
Net Interest Income (m)
Pre Tax Income (m)
Pre Provision Profit (m)
Return on Equity (%)
Tax Rate (%)
Pre S1 and S2 Provision Profit (m)
Non Interest Income as a perc of Revenue (%)
Pre Tax Margin (%)
Net Revenue (m)
NIM (%)
Pre Tax Contribution (m)
Expense Contribution (m)
Net Income Contribution (m)
Expense Margins (%)
Revenue Contribution (%)
Total Deposits (m)
RWA (m)
NIM (AIEA) (%)
Net Income After Tax (m)
PCL as a perc of Average Loans (?)
Non-interest revenue (?)
Personal Deposits (m)
Business Deposits (m)
Average Interest Earnings Assets (m)
Personal loans to deposits ratio (%)
Total loans to deposits ratio (?)
Branches (n)
Tax Rate (TEB) (%)
Business loans to deposits ratio (%)
Total Assets (m)
ACL (m)
NIAT (?)
Revenue (?)
NII (?)
NIBT (?)
Mutual Fund (Total Bank) (?)
Investment Management (Total Bank) (?)
AUM (Total Bank) (?)
PPPT (?)
Total Investment Banking (m)
Total Revenue (excluded Credit Adjustments) (m)
Global Markets Revenue (m)
Equities (m)
Global Markets Revenue (excluded Credit Adjustments) (m)
FICC (excluded Adjustments) (m)
Total Revenue (excluded Underwriting MTM) (m)
Equities (excluded Adjustments) (m)
FICC (m)
Investment Banking Fees (m)
ECM (m)
ECM and DCM (?)
Advisory (m)
DCM (m)
Underwriting MTM (m)
Return on Equity Adjusted (%)
ACL to GIL (%)
EOP Shares (m)
GIL (m)
Core Cash Diluted EPS (m)
CET1 Ratio (%)
Trading Assets (m)
ACL to Loans (%)
Deposit and payment service charges (m)
Average Assets to Equity (%)
Investment management and custodial fees (m)
Total Loans (m)
Average Credit Cards (m)
PCL (AIEA) (%)
Core Lending NIM (%)
Dividends Declared (m)
Dividends Paid (m)
FX and Commodities (m)
EPS Diluted Adjusted (?)
Ending Share Price (?)
Dividend Declared Payout (m)
Mutual fund revenue (m)
Mortgages to Loans (%)
RWA to total assets (%)
Core Cash Return on Assets (ROA) (%)
Revenue yield (%)
Underwriting & Other Advisory (m)
NIR Yield (%)
Credit Fees (m)
BVPS (m)
Average Residential Mortgages (m)
Average Common Shareholders Equity (m)
CET1 (m)
Risk-Adjusted Revenue Yield (%)
Risk-Adjusted NIM (%)
Card Fees (m)
GIL Ratio (%)
Core Cash Return on RWA (%)
Net Revenue (TEB) (m)
Average Personal Loans (m)
Allocated Capital (m)
PCL on loans ratio (?)
LCR (%)
Credit Cards (m)
Retail Mutual Funds (m)
NIX Ratio (Adjusted Revenue, TEB) (%)
Banking fees (m)
PCL ratio on impaired loans (%)
Residential Mortgages (m)
Foreign exchange gains, other than trading (m)
Average Wholesale and Small Business Loans (m)
Total Retail Loans (m)
Core Net Interest Income (NII) (m)
NSFR (%)
Personal Loans (m)
ER (?)
Wholesale and Small Business Loans (m)
Loans to Assets Ratio (%)
PCL ratio on performing loans (%)
Personal AUM (m)
NIE (?)
Non Interest Expense - Adjustment (?)
TEB Adjustment (m)
Expenses (ex-Variable Compensation and Stock Based Compensation) (m)
Price to BVPS (?)
Transaction Banking and Treasury Services (m)
Lending - Loan Book (m)
Average Loans to Assets (%)
Operating leverage (%)
Institutional AUM (m)
Compensation to NIBTCT Ratio (%)
Credit Adjustments (m)
NIBTCT (m)
Compensation Ratio (%)
Total Compensation (m)
PCL (?)
NIE Adjusted (?)
Rev Repo (m)
GM Total Assets (?)
Non-Interest Expense (?)
Available-for-sale debt securities (?)
Corporate Lending (excluding Gain/(Loss) on Loan Hedges) (?)
Net Gains(losses) on Trading Activities (?)
Derivative Assets (?)
Reverse Repurchase Agreements (?)
Trading debt securities (?)
Gain/(Loss) on Loan Hedges (?)
Securities Services Revenue (m)
Lending and Deposit related fees (m)
Provisions for Credit Losses on Loans (?)
ACL on Loans (?)
Transaction Banking (?)
Treasury Service (?)
```

## ALL 48 SEGMENT NAMES (PLATFORM) FOR THE SIX CANADIAN BANKS

```text
Enterprise
Canadian Banking
U.S. & International Banking
Capital Markets
Canadian Wealth & Insurance
Corporate Support
Wealth Management-WMC+GAM+PB+DI
Wealth Management
Wealth Management-US Segment
Wealth Management-CAD
Wealth Management-US Segment-CAD
Insurance
Wealth Management-CNB - USD
Wealth Management-Ex. CNB
Wealth Management-DI & InvestEase
Wealth Management-Ex. IS
Canadian WM-Ex. HBCA
Wealth Management-GAM-HBCA
Wealth Management-WM USA
Wealth Management-WMC+GAM+DI+PB
Wealth Management-DI & InvestEase-HBCA
Wealth Management-Non US and IS
Wealth Management-Ex. CNB and US Other
Canadian WM
Wealth Management-WM USA - USD
Wealth Management-HBCA
Wealth Management-DI & InvestEase-Ex. HBCA
Wealth Management-GAM-Ex. HBCA
WM Canada-Ex. HBCA
Canadian WM-HBCA
Wealth Management-IS
Wealth Management-WMC+GAM
Wealth Management-Non US
WM Canada-HBCA
Wealth Management-WMC+GAM+DI
Wealth Management-GAM
Wealth Management-CNB
Wealth Management-WMC+GAM+USA+DI+PB
Wealth Management-Ex. HBCA
WM Canada
Personal & Commercial Banking
Private Banking
Personal Banking
Commercial Banking
Wealth Management- Ex CDN CB
Canada
Wealth
Wealth Management-BNS Canada
```

Segment names differ by bank and many are wealth-management variants. Enterprise is the whole-bank total. Not every metric exists for every segment: look up (Parameter, Platform) pairs before asking for them.

=== END OF PAGE 10 OF 16 ===
