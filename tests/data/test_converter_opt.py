
import pytest
import numpy as np
import pandas as pd
from freqtrade.data.converter.converter import reduce_dataframe_footprint

def test_reduce_dataframe_footprint_optimization():
    # Case 1: Dataframe needs optimization
    df = pd.DataFrame({
        'float_col': np.array([1.1, 2.2, 3.3], dtype=np.float64),
        'int_col': np.array([1, 2, 3], dtype=np.int64),
        'open': np.array([10.0, 11.0, 12.0], dtype=np.float64),  # Should be ignored
    })

    # Original object ID
    original_id = id(df)

    # Run optimization
    df_opt = reduce_dataframe_footprint(df)

    # Check types changed
    assert df_opt['float_col'].dtype == np.float32
    assert df_opt['int_col'].dtype == np.int32
    # Check ignored column unchanged
    assert df_opt['open'].dtype == np.float64

    # Check values preserved (within float32 precision)
    np.testing.assert_allclose(df['float_col'], df_opt['float_col'], rtol=1e-6)
    np.testing.assert_array_equal(df['int_col'], df_opt['int_col'])

    # Verify it's a new object (because astype was called)
    # Note: In current implementation (unoptimized), this is always true.
    # In optimized implementation, this is also true because changes were needed.
    assert id(df_opt) != original_id

def test_reduce_dataframe_footprint_no_change_needed():
    # Case 2: Dataframe already optimized
    df = pd.DataFrame({
        'float_col': np.array([1.1, 2.2, 3.3], dtype=np.float32),
        'int_col': np.array([1, 2, 3], dtype=np.int32),
        'open': np.array([10.0, 11.0, 12.0], dtype=np.float64),
    })

    # Original object ID
    original_id = id(df)

    # Run optimization
    df_opt = reduce_dataframe_footprint(df)

    # Check types remain same
    assert df_opt['float_col'].dtype == np.float32
    assert df_opt['int_col'].dtype == np.int32
    assert df_opt['open'].dtype == np.float64

    # Verify it is the SAME object (optimization goal)
    # This assertion will FAIL until the optimization is implemented
    assert id(df_opt) == original_id
