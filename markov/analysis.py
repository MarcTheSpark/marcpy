__author__ = 'mpevans'

from marcpy.utilities import cyclic_slice

from pykov import *

class Datum:
    def __init__(self, value=None):
        self.value = value


class AnalysisSynthesisChain(Chain):

    def __init__(self, data, max_order=1.0, cyclic=True):
        super(AnalysisSynthesisChain, self).__init__()
        self.data = data
        self.state_quantities = {}
        for datum in data:
            if datum in self.state_quantities:
                self.state_quantities[datum] += 1.0
            else:
                self.state_quantities[datum] = 1.0
        print self.state_quantities
        self.max_order = max_order
        self.cyclic = cyclic
        self.train_the_chain()

    def move_zeroth_order(self):
        # returns a weighted selection from all the basic states
        r = random.random()
        for key, value in self.state_quantities.items():
            this_key_probability = value/len(self.data)
            if r < this_key_probability:
                return key
            else:
                r -= this_key_probability

    def get_next_values(self, num_values, order=None, start_values=None):
        if order is None:
            order = self.max_order
        if start_values is None:
            start_values = (self.move_zeroth_order(), )
        elif not hasattr(start_values, '__len__'):
            start_values = (start_values, )

        history = list(start_values)
        out = []

        if order <= 0:
            for i in range(num_values):
                out.append(self.move_zeroth_order())
        elif order == int(order):
            for i in range(num_values):
                if len(history) > order:
                    this_key = tuple(history[len(history)-order:])
                else:
                    this_key = tuple(history)

                next_state = self.move(this_key)
                history.append(next_state)
                out.append(next_state)
        else:
            # fractional order, so choose the higher or lower order with appropriate probability
            lower_order = int(order)
            higher_order = lower_order+1
            fractional_part = order - lower_order

            for i in range(num_values):
                this_step_order = higher_order if random.random() < fractional_part else lower_order
                if this_step_order <= 0:
                    next_state = self.move_zeroth_order()
                else:
                    if len(history) > this_step_order:
                        this_key = tuple(history[len(history)-this_step_order:])
                    else:
                        this_key = tuple(history)
                    next_state = self.move(this_key)
                history.append(next_state)
                out.append(next_state)

        return out

    def train_the_chain(self):
        order = int(math.ceil(self.max_order))

        if order >= len(self.data):
            order = len(self.data)

        for o in range(1, order+1):
            if self.cyclic:
                start_indices = range(len(self.data))
            else:
                start_indices = range(len(self.data) - o)

            for i in start_indices:
                this_key = (tuple(cyclic_slice(self.data, i, i+o)), self.data[(i+o) % len(self.data)])
                if this_key in self.keys():
                    self[this_key] += 1
                else:
                    self[this_key] = 1

        # this part is necessary to normalize the probabilities
        antecedent_total_prob_values = {}
        for (antecedent, consequent) in self:
            if antecedent in antecedent_total_prob_values:
                antecedent_total_prob_values[antecedent] += self[(antecedent, consequent)]
            else:
                antecedent_total_prob_values[antecedent] = float(self[(antecedent, consequent)])

        for (antecedent, consequent) in self:
            self[(antecedent, consequent)] = self[(antecedent, consequent)]/antecedent_total_prob_values[antecedent]

from music21 import converter
from music21.stream import *
from music21.note import *
from music21.chord import *
from music21.duration import *

score = converter.parse(get_relative_file_path('Turanga.mxl'))
insts = score.parts

score_pitch_timings = []
for inst in insts:
    for elem in inst.flat.elements:
        if isinstance(elem, Note):
            # put the note, its start time, and its end time into pitch_timings
            score_pitch_timings.append((elem, float(elem.offset), float(elem.offset) + elem.quarterLengthFloat))
        elif isinstance(elem, Chord):
            for note in elem:
                score_pitch_timings.append((note, float(elem.offset), float(elem.offset) + elem.quarterLengthFloat))

score_length = max([end_time for (note, start_time, end_time) in score_pitch_timings])
