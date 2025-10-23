"""
Tom Hougaard's School Run Strategy (SRS) has evolved somewhat over the years.
Originally, it was a simple breakout of the second 15m candle in the session,
which works surprisingly well on its own. There are, however, a couple of
problems with SRS that make it hard to automate.

1. No exit strategy.
   The SRS doesn't explicitly define when/where to cut a position, relying
   instead on the trader's discretion, which can often be a professional's
   greatest weakness.

2. Poor performance on range days.
   An interesting property of the second 15m candle is that it often has a
   similar range (`high - low`) to the opening candle of the same timeframe.
   On range days, specifically, the SRS range is usually just a few points
   short of either the high-of-day or low-of-day. This leads to offside,
   breakout-focused entries with very low MFE.

In order to remedy these issues, Hougaard established the SRS Anti. In this new
version of the strategy, the overnight range (00:00-06:00) is taken into
consideration to determine whether a sideways day is on the horizon. When the
SRS triggers within the overnight range (ONR), its entries are reversed, taking
the short side above SRS high and the long side below SRS low (hence, SRS
_Anti_). Outside of ONR, the SRS behaves (largely) as usual.

My goal here is twofold:

1. Determine whether SRS or SRS Anti signals are more effective long-term.
2. Determine a good set of exit conditions.

If even one of these goals is completed, it will make the SRS that much easier
to automate, leaving me with more time for research (and everyday life, I
suppose).
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import v20


class Candlestick:
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    def __init__(self, dt: datetime, o: float, h: float, l: float, c: float, v: float):
        self.time = dt
        self.open = o
        self.high = h
        self.low = l
        self.close = c
        self.volume = v


class TestResult:
    """
    Contains all relevant results for testing.
    """

    """
    Win rate for the traditional SRS
    """
    school_run_wr: float

    """
    Win rate for the improved SRS Anti
    """
    anti_wr: float

    def __init__(self, school_run_wr: float, anti_wr: float) -> None:
        self.school_run_wr = school_run_wr
        self.anti_wr = anti_wr


def run(end_date: datetime, num_days: int):
    logger = logging.getLogger("srs_and_onr.run")

    logger.info("Connecting to v20 API")

    oanda = v20.Context(
        "api-fxpractice.oanda.com",
        token=os.getenv("OANDA_API_KEY"),
    )

    accounts_response = oanda.account.list()
    if accounts_response.status != 200:
        logger.error("Failed to connect to OANDA server: %s", accounts_response)
        exit(1)

    logger.info("Gathering data")

    candles_response = oanda.instrument.candles(
        instrument="US30_USD",
        price="M",
        granularity="D",
        count=num_days,
        to=end_date,
    )

    if candles_response.status != 200:
        logger.error("Failed to fetch candles: %s", candles_response)

    candles_count = len(candles_response.body.get("candles"))
    candles_first_date = datetime.fromisoformat(
        candles_response.body.get("candles")[0].time
    )
    candles_last_date = datetime.fromisoformat(
        candles_response.body.get("candles")[-1].time
    )

    logger.info(
        "Testing on %i days from %s to %s",
        candles_count,
        candles_first_date,
        candles_last_date,
    )

    timezone_info = ZoneInfo("America/New_York")

    test_results = []

    for session in candles_response.body.get("candles"):
        date = datetime.fromisoformat(session.time).astimezone(timezone_info)
        intraday_candles = oanda.instrument.candles(
            instrument="US30_USD",
            granularity="M15",
            fromTime=(date + timedelta(hours=0)).isoformat(),
            toTime=(date + timedelta(hours=16)).isoformat(),
        )

        if intraday_candles.status != 200:
            logger.error(
                "Failed to fetch intraday candles for %s. Skipping day: %s",
                date.date(),
                intraday_candles.body.get("errorMessage"),
            )
            continue

        candles_list = []
        for candle in intraday_candles.body.get("candles"):
            candles_list.append(
                Candlestick(
                    datetime.fromisoformat(candle.time).astimezone(timezone_info),
                    candle.mid.o,
                    candle.mid.h,
                    candle.mid.l,
                    candle.mid.c,
                    candle.volume,
                )
            )

        test_results.append(test_day(candles_list))

    test_results_len = len(test_results)

    if test_results_len == 0:
        return

    # TODO: i don't actually want to log the results. they should be tallied up and analyzed instead
    for result in test_results:
        logger.info("Result: %s", result)


def test_day(candles: list[Candlestick]) -> TestResult:
    # TODO: actually write the tests
    return TestResult(0, 0)


def main():
    logging.basicConfig(level=logging.DEBUG)
    try:
        run(datetime.now() - timedelta(days=2), 50)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
