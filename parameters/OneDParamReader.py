__author__ = 'mpevans'

from marcpy import utilities

class OneDParamReader:

    def __init__(self, filepath):
        self.array_data, self.data_range, self.param_name = utilities.load_object(filepath)

    def get_array_value_at_percent(self, percent, power=1, cyclic=False):
        index = float(percent) * len(self.array_data)
        return utilities.get_interpolated_array_value(self.array_data, index, power=power, cyclic=cyclic)

    def get_interpolated_array_value(self, index, power=1, cyclic=False):
        return utilities.get_interpolated_array_value(self.array_data, index, power=power, cyclic=cyclic)

    def get_name(self):
        return self.param_name

    def get_range(self):
        return self.data_range