__author__ = 'mpevans'

import os
import sys
import pickle
import inspect
import math
import numpy as np
import bisect
import copy

def enum(**named_values):
    return type('Enum', (), named_values)


# decorator that saves function output
def save_answers(func):
    func.answers = {}

    def func_wrapper(*args):
        t_args = tuple(args)
        if t_args in func.answers:
            return func.answers[t_args]
        else:
            ans = func(*args)
            func.answers[t_args] = ans
            return ans

    return func_wrapper


# determines if application is a script file or frozen exe
def get_relative_file_path(file_name):
    if getattr(sys, 'frozen', False):
        application_path = os.path.join(os.path.dirname(sys.executable), "..")
    else:
        frm = inspect.stack()[1]
        mod = inspect.getmodule(frm[0])
        application_path = os.path.dirname(mod.__file__)

    return os.path.join(application_path, file_name)


def save_object(obj, filename):
    with open(filename, 'wb') as output:
        pickle.dump(copy.deepcopy(obj), output, pickle.HIGHEST_PROTOCOL)


def load_object(filename):
    out = None
    with open(filename, 'rb') as input_:
        out = pickle.load(input_)
    return out


pc_number_to_name = {
    0: "C",
    1: "C#/Db",
    2: "D",
    3: "D#/Eb",
    4: "E",
    5: "F",
    6: "F#/Gb",
    7: "G",
    8: "G#/Ab",
    9: "A",
    10: "A#/Bb",
    11: "B"
}


def get_pitch_description(pitch, accidental_type="standard"):
    pitch = round(pitch)
    octave = int(pitch/12) - 1
    pc_name = pc_number_to_name[pitch % 12]
    if "/" in pc_name and accidental_type != "both":
        # unless accidental type is "both", we need to pick sharp or flat
        # let's have the standard choice be C#, Eb, F#, Ab, Bb
        if accidental_type == "standard":
            accidental_type = "flat" if pitch % 12 in (3, 8, 10) else "sharp"
        # though by setting accidental_type to "flat" or "sharp", the user can choose
        if accidental_type.lower() == "flat":
            pc_name = pc_name.split("/")[1]
        elif accidental_type.lower() == "sharp":
            pc_name = pc_name.split("/")[0]

    return pc_name + str(octave)


def get_pitch_class_description(pitch_class, accidental_type="standard"):
    pc_name = pc_number_to_name[pitch_class]
    if "/" in pc_name and accidental_type != "both":
        # unless accidental type is "both", we need to pick sharp or flat
        # let's have the standard choice be C#, Eb, F#, Ab, Bb
        if accidental_type == "standard":
            accidental_type = "flat" if pitch_class in (3, 8, 10) else "sharp"
        # though by setting accidental_type to "flat" or "sharp", the user can choose
        if accidental_type.lower() == "flat":
            pc_name = pc_name.split("/")[1]
        elif accidental_type.lower() == "sharp":
            pc_name = pc_name.split("/")[0]

    return pc_name


def get_interval_cycle_length(cycle_size):
    x = cycle_size
    length = 1
    while x % 12 != 0:
        x += cycle_size
        length += 1
    return length


def get_interval_cycle_distance(pc1, pc2, cycle_size):
    cycle_length = get_interval_cycle_length(cycle_size)
    distance = 0
    while (pc1 - pc2) % 12 != 0:
        pc2 += cycle_size
        distance += 1
        if distance > cycle_length:
            return - 1
    if distance > cycle_length/2:
        return cycle_length-distance
    return distance

# took this disgustingly unreadable function from somewhere
ordinal = lambda n: "%d%s" % (n,"tsnrhtdd"[(int(n/10)%10!=1)*(n%10<4)*n%10::4])


def is_x_pow_of_y(x, y):
    a = math.log(x, y)
    if a == int(a):
        return True
    else:
        return False


def floor_x_to_pow_of_y(x, y):
    a = math.log(x, y)
    return y ** math.floor(a)


def round_x_to_pow_of_y(x, y):
    a = math.log(x, y)
    return y ** (int(round(a)) if isinstance(y, int) else round(a))


def midi_to_freq(midi_val):
    return 440.0 * 2**((midi_val - 69.0)/12)


def freq_to_midi(frequency):
    return math.log(frequency/440.0, 2.0) * 12 + 69.0


def cents_to_ratio(cents):
    return 2**(cents/1200.0)


def ratio_to_cents(ratio):
    return math.log(ratio)/math.log(2) * 1200.0


def round_to_multiple(x, factor):
    return round(x/factor)*factor


