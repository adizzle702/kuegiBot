from functools import reduce

from market_maker.indicator import Indicator, get_bar_value, highest, lowest, BarSeries
from market_maker.trade_engine import Bar

from typing import List
from collections import namedtuple


def clean_range(bars: List[Bar], offset: int, length: int):
    ranges = []
    for idx in range(offset, offset + length):
        if idx < len(bars):
            ranges.append(bars[idx].high - bars[idx].low)

    ranges.sort(reverse=True)

    # ignore the biggest 10% of ranges
    ignored_count = int(length / 5)
    sum = reduce(lambda x1, x2: x1 + x2, ranges[ignored_count:])
    return sum / (len(ranges) - ignored_count)


class Data:
    def __init__(self,sinceLongReset, sinceShortReset, longTrail, shortTrail, buffer, plotData=None):
        self.sinceLongReset = sinceLongReset
        self.sinceShortReset= sinceShortReset
        self.longTrail = longTrail
        self.shortTrail= shortTrail
        self.buffer= buffer
        self.plotData= plotData


class KuegiChannel(Indicator):
    def __init__(self, max_look_back: int = 15, threshold_factor: float = 0.9, buffer_factor: float = 0.05,
                 max_dist_factor: float = 2):
        super().__init__(
            'KuegiChannel(' + str(max_look_back) + ',' + str(threshold_factor) + ',' + str(buffer_factor) + ',' + str(
                max_dist_factor) + ')')
        self.max_look_back = max_look_back
        self.threshold_factor = threshold_factor
        self.buffer_factor = buffer_factor
        self.max_dist_factor = max_dist_factor

    def on_tick(self, bars: List[Bar]):
        # ignore first 5 bars
        for idx in range(len(bars) - self.max_look_back, -1, -1):
            if bars[idx].did_change:
                self.process_bar(bars[idx:])
                # we are plotting 1 in the future
                prevData:Data= self.get_data(bars[idx+1])
                data:Data= self.get_data(bars[idx])
                data.plotData= [prevData.longTrail,prevData.shortTrail] if prevData is not None else None

    def get_data_for_plot(self, bar: Bar):
        data: Data = self.get_data(bar)
        return data.plotData if data is not None and data.plotData is not None else [bar.close,bar.close]

    def process_bar(self, bars: List[Bar]):
        atr = clean_range(bars, offset=0, length=self.max_look_back * 2)

        offset = 1
        move_length = 1
        if (bars[offset].high - bars[offset].low) < (bars[offset + 1].high - bars[offset + 1].low):
            move_length = 2

        threshold = atr * self.threshold_factor

        maxDist = atr * self.max_dist_factor
        buffer = atr * self.buffer_factor

        [sinceLongReset, longTrail] = self.calc_trail(bars, offset, 1, move_length, threshold, maxDist)
        [sinceShortReset, shortTrail] = self.calc_trail(bars, offset, -1, move_length, threshold, maxDist)

        self.write_data(bars[0], Data(sinceLongReset, sinceShortReset, longTrail, shortTrail, buffer, None))

    def calc_trail(self, bars: List[Bar], offset, direction, move_length, threshold, maxDist):
        if direction > 0:
            range = highest(bars, 2, offset + move_length, BarSeries.HIGH)
            move = bars[offset].high - range
            last_value = bars[0].low
            offset_value = bars[offset].low
        else:
            range = lowest(bars, 2, offset + move_length, BarSeries.LOW)
            move = range - bars[offset].low
            last_value = bars[0].high
            offset_value = bars[offset].high

        last_data: Data = self.get_data(bars[1])
        if last_data is None:
            # defaults
            last_since_reset = 0
            last_buffer = 0
        else:
            last_buffer = last_data.buffer
            if direction > 0:
                last_since_reset = last_data.sinceLongReset
            else:
                last_since_reset = last_data.sinceShortReset

        if move > threshold and last_since_reset >= move_length and (offset_value - last_value) * direction < 0 and (
                range - last_value) * direction < 0:
            sinceReset = move_length + 1
        else:
            sinceReset = min(last_since_reset + 1, self.max_look_back)

        if direction > 0:
            trail = max(
                lowest(bars, sinceReset - 1, 0, BarSeries.LOW) - maxDist,
                lowest(bars, sinceReset, 0, BarSeries.LOW) - last_buffer)
        else:
            trail = min(
                highest(bars, sinceReset - 1, 0, BarSeries.HIGH) + maxDist,
                highest(bars, sinceReset, 0, BarSeries.HIGH) + last_buffer)

        return [sinceReset, trail]
