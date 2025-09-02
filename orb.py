import logging
import os

import backtrader as bt
import btoandav20 as bto
import pytz
from backtrader import TimeFrame

StoreCls = bto.stores.OandaV20Store
DataCls = bto.feeds.OandaV20Data
SizerCls = bt.sizers.PercentSizerInt

datetime = bt.datetime.datetime
time = bt.datetime.time

OANDA_API_KEY = os.getenv("OANDA_API_KEY")
OANDA_ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID")


class ORBStrategy(bt.Strategy):
    params = (
        (
            "open_time",
            time(hour=9, minute=30),
        ),
        ("entry_offset", 5.0),
        ("r", 1.0),
    )

    def __init__(self):
        self.take_range_next_bar: bool = False
        self.open_high: float | None = None
        self.open_low: float | None = None
        self.open_range: float | None = None

    def prenext(self):
        self.next(frompre=True)

    def next(self, frompre=False):
        if frompre:  # Skip if data is not live
            return

        dt: datetime = self.datas[0].datetime.datetime(0)
        if dt.time() < self.p.open_time:
            logging.debug(f"[{dt}] Before market open, waiting for open range.")

        if dt.time() == self.p.open_time:
            self.take_range_next_bar = True
            logging.info(f"[{dt}] Market opened, taking open range next bar.")

        if self.take_range_next_bar:
            self.open_high = self.datas[0].high[-1]
            self.open_low = self.datas[0].low[-1]

            # pyright has a stroke if i don't EXPLICITLY tell it these values exist even though i JUST set them
            assert self.open_high is not None and self.open_low is not None

            self.open_range = self.open_high - self.open_low
            logging.info(
                f"[{dt}] Opening Range defined: High={self.open_high}, Low={self.open_low}, Range={self.open_range}"
            )
            self.take_range_next_bar = False

        if self.open_range is not None and not self.position:
            entry_long = self.open_high + self.p.entry_offset
            entry_short = self.open_low - self.p.entry_offset
            stop_loss_long = entry_long - self.open_range
            stop_loss_short = entry_short + self.open_range
            take_profit_long = entry_long + self.p.r * self.open_range
            take_profit_short = entry_short - self.p.r * self.open_range

            logging.info(
                f"[{dt}] Placing long order: Entry={entry_long}, Stop Loss={stop_loss_long}"
            )
            self.buy_bracket(
                price=entry_long,
                exectype=bt.Order.Stop,
                stopprice=stop_loss_long,
                limitprice=take_profit_long,
                stopexec=bt.Order.Stop,
                limitexec=bt.Order.Limit,
                valid=bt.Order.DAY,
                size=1,
            )
            # logging.info(
            #     f"[{dt}] Placing short order: Entry={entry_short}, Stop Loss={stop_loss_short}"
            # )
            # self.sell_bracket(
            #     price=entry_short,
            #     exectype=bt.Order.Stop,
            #     stopprice=stop_loss_short,
            #     limitprice=take_profit_short,
            #     stopexec=bt.Order.Stop,
            #     limitexec=bt.Order.Limit,
            #     valid=bt.Order.DAY,
            #     size=1,
            # )

            self.open_high = None
            self.open_low = None
            self.open_range = None


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )

    cerebro = bt.Cerebro()
    cerebro.addstrategy(ORBStrategy, open_time=time(9, 30), entry_offset=5.0, r=1.5)
    cerebro.broker.setcash(100000.0)
    cerebro.broker.setcommission(commission=0.0)
    cerebro.addsizer(SizerCls, percents=1.0)
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe")
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="tradeanalyzer")
    cerebro.addanalyzer(bt.analyzers.Transactions, _name="transactions")

    storekwargs = dict(
        account=OANDA_ACCOUNT_ID,
        token=OANDA_API_KEY,
        practice=True,
    )
    store = StoreCls(**storekwargs)

    logging.info("Connected to OANDA")

    instrument = "US30_USD"

    data0kwargs = dict(
        timeframe=TimeFrame.Minutes,
        compression=15,
        fromdate=bt.datetime.datetime(2024, 1, 1),
        todate=bt.datetime.datetime(2025, 8, 31),
        tz=pytz.timezone("US/Eastern"),
        backfill_start=True,
        backfill=True,
        bidask=True,
        useask=False,
        qcheck=0.5,
        historical=True,
    )
    data0 = store.getdata(dataname=instrument, **data0kwargs)
    cerebro.adddata(data0)

    logging.info("Data feed(s) added")

    logging.info(f"Starting Portfolio Value: {cerebro.broker.getvalue():.2f}")

    logging.info("Running the strategy")
    results = cerebro.run()
    logging.info("Strategy run completed")

    strat = results[0]

    logging.info(f"Final Portfolio Value: {cerebro.broker.getvalue():.2f}")

    sharpe = strat.analyzers.sharpe.get_analysis()
    drawdown = strat.analyzers.drawdown.get_analysis()
    tradeanalyzer = strat.analyzers.tradeanalyzer.get_analysis()
    transactions = strat.analyzers.transactions.get_analysis()

    logging.info(f"Sharpe Ratio: {sharpe.get('sharperatio', 'N/A')}")
    logging.info(f"Drawdown: {drawdown.get('max', {}).get('drawdown', 'N/A')}%")
    logging.info(f"Total Trades: {tradeanalyzer.get('total', {}).get('total', 0)}")

    winners = tradeanalyzer.get("won", {}).get("total", 0)
    losers = tradeanalyzer.get("lost", {}).get("total", 0)

    if winners + losers > 0:
        win_rate = winners / (winners + losers) * 100
        logging.info(f"Win Rate: {win_rate:.2f}%")
    else:
        logging.info("Win Rate: N/A (no trades)")
