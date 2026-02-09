## 2025-02-23 - [Pandas dtype optimization]
**Learning:** `df.astype()` creates a full copy of the DataFrame even if the dtypes are identical to the current ones. Checking for necessary changes first and skipping the call if `new_dtypes` is empty avoids this overhead entirely.
**Action:** Always check if a pandas operation is actually necessary before calling it, especially for large DataFrames in hot paths like data loading or backtesting.
