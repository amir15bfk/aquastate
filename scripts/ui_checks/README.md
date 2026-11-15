# UI checks

Browser-driven checks used for the November 2026 redesign (see `UI_IMPROVEMENTS_REPORT.md`).
They drive the installed Microsoft Edge through Playwright against a running dev server on
`http://127.0.0.1:8010`. Playwright is a test-only tool and is not part of `requirements.txt`.

```bash
pip install playwright
python scripts/ui_checks/interact.py out/ui map overview search game pilot   # 54 interaction checks
python scripts/ui_checks/states.py out/states                                 # error/empty states + tablet
python scripts/ui_checks/shoot.py out/shots                                   # full-page screenshots, console errors, overflow
```

Each script prints `PASS` / `FAIL` lines and writes screenshots to the folder given as the first argument.
