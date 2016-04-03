__author__ = 'mpevans'

import bisect


class DiscreteSequence:

    def __init__(self, param_name=None, default_value=None):
        self.param_name = param_name
        self.data = {}
        self.sorted_data = None
        self.time_entries = None
        self.recording_start_time = None
        self.times = set()
        self.default_value = default_value

    def start_recording_data(self, start_value=None):
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
        if self.sorted_data is None:
            if len(self.data) == 0:
                self.sorted_data = None
                self.time_entries = None
            else:
                self.sorted_data = [(t, self.data[t]) for t in self.data]
                self.sorted_data.sort(key=lambda x: x[0])
                self.time_entries = self.data.keys()
                self.time_entries.sort()

    def get_first_entry_time(self):
        if len(self.data) == 0:
            return None
        else:
            self.sort_data()
            return self.time_entries[0]

    def get_last_entry_time(self):
        if len(self.data) == 0:
            return None
        else:
            self.sort_data()
            return self.time_entries[-1]

    def __len__(self):
        return len(self.data)

    def get_value_at_time(self, t):
        """
        interpolation_power of negative 1 (or less than zero) means no interpolation
        :type interpolation_power: float
        """
        if len(self.data) == 0:
            return self.default_value
        else:
            self.sort_data()
            bisect_index = bisect.bisect_right(self.time_entries, t)
            if bisect_index == 0:
                return self.default_value
            else:
                return self.sorted_data[bisect_index-1][1]
