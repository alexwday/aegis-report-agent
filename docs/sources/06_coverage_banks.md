# COVERAGE MATRIX AND BANK UNIVERSE

PAGE 6 / 16 24.0px

## WHAT AEGIS_DATA_AVAILABILITY SAYS IS LOADED (AS OF 2026-11-17, DEV)

| database_names value | Banks | First | Last | Banks flagged (symbols) |
|---|---|---|---|---|
| transcripts | 34 | 2026 Q3 | 2027 Q2 | AB-US AMP-US BBVA-ES BCS-US BMO-CA BNP-FR BNS-CA CM-CA DBK-DE EVR-US FHI-US FLG-US GLE-FR HBAN-US HLI-US HSBA-GB IFC-CA ING-US ISP-IT IVZ-US LAZ-US NA-CA NTRS-US PIPR-US PJT-US RJF-US RY-CA SAN-ES SF-US STAN-GB TD-CA TROW-US UBS-US WBC-AU |
| investor_relations_benchmarking | 14 | 2026 Q1 | 2026 Q1 | BAC-US BMO-CA BNS-CA CM-CA C-US GS-US JEF-US JPM-US MS-US NA-CA RBC-US RY-CA TD-CA WFC-US |
| reports | 13 | 2019 Q2 | 2026 Q3 | BAC-US BMO-CA BNS-CA CM-CA C-US GS-US JPM-US LB-CA MS-US NA-CA RY-CA TD-CA WFC-US |
| supplementary | 13 | 2019 Q1 | 2026 Q3 | BAC-US BMO-CA BNS-CA CM-CA C-US GS-US JEF-US JPM-US MS-US NA-CA RY-CA TD-CA WFC-US |
| rts | 6 | 2020 Q1 | 2026 Q3 | BMO-CA BNS-CA CM-CA NA-CA RY-CA TD-CA |
| investor_presentation | 6 | 2025 Q4 | 2026 Q3 | BMO-CA BNS-CA CM-CA NA-CA RY-CA TD-CA |
| supplementary_financials | 6 | 2026 Q2 | 2026 Q3 | BMO-CA BNS-CA CM-CA NA-CA RY-CA TD-CA |
| pillar3 | 6 | 2020 Q1 | 2026 Q3 | BMO-CA BNS-CA CM-CA NA-CA RY-CA TD-CA |
| event_transcripts | 3 | 2025 Q2 | 2025 Q2 | JPM-US MS-US WFC-US |

**NOTE:** Availability is a HINT, not truth. Measured gaps: (1) investor_relations_benchmarking is flagged only for FY2026 Q1, yet benchmarking_report holds FY2019 to FY2026 Q3. (2) supplementary_financials is flagged only for FY2026 Q2-Q3, yet the table holds FY2025 Q4 onward. (3) supplementary and reports list 13 banks including US banks, but there are no supplementary vector tables for US banks. (4) transcripts flags FY2026 Q3 onward, but the Q1-Q2 2026 Canadian calls are in the unified twin table (page 13). So: use availability to decide what to OFFER the user, but verify against the source table itself before generating.

## SOURCE-BY-BANK REALITY (WHAT THE SOURCE TABLES REALLY CONTAIN)

| Source table | Banks in table | Periods in table |
|---|---|---|
| benchmarking_report | 14 listed banks + RBC-US + 3 aggregates (page 10) | FY2019 (partial) to FY2026 Q3; rectangular from FY2020 Q1 |
| investor slides | 6 core Canadian banks | FY2025 Q4 to FY2026 Q3 |
| financial-supp | 6 core Canadian banks (12 bank spellings) | FY2025 Q4 to FY2026 Q3 |
| aegis_transcripts | 34 institutions; core six only for FY2026 Q3 | FY2026 Q3 (31), Q4 (2), FY2027 Q2 (1) |
| aegis_event_transcripts | JPM-US, MS-US, WFC-US | FY2025 Q2 only |
| pillar3_embedding | 6 core Canadian banks | FY2020 Q1 to FY2026 Q3 (159 of 162) |
| rts_embedding | 6 core Canadian banks | FY2020 to FY2026 Q3 |

## BANK UNIVERSE: 85 INSTITUTIONS IN AVAILABILITY (ID SYMBOL NAME)

