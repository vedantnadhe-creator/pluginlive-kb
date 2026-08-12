# Download / Export Rage-Click Guard (August 2026)

Every "Download Report" / "Export" trigger in the three assessment frontends fired its
request on **every** click. Rage-clicking a report button queued N identical
`generatePDFReport` / Excel-export calls — N PDFs generated server-side, N blobs
downloaded, N files dropped in the user's downloads folder.

There was **no shared download button** in any repo: each screen re-implemented its own
trigger (plain antd `Button`, the custom `Button.Primary` wrapper, a styled `div` with an
icon, or `ViewReportButton`). Only a handful of sites had an ad-hoc `useState` loading flag.

**Live on DEV + UAT (2026-08-12). PROD pending.**

## The shared primitive

The three frontends are separate webpack bundles with no shared npm package, so the
primitive is duplicated **identically** in each repo:

| File | Role |
|------|------|
| `src/hooks/useDownloadGuard.js` | The ~20-line core. `useDownloadGuard(handler, { disabled })` → `{ loading, disabled, onClick }` |
| `src/components/DownloadButton/index.js` | An antd `<Button>` pre-wired to the hook |

The hook holds an `inFlight` ref latch plus a `loading` state. While the click's async
handler is in flight, `onClick` returns immediately (the request cannot re-fire) and
`loading`/`disabled` are true. A `mounted` ref prevents a `setState` on an unmounted
component when the user navigates away mid-download.

Two shapes, because the trigger elements are heterogeneous:

- **Plain antd `<Button>`** → swap the tag for `<DownloadButton>`. Same props, same look.
- **Custom `Button.Primary` / styled `div` / `ViewReportButton`** → call the hook directly
  and wire `loading` / `disabled` / `onClick`. The element is **not** swapped, so nothing
  is restyled.

### The one hard requirement

The guard can only block the second click if the click handler **returns the promise that
settles when the download finishes**:

```js
// correct — guard holds until the export completes
const handleExport = () => dispatch(exportStudentData(assessmentId))

// broken — returns undefined, guard releases on the next microtask
const handleExport = () => { dispatch(exportStudentData(assessmentId)) }
```

Every migrated handler returns its promise, and the underlying export thunks in
`modules/Assessment/actions.js` are all `async` and `await` their axios chain. A handler
that swallows its promise silently reverts that button to rage-clickable — the button
still *looks* guarded (it flashes a spinner) but fires N requests.

### Import resolution gotcha

`config/webpack.base.js` in all three repos aliases only `modules`, `components`, `theme`
(plus `fonts`/`utils` in some). There is **no `hooks` alias** — the bare
`import ... from 'hooks/useDownloadGuard'` resolves via **`babel-plugin-module-resolver`**
with `root: ["./src"]` in `.babelrc`, the same mechanism the existing `utils/...` imports
use. Do not "fix" a bare src-root import to a relative path assuming it is broken; check
`.babelrc` first. (Assessment-React uses relative paths for these two imports; the other
two use the bare form. Both resolve.)

## Guarded sites

**admin-react** (`cdeff1df`)
- `Partials/StudentsTable/index.js` — Export
- `Partials/ActiveCollegeList/CandidateList/index.js` — Export
- `Partials/ActiveCollegeList/DiagnosisList/index.js` — Export
- `Partials/ActiveCollegeList/UnifiedAssessmentTable/index.js` — per-row schedule Export (each row owns its own guard instance)
- `modules/CandidateMetricDetails/CandidateMetricMain.js` — the async-job "Download file" button (previously only *hidden* after click, never disabled)
- `components/Uploader/FileReaderVisible.js` — the icon download; its `XMLHttpRequest` is now wrapped in a Promise that resolves on **both** `onload` and `onerror`, so the guard always releases

**institute-react** (`4de0d1e1` + the earlier CandidateList commit)
- `Partials/CandidateList/index.js` — Export
- `Partials/DiagnosisList/index.js` — Export
- `Partials/StudentsTable/index.js` — Export
- `modules/Reports/Partials/CommonData/ExportPopup.js` — Export (hook form; the existing `Spin` overlay and the empty-selection `disabled` are preserved, the latter merged into the guard)

**Assessment-React** (`1e10e88`)
- `components/ViewReportButton.js` — now **self-guards**. It previously took `loading` + `loadingId` + `id` props and compared `loadingId === id` so the parent could disable one row at a time; `AssessmentContainer/index.js` owned `pdfLoading`/`pdfLoadingId` state for this. All of that plumbing is deleted — each rendered instance owns its own in-flight state, and `handleViewReport` just returns `dispatch(generatePDFReport(id))`.
- `modules/Events/Preview/Partials/EventPreviewContent/index.js` — the document-download `div`. Each document renders through a `DocumentDownloadItem` component so every item gets its own hook (calling the hook inside the parent's `.map` would violate rules-of-hooks).

## Deliberately not guarded

- **Client-side-only exports** — `MetaDashboard/AssessmentTab.js`'s inline `exportXlsx` buttons (`file-saver`, synchronous) and `ResumeDownload.js` (`@react-pdf/renderer` `PDFDownloadLink`, already disabled while rendering). No request to double-fire.
- **Static `<a href=... download>`** links (CV links, bulk-upload templates).
- **Already-guarded by their own local state** — `StudentReport/index.js` (`downloadingReport`) and `TpoStudentListTable.js` (`exporting`) in both admin-react and institute-react. These bind a `useState` flag to antd's `loading` prop, which blocks clicks on its own.

## Known rough edge

In `UnifiedAssessmentTable` the `DownloadButton` sits inside an antd `Tooltip` and is a
plain function component without `forwardRef`. antd v4 falls back to `findDOMNode`, so the
tooltip still positions correctly, but this can emit a ref warning under StrictMode.
Adding `forwardRef` to `DownloadButton` is the clean fix if that warning becomes noise.

## Dead code found along the way

`Aptitude.js` and `Communication.js` (Assessment-React PlacementPrep) pass an
`onDownloadReport` handler into `ScoreDrawer`, but `score-drawer.js` never destructures or
uses the prop — there is no rendered download button behind it. The handlers are marked
with a `ponytail:` comment rather than wiring up new UI.

See `admin-frontend.md`, `institute.md`.
