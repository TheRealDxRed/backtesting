import csv
import logging
import os

import backtrader as bt
import btoandav20 as btv20
import pytz
from backtrader import TimeFrame

# > This is just trading reversals of previous day high/low on ES and GC.
# >
# > 1. mark out the previous day high and low
# > 2. enter short if price taps PDH, enter long if price tals PDL.
#
# We're going to calculate the previous day high and low using daily bars.
# Then we'll use a lower time frame to trade the reversals.
# The stop loss will be 1/2 PDH-PDL away from the entry price.
# Same thing for the profit target. 1R as they say.

StoreCls = btv20.stores.OandaV20Store
DataCls = btv20.feeds.OandaV20Data


def main():
    logging.info("Starting Prior Day Reversal Strategy")
    cerebro = bt.Cerebro()

    # Add a strategy
    cerebro.addstrategy(PriorDayReversal, stop_loss_perc=0.5, profit_target_perc=0.5)
    cerebro.broker.setcash(100000.0)
    cerebro.broker.setcommission(commission=0.0)
    cerebro.addsizer(bt.sizers.FixedSize, stake=1)
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe")
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")

    # Data feed
    storeargs = dict(
        account=os.getenv("OANDA_ACCOUNT_ID"),
        token=os.getenv("OANDA_API_KEY"),
        practice=True,
    )
    store = StoreCls(**storeargs)
    logging.info("Connected to OANDA")

    # swap which instrument is commented here to change the instrument
    instrument = "XAU_USD"
    # instrument = "SPX500_USD"

    data0kwargs = dict(
        timeframe=TimeFrame.Minutes,
        compression=1,
        fromdate=bt.datetime.datetime(2020, 1, 1),
        todate=bt.datetime.datetime(2025, 1, 1),
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

    data1kwargs = dict(
        timeframe=TimeFrame.Days,
        compression=1,
        fromdate=bt.datetime.datetime(2019, 12, 1),
        todate=bt.datetime.datetime(2025, 1, 1),
        tz=pytz.timezone("US/Eastern"),
        backfill_start=True,
        backfill=True,
        bidask=True,
        useask=False,
        qcheck=0.5,
        historical=True,
    )
    data1 = store.getdata(dataname=instrument, **data1kwargs)
    cerebro.adddata(data1)

    logging.info("Data feeds added")

    logging.info(f"Starting Portfolio Value: {cerebro.broker.getvalue():.2f}")

    # Run the strategy
    logging.info("Running the strategy")
    results = cerebro.run()
    logging.info("Strategy run completed")

    strat = results[0]

    logging.info(f"Final Portfolio Value: {cerebro.broker.getvalue():.2f}")

    sharpe = strat.analyzers.sharpe.get_analysis()
    drawdown = strat.analyzers.drawdown.get_analysis()

    winners = sum(1 for t in strat.trades if t["pnl"] > 0)
    losers = sum(1 for t in strat.trades if t["pnl"] <= 0)

    logging.info(f"Sharpe Ratio: {sharpe.get('sharperatio', 'N/A')}")

    logging.info(f"Max Drawdown: {drawdown.max.drawdown:.2f}%")

    logging.info(f"Trades executed: {len(strat.trades)}")
    logging.info(f"Number of winning trades: {winners}")
    logging.info(f"Number of losing trades: {losers}")
    logging.info(
        f"Win rate: {winners / len(strat.trades) * 100:.2f}%"
        if strat.trades
        else "Win rate: N/A"
    )

    # Write trades to CSV
    with open("trades.csv", mode="w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(
            [
                "Datetime",
                "Symbol",
                "Size",
                "Price",
                "PnL",
                "TradeID",
            ]
        )
        for trade in strat.trades:
            writer.writerow(
                [
                    trade["datetime"],
                    trade["symbol"],
                    trade["size"],
                    trade["price"],
                    trade["pnl"],
                    trade["tradeid"],
                ]
            )


class PriorDayReversal(bt.Strategy):
    params = dict(
        stop_loss_perc=0.5,  # stop loss as a percentage of PDH-PDL range
        profit_target_perc=0.5,  # profit target as a percentage of PDH-PDL range
    )

    def __init__(self):
        self.dataclose = self.datas[0].close
        self.datahigh = self.datas[1].high
        self.datalow = self.datas[1].low
        self.pdh = None
        self.pdl = None
        self.trades = []
        self.order = None
        self.stop_price = None
        self.target_price = None
        self.last_date = None

    def next(self):
        dt = self.datas[0].datetime.date(0)
        if self.last_date != dt:
            self.last_date = dt
            if len(self.datahigh) > 1 and len(self.datalow) > 1:
                self.pdh = self.datahigh[-1]
                self.pdl = self.datalow[-1]

        if self.pdh is None or self.pdl is None:
            return

        if not self.position:
            if self.dataclose[0] >= self.pdh:
                size = 1
                self.order = self.sell(size=size)
                range_size = self.pdh - self.pdl
                self.stop_price = self.dataclose[0] + (
                    range_size * self.p.stop_loss_perc
                )
                self.target_price = self.dataclose[0] - (
                    range_size * self.p.profit_target_perc
                )
            elif self.dataclose[0] <= self.pdl:
                size = 1
                self.order = self.buy(size=size)
                range_size = self.pdh - self.pdl
                self.stop_price = self.dataclose[0] - (
                    range_size * self.p.stop_loss_perc
                )
                self.target_price = self.dataclose[0] + (
                    range_size * self.p.profit_target_perc
                )
        else:
            if self.position.size > 0:
                if self.dataclose[0] <= self.target_price:
                    self.close()
                elif self.dataclose[0] >= self.stop_price:
                    self.close()
            elif self.position.size < 0:
                if self.dataclose[0] >= self.target_price:
                    self.close()
                elif self.dataclose[0] <= self.stop_price:
                    self.close()

    def notify_trade(self, trade):
        if trade.isclosed:
            pnl = trade.pnl
            commission = trade.commission
            trade_info = {
                "datetime": self.datas[0].datetime.datetime(0),
                "symbol": self.datas[0]._name,
                "size": trade.size,
                "price": trade.price,
                "pnl": pnl,
                "commission": commission,
                "tradeid": trade.ref,
            }
            self.trades.append(trade_info)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )

    try:
        main()
    except KeyboardInterrupt:
        print()  # hack to move to next line
        logging.info("Process interrupted by user. Exiting...")