| ID | Symbol | Name |
|---|---|---|
| 1 | RY-CA | Royal Bank of Canada |
| 2 | BMO-CA | Bank of Montreal |
| 3 | CM-CA | Canadian Imperial Bank of Commerce |
| 4 | NA-CA | National Bank of Canada |
| 5 | BNS-CA | Bank of Nova Scotia |
| 6 | TD-CA | Toronto-Dominion Bank |
| 7 | LB-CA | Laurentian Bank |
| 8 | JPM-US | JPMorgan Chase & Co. |
| 9 | BAC-US | Bank of America Corporation |
| 10 | WFC-US | Wells Fargo & Company |
| 11 | C-US | Citigroup Inc. |
| 12 | MS-US | Morgan Stanley |
| 13 | GS-US | Goldman Sachs Group Inc. |
| 14 | JEF-US | Jefferies Financial Group Inc. |
| 15 | UBS-US | UBS Group AG |
| 16 | BCS-US | Barclays PLC |
| 17 | DBK-DE | Deutsche Bank AG |
| 18 | GLE-FR | Societe Generale |
| 19 | BNP-FR | BNP Paribas |
| 20 | BBVA-ES | Banco Bilbao Vizcaya Argentaria S.A. |
| 21 | SAN-ES | Banco Santander S.A. |
| 22 | HSBA-GB | HSBC Holdings plc |
| 23 | LLOY-GB | Lloyds Banking Group plc |
| 24 | ING-US | ING Groep N.V. |
| 25 | STAN-GB | Standard Chartered PLC |
| 27 | UCG-IT | UniCredit S.p.A. |
| 28 | ISP-IT | Intesa Sanpaolo |
| 29 | LAZ-US | Lazard Ltd |
| 30 | EVR-US | Evercore Inc |
| 31 | HLI-US | Houlihan Lokey Inc |
| 32 | MC-US | Moelis & Company |
| 33 | PIPR-US | Piper Sandler Companies |
| 34 | PJT-US | PJT Partners Inc |
| 35 | SF-US | Stifel Financial Corp |
| 36 | RJF-US | Raymond James Financial Inc |
| 37 | CF-CA | Canaccord Genuity Group Inc |
| 38 | CIX-CA | CI Financial Corp |
| 39 | AGF.B-CA | AGF Management Limited |
| 40 | IGM-CA | IGM Financial Inc. |
| 41 | FSZ-CA | Fiera Capital Corporation |
| 42 | TFC-US | Truist Financial Corporation |
| 43 | USB-US | U.S. Bancorp |
| 44 | PNC-US | PNC Financial Services Group |
| 45 | RF-US | Regions Financial Corporation |
| 46 | FITB-US | Fifth Third Bancorp |
| 47 | MTB-US | M&T Bank Corporation |
| 48 | HBAN-US | Huntington Bancshares Incorporated |
| 49 | KEY-US | KeyCorp |
| 50 | WAL-US | Western Alliance Bancorporation |
| 51 | FLG-US | Flagstar Financial Inc. |
| 52 | ALLY-US | Ally Financial Inc. |
| 53 | FHN-US | First Horizon Corporation |
| 54 | CMA-US | Comerica Incorporated |
| 55 | CFG-US | Citizens Financial Group Inc. |
| 56 | SNV-US | Synovus Financial Corp. |
| 57 | SCHW-US | Charles Schwab Corporation |
| 58 | BLK-US | BlackRock Inc. |
| 59 | BEN-US | Franklin Resources Inc. |
| 60 | IVZ-US | Invesco Ltd. |
| 61 | AMG-US | Affiliated Managers Group Inc. |
| 62 | AMP-US | Ameriprise Financial Inc. |
| 63 | AB-US | AllianceBernstein Holding LP |
| 64 | FHI-US | Federated Hermes Inc. |
| 65 | JHG-US | Janus Henderson Group plc |
| 66 | TROW-US | T. Rowe Price Group Inc. |
| 67 | RAT-GB | Rathbones Group Plc |
| 69 | QLT-GB | Quilter plc |
| 74 | MFC-CA | Manulife Financial Corporation |
| 75 | SLF-CA | Sun Life Financial Inc. |
| 76 | IAG-CA | iA Financial Corporation Inc. |
| 77 | GWO-CA | Great-West Lifeco Inc. |
| 78 | POW-CA | Power Corporation of Canada |
| 79 | IFC-CA | Intact Financial Corporation |
| 80 | EQB-CA | Equitable Group Inc. |
| 81 | FN-CA | First National Financial Corp. |
| 83 | GSY-CA | goeasy Ltd. |
| 84 | WBC-AU | Westpac Banking Corporation |
| 85 | CBA-AU | Commonwealth Bank of Australia |
| 86 | ANZ-AU | ANZ Group Holdings Limited |
| 87 | NAB-AU | National Australia Bank Limited |
| 88 | BOQ-AU | Bank of Queensland Limited |
| 89 | BK-US | Bank of New York Mellon Corporation |
| 90 | STT-US | State Street Corporation |
| 91 | NTRS-US | Northern Trust Corporation |
| 92 | RBC-US | Royal Bank of Canada-US |

Ids 26, 68, 70-73 and 82 do not appear in the latest data. Symbol format is TICKER-CC. Names above are the canonical bank_name values.

=== END OF PAGE 6 OF 16 ===
