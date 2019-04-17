#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Yahoo! Finance market data downloader (+fix for Pandas Datareader)
# https://github.com/ranaroussi/fix-yahoo-finance
#
# Copyright 2017-2019 Ran Aroussi
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

from __future__ import print_function

__version__ = "0.1.25"
__author__ = "Ran Aroussi"
__all__ = ['download', 'Ticker', 'pdr_override',
           'get_yahoo_crumb', 'parse_ticker_csv']

import time as _time
import datetime as _datetime
import requests as _requests
import pandas as _pd
import numpy as _np
import sys as _sys


def parse_ticker_csv(csv_str, auto_adjust):
    raise DeprecationWarning('This method is deprecated')
    pass


def get_yahoo_crumb(force=False):
    raise DeprecationWarning('This method is deprecated')
    pass


class Ticker():

    def __init__(self, ticker):
        self.ticker = ticker
        self._history = None
        self._base_url = 'https://query1.finance.yahoo.com'

    @property
    def info(self):
        """ retreive metadata and currenct price data """
        url = "{}/v7/finance/quote?symbols={}".format(
            self._base_url, self.ticker)
        r = _requests.get(url=url).json()["quoteResponse"]["result"]
        if len(r) > 0:
            return r[0]
        return {}

    """
    # @todo
    def _options(self):
        # https://query1.finance.yahoo.com/v7/finance/options/SPY
        pass
    """

    @staticmethod
    def _auto_adjust(data):
        df = data.copy()
        ratio = df["Close"] / df["Adj Close"]
        df["Adj Open"] = df["Open"] / ratio
        df["Adj High"] = df["High"] / ratio
        df["Adj Low"] = df["Low"] / ratio

        df.drop(
            ["Open", "High", "Low", "Close"],
            axis=1, inplace=True)

        df.rename(columns={
            "Adj Open": "Open", "Adj High": "High",
            "Adj Low": "Low", "Adj Close": "Close"
        }, inplace=True)

        df = df[["Open", "High", "Low", "Close", "Volume"]]
        return df

    @staticmethod
    def _parse_quotes(data):
        timestamps = data["timestamp"]
        ohlc = data["indicators"]["quote"][0]
        volumes = ohlc["volume"]
        opens = ohlc["open"]
        closes = ohlc["close"]
        lows = ohlc["low"]
        highs = ohlc["high"]

        adjclose = closes
        if "adjclose" in data["indicators"]:
            adjclose = data["indicators"]["adjclose"][0]["adjclose"]

        quotes = _pd.DataFrame({"Open": opens,
                                "High": highs,
                                "Low": lows,
                                "Close": closes,
                                "Adj Close": adjclose,
                                "Volume": volumes})

        quotes.index = _pd.to_datetime(timestamps, unit="s")
        quotes.sort_index(inplace=True)
        return quotes

    @staticmethod
    def _parse_actions(data):
        dividends = _pd.DataFrame(columns=["Dividends"])
        splits = _pd.DataFrame(columns=["Stock Splits"])

        if "events" in data:
            if "dividends" in data["events"]:
                dividends = _pd.DataFrame(data["events"]["dividends"].values())
                dividends.set_index("date", inplace=True)
                dividends.index = _pd.to_datetime(dividends.index, unit="s")
                dividends.sort_index(inplace=True)
                dividends.columns = ["Dividends"]

            if "splits" in data["events"]:
                splits = _pd.DataFrame(data["events"]["splits"].values())
                splits.set_index("date", inplace=True)
                splits.index = _pd.to_datetime(
                    splits.index, unit="s")
                splits.sort_index(inplace=True)
                splits["Stock Splits"] = splits["numerator"] / \
                    splits["denominator"]
                splits = splits["Stock Splits"]

        return dividends, splits

    @property
    def dividends(self):
        if self._history is None:
            self._history = self.history(period="max")
        dividends = self._history["Dividends"]
        return dividends[dividends != 0]

    @property
    def splits(self):
        if self._history is None:
            self.history(period="max")
        splits = self._history["Stock Splits"]
        return splits[splits != 0]

    @property
    def actions(self):
        if self._history is None:
            self.history(period="max")
        actions = self._history[["Dividends", "Stock Splits"]]
        return actions[actions != 0].dropna(how='all').fillna(0)

    def history(self, period="1mo", interval="1d",
                start=None, end=None, prepost=False,
                actions=True, auto_adjust=False):
        """
        :Parameters:
            period : str
                Valid periods: 1d,5d,1mo,3mo,6mo,1y,2y,5y,10y,ytd,max
                Either Use period parameter or use start and end
            interval : str
                Valid intervals: 1m,2m,5m,15m,30m,60m,90m,1h,1d,5d,1wk,1mo,3mo
                Intraday data cannot extend last 60 days
            start: str
                Download start date string (YYYY-MM-DD) or _datetime.
                Default is 1900-01-01
            end: str
                Download end date string (YYYY-MM-DD) or _datetime.
                Default is now
            prepost : bool
                Include Pre and Post market data in results?
                Default is False
            auto_adjust: bool
                Adjust all OHLC automatically? Default is False
        """

        if period is None or period.lower() == "max":
            if start is None:
                start = -2208988800
            elif isinstance(start, _datetime.datetime):
                start = int(_time.mktime(start.timetuple()))
            else:
                start = int(_time.mktime(
                    _time.strptime(str(start), '%Y-%m-%d')))
            if end is None:
                end = int(_time.time())
            elif isinstance(end, _datetime.datetime):
                end = int(_time.mktime(end.timetuple()))
            else:
                end = int(_time.mktime(_time.strptime(str(end), '%Y-%m-%d')))

            params = {"period1": start, "period2": end}
        else:
            period = period.lower()
            params = {"range": period}

        params["interval"] = interval.lower()
        params["includePrePost"] = prepost
        params["events"] = "div,splits"

        url = "{}/v8/finance/chart/{}".format(self._base_url, self.ticker)
        data = _requests.get(url=url, params=params).json()

        # Getting data from json
        error = data["chart"]["error"]
        if error:
            raise ValueError(error["description"])

        # quotes
        quotes = self._parse_quotes(data["chart"]["result"][0])
        if auto_adjust:
            quotes = self._auto_adjust(quotes)

        quotes = _np.round(quotes, data[
            "chart"]["result"][0]["meta"]["priceHint"])
        quotes['Volume'] = quotes['Volume'].fillna(0).astype(_np.int64)

        quotes.dropna(inplace=True)

        # actions
        dividends, splits = self._parse_actions(data["chart"]["result"][0])

        # combine
        df = _pd.concat([quotes, dividends, splits], axis=1, sort=True)
        df["Dividends"].fillna(0, inplace=True)
        df["Stock Splits"].fillna(0, inplace=True)

        # index eod/intraday
        df.index = df.index.tz_localize("UTC").tz_convert(
            data["chart"]["result"][0]["meta"]["exchangeTimezoneName"])

        if params["interval"][-1] == "m":
            df.index.name = "Datetime"
        else:
            df.index = _pd.to_datetime(df.index.date)
            df.index.name = "Date"

        self._history = df.copy()

        if not actions:
            df.drop(columns=["Dividends", "Stock Splits"], inplace=True)

        return df


