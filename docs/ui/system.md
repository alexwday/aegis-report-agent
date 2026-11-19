# Design system

## Tokens and type

| Role | Reference value | Application |
|---|---|---|
| Ink / supporting text | `#182b27` / `#49615a` | Headings, body, labels and secondary text |
| Accent / hover | `#07564b` / `#063e37` | Primary actions, evidence links, proposal border |
| Page / cards / tint | `#f6f8f5` / `#ffffff` / `#e8f2ed` | Page, document cards, context and selected items |
| Navigation | `#112b27` with `#e2efe7` | Persistent left rail, with lighter filled current item |
| Warning / danger | `#674515` on `#fbf0d9` / `#852e2a` on `#fdf0ee` | Pending data and provisional output / failure and destructive actions |
| Focus | `#137b72` | 3 px outline with 3 px offset on light controls |
| Spacing | 4, 8, 12, 16, 20, 24 and 32 px | 8–12 px between related controls, 16 px between panels |
| Radius and elevation | 9, 14, 17 px and two shadows | Controls, cards and hero; stronger elevation for overlays |
| Type | System sans at 13, 14 and 16 px, Georgia display at 28–58 px | Status and metadata, forms and tables, body, and page or canvas titles |
| Motion | 150 ms | Button fill and border changes; reduced-motion preference disables transitions |

Map these semantic roles to Functions Assist theme variables. Preserve readable text and visible focus when replacing colours. The checked-in token file defines the reference palette and responsive heading sizes. [Tokens](../../ui/reference/tokens.css)

## Component inventory

| Component | Anatomy and variants | Interaction |
|---|---|---|
| Application shell | Nav rail, breadcrumb, global notices, main landmark | Brand returns to Reports. Active navigation has `aria-current`. The skip link targets main. |
| Buttons and links | Primary, secondary, quiet, small, danger and disabled | Use a button for actions and a link for navigation. Focus, hover and disabled styles are visible. |
| Template card | Section preview, description and Use template | Opens a named modal with editable report title and starting bank. |
| Report row | Title, saved version, refresh state, waiting bank and menu | Open creates a draft from the head. More exposes rename, duplicate, make a template and archive or restore. |
| Chat and proposal | Conversation log, progress region, compose form, suggested messages and change list | Stream milestones, allow cancel and reconnect, then show a proposal with Accept, Reject and Edit. Highlight all affected existing sections. Confirm removal separately. |
| Section card | Title, bank and source chips, time, mode, format, status and output | Settings, optional gather, up and down, duplicate and remove. Apply settings stages an edit in the draft. The last section stays required. |
| Report output | Cited figures, trends, cited highlights, notes, comparison facts and peer tables | Every data row and supported claim opens evidence. A table mirrors the visible chart data. Ranking uses metric direction where known. Missing and currency uncertainty have text labels. |
| Saved comparison | Summary and paired Saved/Preview blocks | Label additions, removals, moves and modifications with icon plus text. Show changed peer values by bank and report-setting changes in a disclosure. |
| Context drawer | Naming header and close affordance, then forms or detail | At widths above 1250 px use a third column. At tablet widths overlay the canvas column. At narrow widths use a bottom panel. Move focus to its heading and restore focus to the opening control on Escape or Close panel. |
| Dialog | Title, context, fields, action and Cancel | Use native focus containment. Required fields and API feedback stay visible. Destructive confirmation uses a danger button with an explicit verb. |
| Schedule card and timeline | Pinned version, next fiscal target and period rows with missing scopes and output | Initial configuration, pause, provisional policy, refresh and check-now. Distinguish next check, publication and superseded history. |
| Feedback | Waiting, loading, partial, empty, stale, expired, limit and error | Use a polite status for work and completion. Use an alert for failures. Provide reload, reconnect or retry where supported. |

## Accessibility checks

- Keyboard paths cover the skip link, nav, native form controls, section reorder buttons, evidence and Escape to close a drawer or dialog. Tab into a horizontally scrollable figure table to reach the evidence buttons and pan where needed.
- Display status words and explicit change markers with color. Use region labels on the report canvas and tables and separate headings for each drawer. Preserve source table headers when mirroring the chart.
- Announce streamed progress and API feedback through live regions. The reference receives progress events and the final assistant message, with reconnection by event cursor.
- Test 1440 px and 1024 px app widths and 390 px for overflow and drawer focus. Full assistive-technology and production-theme contrast testing belongs with the embedding team. [Browser smoke](../../scripts/reference_smoke.cjs)
