import numpy as np

from freqtrade.data.converter import reduce_dataframe_footprint
from tests.conftest import generate_test_data


def test_reduce_dataframe_footprint_idempotency():
    data = generate_test_data("15m", 40)

    # Add some columns to convert
    data["open_copy"] = data["open"]
    data["close_copy"] = data["close"]

    # First pass: should convert
    df1 = reduce_dataframe_footprint(data)

    assert df1["open_copy"].dtype == np.float32
    assert df1["close_copy"].dtype == np.float32

    # Second pass: should be no-op and return same object
    df2 = reduce_dataframe_footprint(df1)

    assert df2["open_copy"].dtype == np.float32
    assert df2 is df1, "Should return the same dataframe object if no changes are needed"
