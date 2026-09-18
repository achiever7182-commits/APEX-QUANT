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


def test_prevent_double_split_adjustment():
    """
    Test that when adjust_splits=False (input data is already split-adjusted by provider):
    - Historical prices prior to ex-date are NOT divided again by the split multiplier.
    - Historical volumes prior to ex-date are NOT multiplied again.
    - Prevents the artificial ~100% price spike across split boundaries.
    """
    # Simulate pre-adjusted prices as delivered by Yahoo Finance around 2024-10-28 2:1 split:
    # Pre-split close is ~1327.85 and post-split close is ~1334.35 (already split-adjusted by provider)
    pre_adjusted_df = pd.DataFrame({
        "timestamp": pd.to_datetime(["2024-10-25", "2024-10-28"]),
        "open": [1343.50, 1337.00],
        "high": [1352.00, 1345.00],
        "low": [1320.00, 1330.00],
        "close": [1327.85, 1334.35],
        "volume": [18_000_000.0, 10_000_000.0],
    })

    split_action = CorporateAction(
        symbol="RELIANCE",
        ex_date=date(2024, 10, 28),
        action_type=CorporateActionType.SPLIT,
        ratio_numerator=2.0,
        ratio_denominator=1.0,
    )

    # Calling with adjust_splits=False prevents double adjustment
    adjusted = CorporateActionAdjuster.adjust_historical_bars(
        pre_adjusted_df,
        [split_action],
        adjust_splits=False,
    )

    # 1. Prices prior to ex-date must NOT be divided by 2.0 again
    assert adjusted.loc[0, "adjusted_close"] == 1327.85
    assert adjusted.loc[1, "adjusted_close"] == 1334.35

    # 2. Return across split date should be normal (~ +0.49%), NOT +100%
    day_return = (adjusted.loc[1, "adjusted_close"] / adjusted.loc[0, "adjusted_close"]) - 1.0
    assert abs(day_return - 0.004895) < 1e-4

    # 3. Volume prior to ex-date must NOT be doubled again
    assert adjusted.loc[0, "adjusted_volume"] == 18_000_000.0
    assert adjusted.loc[1, "adjusted_volume"] == 10_000_000.0

    # 4. Adjustment factor is 1.0
    assert (adjusted["adjustment_factor"] == 1.0).all()


def test_provider_split_adjusted_contract():
    """Verify provider declarations regarding whether their bars are already split-adjusted."""
    from data.market.provider import YahooFinanceProvider, MockMarketDataProvider

    yahoo = YahooFinanceProvider()
    assert yahoo.is_split_adjusted is True, "YahooFinanceProvider chart API quotes must declare is_split_adjusted=True"

    mock = MockMarketDataProvider()
    assert mock.is_split_adjusted is False, "MockMarketDataProvider must declare is_split_adjusted=False"