def is_multiple(x, y):
    return round_to_multiple(x, y) == x


def get_bracketed_text(string, start_bracket, end_bracket):
    out = []
    next_start_bracket = string.find(start_bracket)
    while next_start_bracket != -1:
        string = string[next_start_bracket+len(start_bracket):]
        next_end_bracket = string.find(end_bracket)
        if next_end_bracket == -1:
            break
        else:
            out.append(string[:next_end_bracket])
            string = string[next_end_bracket:]
        next_start_bracket = string.find(start_bracket)
    return out

# Color stuff

def get_luminance(r, g, b):
    return 0.2126 * r + 0.7152 * g + 0.0722 * g

# Geometric shit

def get_projection_and_rejection_of_a_onto_b(a, b):
    assert isinstance(a, np.ndarray) and a.ndim == 1
    assert isinstance(b, np.ndarray) and a.ndim == 1
    projection = np.dot(a, b) * b / np.linalg.norm(b)**2
    rejection = a-projection
    return projection, rejection

def get_projection_a_onto_b(a, b):
    assert isinstance(a, np.ndarray) and a.ndim == 1
    assert isinstance(b, np.ndarray) and a.ndim == 1
    return np.dot(a, b) * b / np.linalg.norm(b)**2

def get_rejection_of_a_onto_b(a, b):
    assert isinstance(a, np.ndarray) and a.ndim == 1
    assert isinstance(b, np.ndarray) and a.ndim == 1
    return a - np.dot(a, b) * b / np.linalg.norm(b)**2

# --------------------- list stuff ---------------------------


def make_flat_list(l, indivisible_type=None):
    # indivisible_type is a type that we don't want to divide,
    new_list = list(l)
    i = 0
    while i < len(new_list):
        if hasattr(new_list[i], "__len__"):
            if indivisible_type is None or not isinstance(new_list[i], indivisible_type):
                new_list = new_list[:i] + new_list[i] + new_list[i+1:]
        else:
            i += 1
    return new_list


def get_interpolated_array_value(array, index, power=1, cyclic=False, normalized=False):
    if normalized:
        index *= len(array)
        index = round(index, 10)
    # some special cases
    if index < 0:
        if cyclic:
            index = index % len(array)
        else:
            return array[0]
    elif index >= len(array)-1:
        if cyclic:
            index = index % len(array)
        else:
            return  array[-1]
    elif index == int(index):
        return array[int(index)]

    lower_index_value = array[int(index)]
    upper_index_value = array[(int(index)+1) % len(array)]
    progress_to_next = (index - int(index))**power
    return lower_index_value * (1 - progress_to_next) + upper_index_value * progress_to_next


def get_closest_index(myList, value):
    """
    Assumes myList is sorted. Returns closest value to myNumber.

    If two numbers are equally close, return the index of the smallest number.
    """
    pos = bisect.bisect_left(myList, value)
    if pos == 0:
        return 0
    if pos == len(myList):
        return len(myList) - 1
    before = myList[pos - 1]
    after = myList[pos]
    if after - value < value - before:
       return pos
    else:
       return pos - 1


def cyclic_slice(l, start, end):
    # m
    """
    takes a slice that loops back to the beginning if end is before start
    :param l(list): the list to slice
    :param start(int): start index
    :param end(int): end index
    :return: list
    """

    if end >= start:
        # start by making both indices positive, since that's easier to handle
        while start < 0 or end < 0:
            start += len(l)
            end += len(l)
        if end >= start + len(l):
            out = []
            while end - start >= len(l):
                out.extend(l[start:] + l[:start])
                end -= len(l)
            out += cyclic_slice(l, start, end)
            return out
        else:
            end = end % len(l)
            start = start % len(l)
            if end >= start:
                return l[start:end]
            else:
                return l[start:] + l[:end]
    else:
        # if the end is before the beginning, we do a backwards slice
        # basically this means we reverse the list, and recalculate the start and end
        new_start = len(l)-start-1
        new_end = len(l)-end-1
        new_list = list(l)
        new_list.reverse()
        return cyclic_slice(new_list, new_start, new_end)


class CyclingTuple:
    def __init__(self, *tuples_that_cycle):
        self.tuples = tuples_that_cycle
        self.num_versions = len(tuples_that_cycle)
        self.current_version = 0

    def __getitem__(self, item):
        out = self.tuples[self.current_version][item]
        return out

    def __getslice__(self, i, j):
        out = self.tuples[self.current_version][i: j]
        return out

    def __len__(self):
        return len(self.tuples)

    def next_cycle(self):
        self.current_version = (self.current_version + 1) % self.num_versions