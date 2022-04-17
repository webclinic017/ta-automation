from abc import ABC, abstractmethod
import yfinance as yf
from datetime import datetime
from pandas import DataFrame as df
import btalib
from datetime import timedelta, datetime
from dateutil.relativedelta import relativedelta


class IFeeder(ABC):
    @abstractmethod
    def __init__(self):
        ...


class YFinanceFeeder:
    def get_bars(
        self, symbol: str, start: datetime, end: datetime = None, interval: str = "1d"
    ):
        intervals = [
            "1m",
            "2m",
            "5m",
            "15m",
            "30m",
            "60m",
            "90m",
            "1h",
            "1d",
            "5d",
            "1wk",
            "1mo",
            "3mo",
        ]
        if interval not in intervals:
            raise ValueError(
                f"Interval was {str(interval)} but must be one of {str(intervals)}"
            )

        if end == None:
            end = datetime.now().astimezone()

        #### datetime.now().astimezone()

        # start = datetime.fromisoformat(start)
        # end = datetime.fromisoformat(end)

        return yf.Ticker(symbol).history(
            start=start, end=end, interval=interval, actions=False
        )


class MockerException(Exception):
    ...


class Mocker:
    symbol: str
    start: datetime
    end: datetime
    current: datetime
    interval: str
    initialised: bool = False
    bars: df

    def __init__(
        self,
        data_source,
        real_end: datetime = None,
    ):
        if real_end == None:
            self.read_end = datetime.now().astimezone()
        else:
            self.real_end = real_end.astimezone()

        self.data_source = data_source

    def get_bars(
        self, symbol: str, start: str, end: str, interval: str = "1d", do_macd=False
    ):
        # yf/pandas will drop time and timezone if interval is greater than 24 hours
        if not self.initialised:
            self.bars = self.data_source.get_bars(
                symbol=symbol, start=start, end=self.real_end, interval=interval
            )

            self.symbol = symbol
            self.start = start
            self.current = end
            self.interval = interval
            self.initialised = True

            self.bars = self.bars.tz_localize(None)

            interval_delta, max_range, tick = self.get_interval_settings(
                interval=interval
            )

            if do_macd:
                # do it
                macd = btalib.macd(self.bars)
                self.bars["macd_macd"] = macd["macd"]
                self.bars["macd_signal"] = macd["signal"]
                self.bars["macd_histogram"] = macd["histogram"]
                self.bars["macd_crossover"] = False
                self.bars["macd_signal_crossover"] = False
                self.bars["macd_above_signal"] = False
                self.bars["macd_cycle"] = None

                # loops looking for three things - macd-signal crossover, signal-macd crossover, and whether macd is above signal
                cycle = None

                for d in self.bars.index:
                    # start with crossover search
                    # convert index to a datetime so we can do a delta against it                           ****************
                    previous_key = d - interval_delta
                    # previous key had macd less than or equal to signal
                    if self.bars["macd_macd"].loc[d] > self.bars["macd_signal"].loc[d]:
                        # macd is greater than signal - crossover
                        self.bars.at[d, "macd_above_signal"] = True
                        try:
                            if (
                                self.bars["macd_macd"].loc[previous_key]
                                <= self.bars["macd_signal"].loc[previous_key]
                            ):
                                cycle = "blue"
                                self.bars.at[d, "macd_crossover"] = True

                        except KeyError as e:
                            # ellipsis because i don't care if i'm missing data (maybe i should...)
                            ...

                    if self.bars["macd_macd"].loc[d] < self.bars["macd_signal"].loc[d]:
                        # macd is less than signal
                        try:
                            if (
                                self.bars["macd_macd"].loc[previous_key]
                                >= self.bars["macd_signal"].loc[previous_key]
                            ):
                                cycle = "red"
                                self.bars.at[d, "macd_signal_crossover"] = True

                        except KeyError as e:
                            # ellipsis because i don't care if i'm missing data (maybe i should...)
                            ...

                    self.bars.at[d, "macd_cycle"] = cycle

                if self.symbol != symbol or self.start != start or self.interval != interval:
                    raise MockerException(
                        "Can't change symbol, start or interval once instantiated!"
                    )

        #
        #       this logic wouldn't even work anyway since there is a months symbol....
        #        if len(end) > 10 and "m" not in interval:
        #            raise ValueError(
        #                f"Interval must be <24 hours when specifying a real_end that contains time and timezone. Found {interval} interval and {end} date/time"
        #            )
        #        elif len(end) < 25 and "m" in interval:
        #            raise ValueError(
        #                f"When interval is set to minutes, date/time must be specified similar to 2022-03-30T00:00:00+10:00. Found {end}"
        #            )
        self.last_end = end

        return self.bars.loc[:end]

    def get_next(self):
        try:
            return self.bars.loc[self.bars.index > self.last_end].index[0]
        except:
            return False

    def get_interval_settings(self, interval):
        minutes_intervals = ["1m", "2m", "5m", "15m", "30m", "60m", "90m"]
        max_period = {
            "1m": 7,
            "2m": 60,
            "5m": 60,
            "15m": 60,
            "30m": 60,
            "60m": 500,
            "90m": 60,
            "1h": 500,
            "1d": 2000,
            "5d": 500,
            "1wk": 500,
            "1mo": 500,
            "3mo": 500,
        }

        if interval in minutes_intervals:
            return (
                relativedelta(minutes=int(interval[:-1])),
                max_period[interval],
                timedelta(minutes=int(interval[:-1])),
            )
        elif interval == "1h":
            return (
                relativedelta(hours=int(interval[:-1])),
                max_period[interval],
                timedelta(hours=int(interval[:-1])),
            )
        elif interval == "1d" or interval == "5d":
            return (
                relativedelta(days=int(interval[:-1])),
                max_period[interval],
                timedelta(days=int(interval[:-1])),
            )
        elif interval == "1wk":
            return (
                relativedelta(weeks=int(interval[:-2])),
                max_period[interval],
                timedelta(weeks=int(interval[:-2])),
            )
        elif interval == "1mo" or interval == "3mo":
            raise ValueError("I can't be bothered implementing month intervals")
            return (
                relativedelta(months=int(interval[:-2])),
                max_period[interval],
                timedelta(months=int(interval[:-1])),
            )
        else:
            # got an unknown interval
            raise ValueError(f"Unknown interval type {interval}")


# self.bars.index
# self.bars.keys
# self.bars["column"]
