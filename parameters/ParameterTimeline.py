__author__ = 'mpevans'

import time
import bisect


class ParameterTimeLine:

    def __init__(self, param_name=None):
        self.param_name = param_name
        self.data = {}
        self.sorted_data = None
        self.time_entries = None
        self.recording_start_time = None
        self.times = set()

    def start_recording_data(self, start_value):
        self.data[0.0] = start_value
        self.recording_start_time = time.time()

    def log_value(self, value, t=None):
        if t is None:
            assert self.recording_start_time is not None
            t = time.time() - self.recording_start_time
        self.data[float(t)] = value
        self.sorted_data = None
        self.time_entries = None

    def sort_data(self):
        if len(self.data) == 0:
            self.sorted_data = None
            self.time_entries = None
        else:
            self.sorted_data = [(t, self.data[t]) for t in self.data]
            self.sorted_data.sort(key=lambda x: x[0])
            self.time_entries = self.data.keys()
            self.time_entries.sort()

    def get_value_at_time(self, t, interpolation_power=1):
        """
        interpolation_power of negative 1 (or less than zero) means no interpolation
        :type interpolation_power: float
        """
        if len(self.data) == 0:
            return None
        else:
            if self.sorted_data is None:
                self.sort_data()
            bisect_index = bisect.bisect_left(self.time_entries, t)
            if bisect_index == 0:
                # at or below lowest time value
                return self.sorted_data[0][1]
            elif bisect_index == len(self.sorted_data):
                # above highest time value
                return self.sorted_data[-1][1]
            elif t == self.time_entries[bisect_index]:
                # exactly at a time value
                return self.sorted_data[bisect_index][1]
            elif interpolation_power < 0:
                return self.sorted_data[bisect_index-1][1]
            elif interpolation_power == 0:
                return self.sorted_data[bisect_index][1]
            else:
                # in between two time values
                lower_value = self.sorted_data[bisect_index-1][1]
                upper_value = self.sorted_data[bisect_index][1]
                partial_progress = (t - self.sorted_data[bisect_index-1][0]) / \
                                   (self.sorted_data[bisect_index][0] - self.sorted_data[bisect_index-1][0])
                return (1 - partial_progress**interpolation_power) * lower_value + \
                    partial_progress**interpolation_power * upper_value