# Walk the reference app

## Launch

Install `uv`, PostgreSQL server tools and pgvector 0.8.x. `pg_config --bindir` should point to the PostgreSQL install with pgvector. Start the disposable fixture app and worker. The short quiet period lets the scheduler demonstrate publication in seconds.

```sh
QUIET_SECONDS=1 ./scripts/dev --reference
```

Open [the reference app](http://127.0.0.1:8000/). The demo starts at FY2090 Q2 with three fabricated banks. Ctrl-C removes the fixture database. The installed app and seed run without network access after the runtime and dependencies have been installed. If local `uv` caches are populated, start with `UV_OFFLINE=1 QUIET_SECONDS=1 ./scripts/dev --reference` to enforce offline dependency resolution. [Runtime configuration](../../README.md#runtime-configuration)

For approved read-only source access, set `AEGIS_READONLY_SOURCE_DATABASE_URL` in the local shell before launching `./scripts/dev --reference`. Use a SELECT-only account. The app labels the source connection and continues to write drafts, reports and schedule history to its disposable reporting database. The reference launcher always uses the local assistant stub and report state disappears when the launcher exits. The reviewer can use the separate real-model evaluators with authorized credentials. [Evaluation configuration](../integration/evaluation.md)

## Five tasks

1. **Build from a template.** In Reports or Templates, choose **Use template** on Quarterly earnings. Name the report `Quarterly earnings brief`, leave Fixture Bank One selected and choose **Create draft**. The canvas has a Net income section. Select **Preview report** and look for 435 millions in FY2090 Q2. Choose **Save report**, optionally add `Initial earnings review` and save version 1. [Template setup](screenshots/desktop-template-start.png), [first preview](screenshots/tablet-workspace-preview.png)
2. **Describe a report.** Open Reports. Select **Try an example** or enter `Build a report comparing Net Income for SYN1-CA and SYN2-CA over the last four quarters` and choose **Start with chat**. Aegis proposes a bank and time scope change and highlights the affected section. Choose **Accept**, then **Preview report**. The section shows both banks, four fiscal quarters, cited rows and a trend. [Proposal](screenshots/desktop-chat-proposal.png)
3. **Adjust a section and review changes.** Open the saved earnings report from task 1. Choose **Edit section**, select Fixture Bank Two, choose **Last quarters** and enter `4`. Choose **Apply section settings**, then **Preview changes**. Scan the Saved and Preview columns. Open the FY2090 Q2 peer comparison. Save version 2 with an optional note, open **Version history** and select **What changed**. [Section settings](screenshots/tablet-section-settings.png), [comparison](screenshots/desktop-comparison.png), [version changes](screenshots/tablet-version-changes.png)
4. **Check a figure.** On either preview, select **View evidence** beside Fixture Bank One’s FY2090 Q2 value. Check the source, fiscal period, page or sheet and the excerpt. The data status reports the latest stability check. Escape closes the drawer and returns focus to the citation. [Source evidence](screenshots/desktop-evidence.png)
5. **Schedule a quarterly refresh.** Open the report from task 3. Choose **Schedule refresh**, leave automatic refresh selected, choose version 2 and FY2090 Q2. Choose **Allow a provisional report** and use `0.001` hours for this fixture exercise. Save and open **Schedules and status**. Select **Refresh status** until FY2090 Q2 is published and FY2090 Q3 shows a pending bank. Expand **Pending banks and sources** to see Fixture Bank Two’s Net Income observation. Expand **Download output** on the complete quarter for HTML, PDF or JSON. The schedule can publish Q3 provisionally after its deadline and retain Q3 until the missing data arrives. [Schedule settings](screenshots/desktop-schedule-settings.png), [timeline](screenshots/tablet-schedules.png)

The five tasks take about seven minutes on the fixture. The chat example is deterministic. Enter supported edits using the suggested messages, or use section settings for an exact configuration.

## Regenerate and test

In a second terminal with Node 22 or newer, install the pinned browser test dependency and its Chromium build once. These downloads are for browser tests. The app has no JavaScript package dependency.

```sh
npm install --prefix /tmp/aegis-browser playwright@1.62.1
/tmp/aegis-browser/node_modules/.bin/playwright install chromium
PLAYWRIGHT_MODULE=/tmp/aegis-browser/node_modules/playwright node scripts/reference_smoke.cjs --screenshots
```

Omit `--screenshots` for smoke checks only. Set `AEGIS_UI_URL=http://127.0.0.1:8151` when using a custom `AEGIS_DEV_PORT`. Set `CHROMIUM_PATH` to a compatible installed Chrome or Chromium executable to reuse it. Run on a fresh disposable fixture for the empty home and deterministic screenshot set. The script uses two seeded fixture identities for 1440 × 1000 and 1024 × 900. It archives its named smoke report from an earlier run if one exists and checks the 390 × 844 layout with the default fixture identity. It checks same-origin requests, keyboard focus and the five task outcomes. Expired session, conflict, limit and service errors are simulated at the browser boundary and the loading capture deliberately delays a real call. [Browser harness](../../scripts/reference_smoke.cjs)
