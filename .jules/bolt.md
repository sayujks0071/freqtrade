## 2026-02-07 - [Pandas Subset Copy Optimization]
**Learning:** When selecting a small subset of columns from a large DataFrame (e.g. 200+ cols -> 10 cols), `df.reindex(columns=subset)` is ~1000x faster than `df.copy()` and significantly faster (~30x) than `df[subset].copy()`.
**Action:** Always prefer `reindex` or direct slicing when creating a copy of a subset of columns, especially in hot loops. Be aware `reindex` inserts NaNs for missing columns, which can be a feature or a bug depending on context.