def test_loader_prevents_double_adjustment():
    """Verify MarketDataLoader automatically coordinates with provider contract to avoid double adjustment."""
    import shutil
    import tempfile
    from pathlib import Path
    from data.corporate_actions.loader import CorporateActionsLoader
    from data.market.loader import MarketDataLoader
    from data.market.provider import IMarketDataProvider
    from data.market.storage import ParquetMarketDataStorage

    class DummySplitAdjustedProvider(IMarketDataProvider):
        @property
        def is_split_adjusted(self) -> bool:
            return True

        def get_daily_bars(self, symbol, start_date=None, end_date=None):
            return pd.DataFrame({
                "timestamp": pd.to_datetime(["2024-10-25", "2024-10-28"]),
                "open": [100.0, 101.0],
                "high": [105.0, 106.0],
                "low": [98.0, 99.0],
                "close": [103.0, 104.0],
                "volume": [1000.0, 1200.0],
            })

        def get_intraday_bars(self, symbol, timeframe="5m", start_date=None, end_date=None):
            return pd.DataFrame()

        def get_corporate_actions(self, symbol, start_date=None, end_date=None):
            return [
                CorporateAction(
                    symbol=symbol,
                    ex_date=date(2024, 10, 28),
                    action_type=CorporateActionType.SPLIT,
                    ratio_numerator=2.0,
                    ratio_denominator=1.0,
                )
            ]

        def get_instruments(self):
            return ["TEST"]

    temp_dir = Path(tempfile.mkdtemp(prefix="apex_test_loader_"))
    try:
        storage = ParquetMarketDataStorage(base_dir=temp_dir / "parquet")
        actions_loader = CorporateActionsLoader(cache_dir=temp_dir / "actions")
        loader = MarketDataLoader(
            provider=DummySplitAdjustedProvider(),
            storage=storage,
            actions_loader=actions_loader,
        )
        clean_df, report = loader.ingest_symbol("TEST")
        
        # Pre-split close (103.0) should NOT be halved to 51.5
        assert clean_df.loc[0, "adjusted_close"] == 103.0
        assert clean_df.loc[1, "adjusted_close"] == 104.0
        assert (clean_df["adjustment_factor"] == 1.0).all()
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_corporate_actions_point_in_time_cutoff():
    """
    Test point-in-time filtering on CorporateActionsLoader.load_actions:
    - Future corporate actions are excluded from a historical query.
    - Actions on the cutoff date are included.
    - No cutoff (as_of_date=None) preserves existing behavior.
    """
    import shutil
    import tempfile
    from pathlib import Path
    from datetime import datetime
    from data.corporate_actions.loader import CorporateActionsLoader

    temp_dir = Path(tempfile.mkdtemp(prefix="apex_test_actions_pit_"))
    try:
        loader = CorporateActionsLoader(cache_dir=temp_dir)
        actions = [
            CorporateAction(
                symbol="RELIANCE",
                ex_date=date(2020, 5, 1),
                action_type=CorporateActionType.DIVIDEND,
                value=6.5,
            ),
            CorporateAction(
                symbol="RELIANCE",
                ex_date="2022-06-15",
                action_type=CorporateActionType.DIVIDEND,
                value=8.0,
            ),
            CorporateAction(
                symbol="RELIANCE",
                ex_date=date(2024, 10, 28),
                action_type=CorporateActionType.SPLIT,
                ratio_numerator=2.0,
                ratio_denominator=1.0,
            ),
        ]
        loader.save_actions("RELIANCE", actions)

        # 1. No cutoff -> returns all 3 actions
        all_actions = loader.load_actions("RELIANCE", as_of_date=None)
        assert len(all_actions) == 3

        # 2. Historical query prior to split -> future split excluded
        pit_actions = loader.load_actions("RELIANCE", as_of_date="2023-01-01")
        assert len(pit_actions) == 2
        assert all(a.ex_date_obj <= date(2023, 1, 1) for a in pit_actions)
        assert not any(a.action_type == CorporateActionType.SPLIT for a in pit_actions)

        # 3. Actions exactly on the cutoff date are included
        cutoff_exact = loader.load_actions("RELIANCE", as_of_date=date(2022, 6, 15))
        assert len(cutoff_exact) == 2
        assert cutoff_exact[-1].ex_date_obj == date(2022, 6, 15)

        # 4. Cutoff with datetime object
        dt_cutoff = loader.load_actions("RELIANCE", as_of_date=datetime(2020, 5, 1, 10, 0))
        assert len(dt_cutoff) == 1
        assert dt_cutoff[0].action_type == CorporateActionType.DIVIDEND

        # 5. Query prior to all actions returns empty list
        early_cutoff = loader.load_actions("RELIANCE", as_of_date="2019-12-31")
        assert len(early_cutoff) == 0
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    test_split_backward_adjustment()
    print("  [OK] test_split_backward_adjustment")
    test_bonus_issue_adjustment()
    print("  [OK] test_bonus_issue_adjustment")
    test_no_actions_returns_identical_adjusted()
    print("  [OK] test_no_actions_returns_identical_adjusted")
    test_prevent_double_split_adjustment()
    print("  [OK] test_prevent_double_split_adjustment")
    test_provider_split_adjusted_contract()
    print("  [OK] test_provider_split_adjusted_contract")
    test_loader_prevents_double_adjustment()
    print("  [OK] test_loader_prevents_double_adjustment")
    test_corporate_actions_point_in_time_cutoff()
    print("  [OK] test_corporate_actions_point_in_time_cutoff")
    print("\nAll Corporate Action Adjustment tests PASSED successfully.")
