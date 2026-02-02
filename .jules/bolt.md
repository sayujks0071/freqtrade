## 2025-02-23 - Pandas DataFrame Redundancy
**Learning:** Duplicate assignments in Pandas (`df.loc[mask] = val`) trigger full mask re-calculation, which is expensive on large DataFrames.
**Action:** Always verify if a boolean mask is used multiple times and assign it to a variable or ensure logic is not duplicated.
