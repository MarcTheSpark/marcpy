__author__ = 'mpevans'

from fractions import Fraction

from marcpy import utilities, barlicity


class MPNote:
    def __init__(self, start_time, length, pitch, volume, variant=None, tie=None, notations=None, articulations=None):
        self.start_time = start_time
        self.length = length
        self.pitch = pitch
        self.volume = volume
        self.variant = variant
        self.tie = tie
        self.time_modification = None
        self.notations = [] if notations is None else notations
        self.articulations = [] if articulations is None else articulations
        self.length_without_tuplet = None

    def __repr__(self):
        return "MPNote(start_time={}, length={}, pitch={}, volume={}, variant={}, tie={}, time_modification={}, " \
               "notations={}, articulations={})".format(
            self.start_time, self.length, self.pitch, self.volume, self.variant, self.tie,
            self.time_modification, self.notations, self.articulations
        )

    @staticmethod
    def length_to_undotted_constituents(length):
        length = round(length, 6)
        length_parts = []
        while length > 0:
            this_part = utilities.floor_x_to_pow_of_y(length, 2.0)
            length -= this_part
            length_parts.append(this_part)
        return length_parts


class BeatQuantizationScheme:

    def __init__(self, tempo, beat_length, max_divisions=8, max_indigestibility=4, quantization_divisions=None,
                 simplicity_preference=1.0):
        """

        :param tempo: In quarter-notes per minute
        :param beat_length: In quarter-notes
        :param max_divisions: For generating preferred divisions automatically, the biggest divisor allowed.
        :param max_indigestibility: For generating preferred divisions automatically, the biggest divisor
        indigestibility allowed.
        :param quantization_divisions: Use this to set the quantization divisions manually. Either a 1D list or
        tuple, or a nx2 list/tuple consisting of (divisor, divisor undesirability) as elements. If 1D, the
        undesirabilities are generated automatically.
        :param simplicity_preference: ranges 0 - whatever. A simplicity_preference of 0 means, all divisions are
        treated equally; a 7 is as good as a 4. A simplicity_preference of 1 means that the most desirable division
        is left along, the most undesirable division gets its error doubled, and all other divisions are somewhere in
        between. Simplicity preference can be greater than 1.
        """
        self.tempo = tempo
        self.beat_length = float(beat_length)

        # now we populate a self.quantization_divisions with tuples consisting of the allowed divisions and
        # their undesirabilities. Undesirability is a factor by which the error in a given quantization option
        # is multiplied; the lowest possible undesirability is 1
        if quantization_divisions is None:
            # what we care about is how well the given division works within the most natural division of the beat_length
            # so first notate the beat_length as a fraction; its numerator is its most natural division
            beat_length_fraction = Fraction(self.beat_length).limit_denominator()

            quantization_divisions = []
            div_indigestibilities = []
            for div in range(2, max_divisions + 1):
                relative_division = Fraction(div, beat_length_fraction.numerator)
                div_indigestibility = barlicity.indigestibility(relative_division.numerator) + \
                    barlicity.indigestibility(relative_division.denominator)
                if div_indigestibility < max_indigestibility:
                    quantization_divisions.append(div)
                    div_indigestibilities.append(div_indigestibility)
            div_indigestibility_range = min(div_indigestibilities), max(div_indigestibilities)
            div_undesirabilities = [1 + simplicity_preference * (float(di) - div_indigestibility_range[0]) /
                                    (div_indigestibility_range[1] - div_indigestibility_range[0])
                                    for di in div_indigestibilities]
            self.quantization_divisions = zip(quantization_divisions, div_undesirabilities)
        else:
            if isinstance(quantization_divisions[0], tuple):
                # already (divisor, undesirability) tuples
                self.quantization_divisions = quantization_divisions
            else:
                # we've just been given the divisors, and have to figure out the undesirabilities
                beat_length_fraction = Fraction(self.beat_length).limit_denominator()
                div_indigestibilities = []
                for div in quantization_divisions:
                    relative_division = Fraction(div, beat_length_fraction.numerator)
                    div_indigestibility = barlicity.indigestibility(relative_division.numerator) + \
                        barlicity.indigestibility(relative_division.denominator)
                    div_indigestibilities.append(div_indigestibility)
                div_indigestibility_range = min(div_indigestibilities), max(div_indigestibilities)
                div_undesirabilities = [1 + simplicity_preference * (float(di) - div_indigestibility_range[0]) /
                                        (div_indigestibility_range[1] - div_indigestibility_range[0])
                                        for di in div_indigestibilities]
                self.quantization_divisions = zip(quantization_divisions, div_undesirabilities)

        # when used to quantize something, this gets set
        self.start_time = 0

    def __str__(self):
        return "BeatQuantizationScheme [tempo=" + str(self.tempo) + ", beat_length=" + str(self.beat_length) + \
               ", quantization_divisions=" + str(self.quantization_divisions) + "]"


