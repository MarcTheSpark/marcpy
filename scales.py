__author__ = 'mpevans'

import math

class Scale:
    def __init__(self, start_pitch, interval_series, repeat_interval):
        self.start_pitch = start_pitch
        self.interval_series = interval_series
        self.repeat_interval = repeat_interval

    def get_pitch_by_index(self, index):
        the_pitch = self.start_pitch
        octaves_up = int(index / len(self.interval_series))
        note_of_scale = index % len(self.interval_series)
        return the_pitch + self.repeat_interval * octaves_up + self.interval_series[note_of_scale]

    def round_pitch_to_scale(self, pitch):
        which_octave = math.floor((pitch - self.start_pitch) / self.repeat_interval)
        remainder = (pitch - self.start_pitch) % self.repeat_interval
        dist = None
        winning_interval = None
        for interval in self.interval_series + [self.repeat_interval]:
            if dist is None or abs(remainder - interval) < dist:
                dist = abs(remainder - interval)
                winning_interval = interval
        return self.start_pitch + which_octave * self.repeat_interval + winning_interval