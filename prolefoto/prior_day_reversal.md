# Prior Day Reversal

## Intro

> This is just trading reversals of previous day high/low on ES and GC.
>
> 1. mark out the previous day high and low
> 2. enter short if price taps PDH, enter long if price tals PDL.

Keeping it simple. I like that. Let's talk about a few technicalities first:

1. `ES` and `GC` are a PITA to collect data for on their own, but we can work around
   that by using OANDA's `SPX500_USD` and `XAU_USD`, which follow the same indices as
   `ES` and `GC`, respectively. OANDA's data is free-to-use for essentially any
   purpose, so we're going to be working with that instead.
2. We still don't have an idea of SL and TP values on each entry, so that needs
   to get sorted _before_ we can start backtesting.

## First Test

I'll take the naive approach first, setting the SL and TP to `1/2*(PDH-PDL)`, or
_prior day range_ in English. This will give us an idea of how often this concept
alone succeeds. I'll start with a modest 5 years (start of 2020 to start of 2025)
which gives us this:

First, `XAU_USD`:

```
$ python prolefoto/prior_day_reversal.py
2025-08-23 21:21:47,071 - INFO - Starting Prior Day Reversal Strategy
2025-08-23 21:21:47,071 - INFO - Connected to OANDA
2025-08-23 21:21:47,081 - INFO - Data feeds added
2025-08-23 21:21:47,081 - INFO - Starting Portfolio Value: 100000.00
2025-08-23 21:21:47,081 - INFO - Running the strategy
2025-08-23 21:22:13,106 - INFO - Strategy run completed
2025-08-23 21:22:13,106 - INFO - Final Portfolio Value: 99905.88
2025-08-23 21:22:13,113 - INFO - Sharpe Ratio: -16.462564900286527
2025-08-23 21:22:13,113 - INFO - Max Drawdown: 0.51%
2025-08-23 21:22:13,113 - INFO - Trades executed: 17766
2025-08-23 21:22:13,113 - INFO - Number of winning trades: 8891
2025-08-23 21:22:13,113 - INFO - Number of losing trades: 8875
2025-08-23 21:22:13,113 - INFO - Win rate: 50.05%
```

Second, `SPX500_USD`:

```
$ python prolefoto/prior_day_reversal.py
2025-08-23 21:23:33,663 - INFO - Starting Prior Day Reversal Strategy
2025-08-23 21:23:33,663 - INFO - Connected to OANDA
2025-08-23 21:23:33,672 - INFO - Data feeds added
2025-08-23 21:23:33,672 - INFO - Starting Portfolio Value: 100000.00
2025-08-23 21:23:33,672 - INFO - Running the strategy
2025-08-23 21:23:58,370 - INFO - Strategy run completed
2025-08-23 21:23:58,370 - INFO - Final Portfolio Value: 101149.00
2025-08-23 21:23:58,377 - INFO - Sharpe Ratio: -2.1314923385295037
2025-08-23 21:23:58,377 - INFO - Max Drawdown: 0.90%
2025-08-23 21:23:58,377 - INFO - Trades executed: 17895
2025-08-23 21:23:58,377 - INFO - Number of winning trades: 8687
2025-08-23 21:23:58,377 - INFO - Number of losing trades: 9208
2025-08-23 21:23:58,377 - INFO - Win rate: 48.54%
```

My first impressions aren't very good. A 50% winrate is tradable, sure, but only
with higher-R entries. At 1R, we're doing about as well as a coinflip (worse,
even in the case of `ES`/`SPX500_USD`). That isn't good news. I'll mess around with
trailing stops next to see if I can squeeze something out of this consistent
winrate.
