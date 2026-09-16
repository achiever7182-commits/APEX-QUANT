import os
import sys
from datetime import date
import pandas as pd

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from data.corporate_actions.models import CorporateAction, CorporateActionType
from data.corporate_actions.adjuster import CorporateActionAdjuster


def test_split_backward_adjustment():
    """
    Test that a 2:1 stock split on 2024-02-01:
    - Leaves prices on or after 2024-02-01 unchanged.
    - Divides prices prior to 2024-02-01 by 2.0.
    - Multiplies volume prior to 2024-02-01 by 2.0.
    - Leaves the original input DataFrame completely unchanged.
    """
    raw_df = pd.DataFrame({
        "timestamp": pd.to_datetime(["2024-01-30", "2024-01-31", "2024-02-01", "2024-02-02"]),
        "open": [2000.0, 2020.0, 1010.0, 1020.0],
        "high": [2050.0, 2060.0, 1030.0, 1040.0],
        "low": [1980.0, 2000.0, 1000.0, 1010.0],
        "close": [2010.0, 2040.0, 1020.0, 1030.0],
        "volume": [100_000.0, 120_000.0, 250_000.0, 240_000.0],
    })
    raw_copy = raw_df.copy()

    split_action = CorporateAction(
        symbol="RELIANCE",
        ex_date=date(2024, 2, 1),
        action_type=CorporateActionType.SPLIT,
        ratio_numerator=2.0,
        ratio_denominator=1.0,
    )

    adjusted = CorporateActionAdjuster.adjust_historical_bars(raw_df, [split_action])

    # 1. Verify raw DataFrame was not mutated
    pd.testing.assert_frame_equal(raw_df, raw_copy)

    # 2. Verify prior bars (2024-01-30, 2024-01-31) have adjusted price / 2
    assert adjusted.loc[0, "adjusted_close"] == 1005.0  # 2010 / 2
    assert adjusted.loc[1, "adjusted_close"] == 1020.0  # 2040 / 2
    assert adjusted.loc[0, "adjusted_volume"] == 200_000.0  # 100_000 * 2

    # 3. Verify post-split bars (2024-02-01, 2024-02-02) have adjusted price equal to raw price
    assert adjusted.loc[2, "adjusted_close"] == 1020.0  # 1020.0 (no adjustment)
    assert adjusted.loc[3, "adjusted_close"] == 1030.0  # 1030.0
    assert adjusted.loc[2, "adjusted_volume"] == 250_000.0


def test_bonus_issue_adjustment():
    """
    Test 1:1 bonus issue (1 bonus share for every 1 held -> total 2 shares).
    Multiplier = (1 + 1) / 1 = 2.0.
    """
    raw_df = pd.DataFrame({
        "timestamp": pd.to_datetime(["2024-06-01", "2024-06-05"]),
        "open": [3000.0, 1500.0],
        "high": [3050.0, 1550.0],
        "low": [2950.0, 1480.0],
        "close": [3020.0, 1510.0],
        "volume": [50_000.0, 110_000.0],
    })

    bonus_action = CorporateAction(
        symbol="TCS",
        ex_date="2024-06-05",
        action_type=CorporateActionType.BONUS,
        ratio_numerator=1.0,
        ratio_denominator=1.0,
    )

    adjusted = CorporateActionAdjuster.adjust_historical_bars(raw_df, [bonus_action])
    assert adjusted.loc[0, "adjusted_close"] == 1510.0  # 3020 / 2
    assert adjusted.loc[1, "adjusted_close"] == 1510.0  # 1510 / 1


def test_no_actions_returns_identical_adjusted():
    raw_df = pd.DataFrame({
        "timestamp": pd.to_datetime(["2024-01-01", "2024-01-02"]),
        "open": [100.0, 102.0],
        "high": [105.0, 106.0],
        "low": [98.0, 101.0],
        "close": [103.0, 104.0],
        "volume": [1000.0, 1500.0],
    })
    adjusted = CorporateActionAdjuster.adjust_historical_bars(raw_df, [])
    assert (adjusted["adjusted_close"] == raw_df["close"]).all()
    assert (adjusted["adjusted_volume"] == raw_df["volume"]).all()


if __name__ == "__main__":
    test_split_backward_adjustment()
    print("  [OK] test_split_backward_adjustment")
    test_bonus_issue_adjustment()
    print("  [OK] test_bonus_issue_adjustment")
    test_no_actions_returns_identical_adjusted()
    print("  [OK] test_no_actions_returns_identical_adjusted")
    print("\nAll Corporate Action Adjustment tests PASSED successfully.")
