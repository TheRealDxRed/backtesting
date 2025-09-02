import csv
import logging
import os

import backtrader as bt
import btoandav20 as btv20
import pandas as pd
import pytz
from backtrader import TimeFrame

# > This is just trading reversals of previous day high/low on ES and GC.
# >
# > 1. mark out the previous day high and low
# > 2. enter short if price taps PDH, enter long if price tals PDL.

StoreCls = btv20.stores.OandaV20Store
DataCls = btv20.feeds.OandaV20Data


def main():
    logging.info("Starting Prior Day Reversal Strategy")
    cerebro = bt.Cerebro()

    # Add a strategy
    cerebro.addstrategy(PriorDayReversal, stop_loss_perc=0.1, profit_target_perc=0.5)
    cerebro.broker.setcash(100000.0)
    cerebro.broker.setcommission(
        commission=0.0,
        leverage=20.0,
        margin=0.5,
        mult=1.0,
        stocklike=False,
        interest=0.0,
    )
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe")
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="tradeanalyzer")
    cerebro.addanalyzer(bt.analyzers.Transactions, _name="transactions")

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
        fromdate=bt.datetime.datetime(2024, 1, 1),
        todate=bt.datetime.datetime(2024, 12, 31),
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
        fromdate=bt.datetime.datetime(2023, 12, 31),
        todate=bt.datetime.datetime(2024, 12, 31),
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
    tradeanalyzer = strat.analyzers.tradeanalyzer.get_analysis()
    transactions = strat.analyzers.transactions.get_analysis()

    logging.debug(f"Sharpe Ratio: {type(sharpe)}")
    logging.debug(f"Drawdown: {type(drawdown)}")
    logging.debug(f"Trade Analyzer: {type(tradeanalyzer)}")
    logging.debug(f"Transactions: {type(transactions)}")

    winners = tradeanalyzer.won.total if tradeanalyzer.won.total else 0
    losers = tradeanalyzer.lost.total if tradeanalyzer.lost.total else 0

    logging.info(f"Sharpe Ratio: {sharpe.get('sharperatio', 'N/A')}")

    logging.info(f"Max Drawdown: {drawdown.max.drawdown:.2f}%")

    logging.info(
        f"Trades executed: {tradeanalyzer.total.closed if tradeanalyzer.total.closed else 0}"
    )
    logging.info(f"Number of winning trades: {winners}")
    logging.info(f"Number of losing trades: {losers}")
    logging.info(
        f"Win rate: { (winners / (winners + losers) * 100) if (winners + losers) > 0 else 0:.2f}%"
    )

    logging.info(
        f"Average number of bars in the market: {tradeanalyzer.len.average if tradeanalyzer.len.average else 0}"
    )
    logging.info(
        f"Longest time in the market: {tradeanalyzer.len.max if tradeanalyzer.len.max else 0} bars"
    )
    logging.info(
        f"Shortest time in the market: {tradeanalyzer.len.min if tradeanalyzer.len.min else 0} bars"
    )

    logging.info(
        f"Net Profit: {tradeanalyzer.pnl.net.total if tradeanalyzer.pnl.net.total else 0:.2f}"
    )
    logging.info(
        f"Profit Factor: {tradeanalyzer.pnl.net.total / abs(tradeanalyzer.pnl.net.total) if tradeanalyzer.pnl.net.total and tradeanalyzer.pnl.net.total < 0 else 'N/A'}"
    )

    # save transactions to csv
    logging.info("Saving transactions to trades.csv")

    # format the DF correctly
    rows = []
    for dt, row in transactions.items():
        for trans in row:
            rows.append(
                {
                    "date": dt,
                    "amount": trans[0],
                    "price": trans[1],
                    # "sid": trans[2],
                    "symbol": trans[3],
                    "value": trans[4],
                }
            )

    df = pd.DataFrame(rows)
    df.to_csv("trades.csv")
    logging.info("Transactions saved to trades.csv")

    cerebro.plot()