class MeasureScheme:

    def __init__(self, time_signature, beat_quantization_schemes):
        # time_signature is either a tuple, e.g. (3, 4), or a string, e.g. "3/4"
        self.string_time_signature, self.tuple_time_signature = MeasureScheme.time_sig_to_string_and_tuple(time_signature)
        # in quarter notes
        self.measure_length = self.tuple_time_signature[0]*4/float(self.tuple_time_signature[1])

        # either we give a list of beat_quantization schemes or a single beat quantization scheme to use for all beats
        if hasattr(beat_quantization_schemes, "__len__"):
            total_length = 0
            for beat_quantization_scheme in beat_quantization_schemes:
                assert isinstance(beat_quantization_scheme, BeatQuantizationScheme)
                total_length += beat_quantization_scheme.beat_length
            assert total_length == self.measure_length
            self.beat_quantization_schemes = beat_quantization_schemes
        else:
            assert isinstance(beat_quantization_schemes, BeatQuantizationScheme)
            assert utilities.is_multiple(self.measure_length, beat_quantization_schemes.beat_length)
            self.beat_quantization_schemes = [beat_quantization_schemes] * \
                int(round(self.measure_length / beat_quantization_schemes.beat_length))

        self.length = sum([beat_scheme.beat_length for beat_scheme in self.beat_quantization_schemes])
        
        # when used to quantize something, this gets set
        self.start_time = 0

    @staticmethod
    def time_sig_to_string_and_tuple(time_signature):
        if isinstance(time_signature, str):
            string_time_signature = time_signature
            tuple_time_signature = tuple([int(x) for x in time_signature.split("/")])
        else:
            tuple_time_signature = tuple(time_signature)
            string_time_signature = str(time_signature[0]) + "/" + str(time_signature[1])
        return string_time_signature, tuple_time_signature

    @classmethod
    def from_time_signature(cls, time_signature, tempo, max_divisions=8, max_indigestibility=4, simplicity_preference=0.2):
        # it would be good to be able to handle ((2, 3, 2), 8) or "2+3+2/8"
        _, tuple_time_signature = MeasureScheme.time_sig_to_string_and_tuple(time_signature)
        measure_length = tuple_time_signature[0] * 4.0 / tuple_time_signature[1]
        assert utilities.is_x_pow_of_y(tuple_time_signature[1], 2)
        if tuple_time_signature[1] <= 4:
            beat_length = 4.0 / tuple_time_signature[1]
            num_beats = int(round(measure_length/beat_length))
            beat_quantization_schemes = [BeatQuantizationScheme(tempo, beat_length, max_divisions=max_divisions,
                                                                max_indigestibility=max_indigestibility,
                                                                simplicity_preference=simplicity_preference)] * num_beats
        else:
            # we're dealing with a denominator of 8, 16, etc., so either we have a compound meter, or an uneven meter
            if utilities.is_multiple(tuple_time_signature[0], 3):
                beat_length = 4.0 / tuple_time_signature[1] * 3
                num_beats = int(round(measure_length/beat_length))
                beat_quantization_schemes = [BeatQuantizationScheme(tempo, beat_length, max_divisions=max_divisions,
                                                                    max_indigestibility=max_indigestibility,
                                                                    simplicity_preference=simplicity_preference)] * num_beats
            else:
                duple_beat_length = 4.0 / tuple_time_signature[1] * 2
                triple_beat_length = 4.0 / tuple_time_signature[1] * 3
                if utilities.is_multiple(tuple_time_signature[0], 2):
                    num_duple_beats = int(round(measure_length/duple_beat_length))
                    num_triple_beats = 0
                else:
                    num_duple_beats = int(round((measure_length-triple_beat_length)/duple_beat_length))
                    num_triple_beats = 1
                beat_quantization_schemes = [BeatQuantizationScheme(tempo, duple_beat_length, max_divisions=max_divisions,
                                                                    max_indigestibility=max_indigestibility,
                                                                    simplicity_preference=simplicity_preference)] * num_duple_beats + \
                                            [BeatQuantizationScheme(tempo, triple_beat_length, max_divisions=max_divisions,
                                                                    max_indigestibility=max_indigestibility,
                                                                    simplicity_preference=simplicity_preference)] * num_triple_beats
        return cls(time_signature, beat_quantization_schemes)