def download(tickers, start=None, end=None, actions=False, threads=None,
             group_by='column', auto_adjust=False, progress=True,
             period="max", interval="1d", prepost=False, **kwargs):
    """Download yahoo tickers
    :Parameters:
        tickers : str, list
            List of tickers to download
        period : str
            Valid periods: 1d,5d,1mo,3mo,6mo,1y,2y,5y,10y,ytd,max
            Either Use period parameter or use start and end
        interval : str
            Valid intervals: 1m,2m,5m,15m,30m,60m,90m,1h,1d,5d,1wk,1mo,3mo
            Intraday data cannot extend last 60 days
        start: str
            Download start date string (YYYY-MM-DD) or _datetime.
            Default is 1900-01-01
        end: str
            Download end date string (YYYY-MM-DD) or _datetime.
            Default is now
        group_by : str
            Group by 'ticker' or 'column' (default)
        prepost : bool
            Include Pre and Post market data in results?
            Default is False
        auto_adjust: bool
            Adjust all OHLC automatically? Default is False
        actions: bool
            Download dividend + stock splits data. Default is False
        threads: int
            Deprecated
    """

    # create ticker list
    tickers = tickers if isinstance(tickers, list) else tickers.split()
    tickers = [x.upper() for x in tickers]

    if progress:
        _PROGRESS_BAR = _ProgressBar(len(tickers), 'downloaded')

    _DFS = {}
    for ticker in tickers:
        data = Ticker(ticker).history(period=period, interval=interval,
                                      start=start, end=end, prepost=prepost,
                                      actions=actions, auto_adjust=auto_adjust)
        _DFS[ticker] = data
        if progress:
            _PROGRESS_BAR.animate()

    if progress:
        _PROGRESS_BAR.completed()

    data = _pd.concat(_DFS.values(), axis=1, keys=_DFS.keys())
    if group_by == 'column':
        data.columns = data.columns.swaplevel(0, 1)
        data.sort_index(level=0, axis=1, inplace=True)

    if len(tickers) == 1:
        data = _DFS[tickers[0]]
    return data


class _ProgressBar:
    def __init__(self, iterations, text='completed'):
        self.text = text
        self.iterations = iterations
        self.prog_bar = '[]'
        self.fill_char = '*'
        self.width = 50
        self.__update_amount(0)
        self.elapsed = 1

    def completed(self):
        if self.elapsed > self.iterations:
            self.elapsed = self.iterations
        self.update_iteration(1)
        print('\r' + str(self), end='')
        _sys.stdout.flush()
        print()

    def animate(self, iteration=None):
        if iteration is None:
            self.elapsed += 1
            iteration = self.elapsed
        else:
            self.elapsed += iteration

        print('\r' + str(self), end='')
        _sys.stdout.flush()
        self.update_iteration()

    def update_iteration(self, val=None):
        val = val if val is not None else self.elapsed / float(self.iterations)
        self.__update_amount(val * 100.0)
        self.prog_bar += '  %s of %s %s' % (
            self.elapsed, self.iterations, self.text)

    def __update_amount(self, new_amount):
        percent_done = int(round((new_amount / 100.0) * 100.0))
        all_full = self.width - 2
        num_hashes = int(round((percent_done / 100.0) * all_full))
        self.prog_bar = '[' + self.fill_char * \
            num_hashes + ' ' * (all_full - num_hashes) + ']'
        pct_place = (len(self.prog_bar) // 2) - len(str(percent_done))
        pct_string = '%d%%' % percent_done
        self.prog_bar = self.prog_bar[0:pct_place] + \
            (pct_string + self.prog_bar[pct_place + len(pct_string):])

    def __str__(self):
        return str(self.prog_bar)


# make pandas datareader optional
# otherwise can be called via fix_yahoo_finance.download(...)
def pdr_override():
    try:
        import pandas_datareader
        pandas_datareader.data.get_data_yahoo = download
        pandas_datareader.data.get_data_yahoo_actions = download
    except Exception:
        pass