class PriorDayReversal(bt.Strategy):
    params = dict(
        stop_loss_perc=0.5,  # stop loss as a percentage of PDH-PDL range
        profit_target_perc=0.5,  # profit target as a percentage of PDH-PDL range
        risk_per_trade=0.01,  # risk per trade as a percentage of account equity
    )

    def __init__(self):
        self.dataclose = self.datas[0].close
        self.datahigh = self.datas[1].high
        self.datalow = self.datas[1].low
        self.pdh = None
        self.pdl = None
        self.last_date = None
        self.long_orders = None
        self.short_orders = None

        logging.info("Prior Day Reversal Strategy initialized")
        logging.info(f"Stop Loss Percentage: {self.p.stop_loss_perc * 100}%")
        logging.info(f"Profit Target Percentage: {self.p.profit_target_perc * 100}%")

    def next(self):
        dt = self.datas[0].datetime.date(0)
        if self.last_date != dt:
            self.last_date = dt
            if len(self.datahigh) > 1 and len(self.datalow) > 1:
                self.pdh = self.datahigh[-1]
                self.pdl = self.datalow[-1]

        if self.pdh is None or self.pdl is None:
            return

        # execute only at NY open (9:30 AM Eastern)
        if self.datas[0].datetime.time(0) == bt.datetime.time(9, 30):
            pdr = self.pdh - self.pdl

            long_entry_price = self.pdl
            long_stop_price = self.pdl - pdr * self.p.stop_loss_perc
            long_limit_price = self.pdl + pdr * self.p.profit_target_perc

            short_entry_price = self.pdh
            short_stop_price = self.pdh + pdr * self.p.stop_loss_perc
            short_limit_price = self.pdh - pdr * self.p.profit_target_perc

            lot_size = int(
                (self.broker.getvalue() * self.p.risk_per_trade)
                / (pdr * self.p.stop_loss_perc)
            )

            logging.debug(f"Lot size calculated: {lot_size}")

            logging.debug(
                f"{dt} - Long Entry: {long_entry_price:.2f}, Stop: {long_stop_price:.2f}, Limit: {long_limit_price:.2f}"
            )
            logging.debug(
                f"{dt} - Short Entry: {short_entry_price:.2f}, Stop: {short_stop_price:.2f}, Limit: {short_limit_price:.2f}"
            )

            self.long_orders = self.buy_bracket(
                size=lot_size,
                data=self.datas[0],
                price=long_entry_price,
                exectype=bt.Order.Limit,
                stopprice=long_stop_price,
                limitprice=long_limit_price,
                stopexec=bt.Order.Stop,
                limitexec=bt.Order.Limit,
                valid=bt.Order.DAY,
            )

            for o in self.long_orders:
                logging.debug(
                    f"Long order created: {o.created.size} @ {o.created.price} ({o.ref})"
                )

            self.short_orders = self.sell_bracket(
                size=lot_size,
                data=self.datas[0],
                price=short_entry_price,
                exectype=bt.Order.Limit,
                stopprice=short_stop_price,
                limitprice=short_limit_price,
                stopexec=bt.Order.Stop,
                limitexec=bt.Order.Limit,
                valid=bt.Order.DAY,
            )

            for o in self.short_orders:
                logging.debug(
                    f"Short order created: {o.created.size} @ {o.created.price} ({o.ref})"
                )

        # cancel unfilled orders at the end of the day (4:00 PM Eastern) and flatten
        if self.datas[0].datetime.time(0) == bt.datetime.time(16, 0):
            if self.long_orders:
                for order in self.long_orders:
                    if order.status in [bt.Order.Submitted, bt.Order.Accepted]:
                        self.cancel(order)
                self.long_orders = None
            if self.short_orders:
                for order in self.short_orders:
                    if order.status in [bt.Order.Submitted, bt.Order.Accepted]:
                        self.cancel(order)
                self.short_orders = None

            if self.position != 0:
                self.close()

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return

        if order.status in [order.Completed]:
            # cancel short entry if long entry is filled and vice versa
            # i hate manual OCO like this but backtrader's OCO handling is fucked
            if order.isbuy() and self.short_orders and self.position:
                logging.debug(f"Long entry filled, cancelling short entry: {order.ref}")
                for o in self.short_orders:
                    self.cancel(o)
                self.short_orders = None
            elif order.issell() and self.long_orders and self.position:
                logging.debug(f"Short entry filled, cancelling long entry: {order.ref}")
                for o in self.long_orders:
                    self.cancel(o)
                self.long_orders = None

        elif order.status in [order.Margin]:
            logging.warning(f"Margin issue with order {order.ref}")
        elif order.status in [order.Rejected]:
            logging.warning(f"Order Rejected: {order.ref}")


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
    )

    try:
        main()
    except KeyboardInterrupt:
        print()  # hack to move to next line
        logging.info("Process interrupted by user. Exiting...")
