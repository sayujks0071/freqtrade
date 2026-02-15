        # Check for current hour - but allow it to be missing if we are at the very beginning
        # of the hour and the exchange didn't return it yet.
        if not mark_candles[mark_candles["date"] == this_hour].empty:
            assert mark_candles[mark_candles["date"] == this_hour].iloc[0]["open"] != 0.0
