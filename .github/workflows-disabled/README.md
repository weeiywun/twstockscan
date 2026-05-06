# Disabled Workflows

These workflows are intentionally kept outside `.github/workflows` so they do not appear as runnable GitHub Actions.

- `ai_ranking.yml`: legacy Gemini ranking flow; current UI uses `ai_analysis.json` instead.
- `volume_breakout_scan.yml`: paused legacy full-market strategy; high request cost if run accidentally.
- `ema_tangling_scan.yml`: paused legacy full-market strategy; high request cost if run accidentally.
- `price_cache_init.yml`: one-time cache rebuild tool; restore only when intentionally rebuilding `price_cache.parquet`.
- `right_top_scan.yml`: covered by `daily_scan.yml`; standalone runs can create inconsistent data timestamps.
- `volume_signal_scan.yml`: covered by `daily_scan.yml`; standalone runs mutate multiple data files.

To re-enable one, move it back into `.github/workflows/` and review its data request cost before running.
