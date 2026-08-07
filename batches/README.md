# Batches — 7 August 2026

Chronological QuickStatements batches from the data-integrity fix session.
See `../../SESSION_2026-08-07.md` for the full narrative.

| File | Purpose | Result |
|---|---|---|
| batch1_fix_p5.qs | Link items to collection (P5) | 98/150 ok |
| batch2b_fix_dates_CORRECTED.qs | Date fixes, quoting attempt 1 | partial |
| batch2c_fix_dates_FINAL.qs | Date fixes, quoting attempt 2 | 33/57 ok |
| batch2d_add_labels.qs | Add labels to then-missing items | failed — hung on ghost Q-IDs |
| batch2f_create_missing_FIXED.qs | Recreate 23 missing items | 17/23 ok first pass |
| batch2g_fix_greek_labels.qs | Add Greek labels to recreated items | 23/23 labels ok |
| batch2h_v3_correct_syntax.qs | Remove statements from 17 duplicates | 94/111 lines ok |
| batch3a_backfill_identifiers.qs | **Backfill new P14 identifier on all 150 planned items — diagnostic** | 125/150 ok, 25 errors = definitive missing list |
| batch3b_fix_creator_swap.qs | Fix creator/description column-swap bug | ok |
| batch3c_fix_labels.qs | Fix backslash-corrupted labels | 46/46 ok |
| batch4_create_final25.qs | Recreate the 25 confirmed-missing items | 16/24 ok first pass (1 skipped: no title) |
| batch5_final_9items.qs | Retry remaining 8 + the no-title item | 1/9 ok (label=description collision) |
| batch6_final_8items_nodesc.qs | Retry 8, description omitted | 8/8 ok |
| batch7_clean_orphans.qs | Remove P1 from 8 pre-existing ghost duplicates (from 3 Aug import) | 8/8 ok |

**End state:** 150/150 unique P14 identifiers confirmed via SPARQL.
