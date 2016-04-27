__author__ = 'mpevans'

from MusicXMLExporter import *
from MeasuresBeatsNotes import *
from marcpy.usefulimports.interval import IntervalSet
from copy import deepcopy
from collections import defaultdict

# how various notations split when we divide a note up
how_they_split = defaultdict(lambda: "all", {
    "Tuplet(start)": "first",
    "Tuplet(end)": "end"
})


def save_to_xml_file(recorded_parts, part_names, file_name, measure_schemes=None, time_signature="4/4", tempo=60, max_divisions=8,
                     max_indigestibility=4, simplicity_preference=0.2, title=None, composer=None):

    print "Saving Output..."

    # get measure schemes from time signature if not supplied
    if measure_schemes is None:
        measure_schemes = [MeasureScheme.from_time_signature(time_signature, tempo, max_divisions=max_divisions,
                                                             max_indigestibility=max_indigestibility,
                                                             simplicity_preference=simplicity_preference)]

    # make a list of the beat schemes (up to repeating the last one)
    beat_schemes = []
    for ms in measure_schemes:
        beat_schemes.extend(ms.beat_quantization_schemes)

    # now that we have all the tempo info from the beat schemes, let's figure out the length in quarters
    total_quarters_length = _get_recording_quarters_length(recorded_parts, beat_schemes)

    # keep repeating the last measure_scheme until we get to the end of the recording
    total_measure_schemes_length = sum(ms.length for ms in measure_schemes)
    while total_measure_schemes_length < total_quarters_length:
        measure_schemes.append(deepcopy(measure_schemes[-1]))
        beat_schemes.extend(measure_schemes[-1].beat_quantization_schemes)
        total_measure_schemes_length += measure_schemes[-1].length

    # set the start_times of all the measure and beat schemes
    current_time = 0
    for measure_scheme in measure_schemes:
        measure_scheme.start_time = current_time
        for beat_scheme in measure_scheme.beat_quantization_schemes:
            beat_scheme.start_time = current_time
            current_time += beat_scheme.beat_length

    xml_score = Score(title, composer)
    for which_part, (part_recording, part_name) in enumerate(zip(recorded_parts, part_names)):
        print "Working on Part " + str(which_part+1) + "..."

        # make the music21 part object, and add the instrument
        xml_part = Part(part_name)

        # quantize the recording, also noting the beat divisors
        quantized_recording, beat_divisors = _quantize_recording(part_recording, beat_schemes)

        # merge notes into chords
        quantized_recording = _collapse_recording_chords(quantized_recording)
        # separate it into non-overlapping voices
        quantized_separated_voices = _separate_into_non_overlapping_voices(quantized_recording, 0.001)
        # clean up pc_voices: add rests, break into ties, etc.
        clean_pc_voices = [_raw_voice_to_pretty_looking_voice(v, beat_schemes)
                           for v in quantized_separated_voices]

        for v in clean_pc_voices:
            # this method modifies in place
            _set_tuplets_for_notes_in_voice(v, beat_schemes, beat_divisors)
            _break_notes_into_undotted_constituents(v, beat_schemes)

        # create xml measure objects with time signatures and add to the part
        last_time_signature = None
        last_tempo = None
        measure_num = 1
        for measure_scheme in measure_schemes:
            measure_start, measure_time_signature = measure_scheme.start_time, measure_scheme.tuple_time_signature
            measure_end = measure_scheme.end_time

            # make a xml measure with the appropriate time signature
            clef = "treble" if measure_num == 1 else None
            time_signature = measure_time_signature if measure_time_signature != last_time_signature else None
            xml_measure = Measure(number=measure_num, clef=clef, time_signature=time_signature)
            last_time_signature = measure_time_signature

            # add the measure to the part, and increment measure_num
            xml_part.append(xml_measure)
            measure_num += 1

            # add any metronome marks we need based on beat tempos
            offset = 0
            for beat_scheme in measure_scheme.beat_quantization_schemes:
                if beat_scheme.tempo != last_tempo:
                    xml_measure.append(MetronomeMark("quarter", beat_scheme.tempo, offset=offset))
                    last_tempo = beat_scheme.tempo
                offset += beat_scheme.beat_length

            # now we add the notes to the measure
            # first group notes into the voices in the measure
            voices_in_measure = []
            for voice in clean_pc_voices:
                voice_in_measure = [pc_note for pc_note in voice
                                    if measure_start <= pc_note.start_time < measure_end]
                # make sure one of them is not a rest
                if len([n for n in voice_in_measure if n.pitch is not None]) > 0:
                    voices_in_measure.append(voice_in_measure)

            # populate the xml measure object with xml notes
            if len(voices_in_measure) == 0:
                # if the measure's empty, add a bar rest
                xml_measure.append(Note.bar_rest(measure_end - measure_start))
            else:
                # otherwise go through each voice present in the measure
                for which_voice, voice_in_measure in enumerate(voices_in_measure):
                    # each note in each voice
                    for pc_note in voice_in_measure:
                        assert isinstance(pc_note, MPNote)

                        # and each length component in each note
                        for component_num, length_component in enumerate(pc_note.length_without_tuplet):
                            if component_num == 0 and component_num == len(pc_note.length_without_tuplet) - 1:
                                # only one component, so tie type is just whatever the pc_note is
                                ties = pc_note.tie
                                component_notations = pc_note.notations
                                component_articulations = pc_note.notations
                            elif component_num == 0:
                                # multiple components, of which this is the first
                                ties = "continue" if pc_note.tie == "end" or pc_note.tie == "continue" else "start"
                                component_notations = [n for n in pc_note.notations if
                                                       how_they_split[str(n)] in "start or all"]
                                component_articulations = [a for a in pc_note.articulations if
                                                           how_they_split[str(a)] in "start or all"]
                            elif component_num == len(pc_note.length_without_tuplet) - 1:
                                # multiple components, of which this is the last
                                ties = "continue" if pc_note.tie == "start" or pc_note.tie == "continue" else "end"
                                component_notations = [n for n in pc_note.notations if
                                                       how_they_split[str(n)] in "end or all"]
                                component_articulations = [a for a in pc_note.articulations if
                                                           how_they_split[str(a)] in "end or all"]
                            else:
                                ties = "continue"
                                component_notations = [n for n in pc_note.notations if
                                                       how_they_split[str(n)] == "all"]
                                component_articulations = [a for a in pc_note.articulations if
                                                           how_they_split[str(a)] == "all"]

                            xml_measure.append(Note(
                                None if pc_note.pitch is None else Pitch(pc_note.pitch),
                                duration=Duration(length_component, pc_note.time_modification),
                                voice=which_voice+1, notations=component_notations, articulations=component_articulations,
                                ties=ties)
                            )
        xml_score.add_part(xml_part)
    xml_score.save_to_file(file_name)

# [ ---------- Utilities -----------]


def _get_recording_quarters_length(recorded_parts, beat_schemes):
    # returns the length in seconds, and then the length in quarters, taking into account the tempos of the beats
    length = max([max([pc_note.start_time + pc_note.length for pc_note in part])
                  for part in recorded_parts])
    quarter_length = 0
    current_beat = 0
    while length > 0:
        current_beat_scheme = beat_schemes[current_beat]
        assert isinstance(current_beat_scheme, BeatQuantizationScheme)
        beat_length_in_seconds = current_beat_scheme.beat_length * 60.0 / current_beat_scheme.tempo
        quarter_length += current_beat_scheme.beat_length
        length -= beat_length_in_seconds
        if current_beat + 1 < len(beat_schemes):
            current_beat += 1
    return quarter_length

# [ ------- Part Processing ------- ]


def _quantize_recording(recording_in_seconds, beat_schemes, onset_termination_weighting=0.3):

    """

    :param recording_in_seconds: a voice consisting of MPNotes, with timings in seconds
    :param beat_schemes: a list of beat_schemes through which we iterate, which determine the quantization
    parameters. The last beat scheme is looped through till the end.
    :param onset_termination_weighting: 0 means we only care about onsets when determining the best quantization,
    and 1 means we only care about terminations. In between is a weighting.
    """
    # raw_onsets and raw_terminations are in seconds
    raw_onsets = [(pc_note.start_time, pc_note) for pc_note in recording_in_seconds]
    raw_terminations = [(pc_note.start_time + pc_note.length, pc_note) for pc_note in recording_in_seconds]
    raw_onsets.sort(key=lambda x: x[0])
    raw_terminations.sort(key=lambda x: x[0])

    pc_note_to_quantize_start_time = {}
    pc_note_to_quantize_end_time = {}
    current_beat_scheme = 0
    quarters_beat_start_time = 0.0
    seconds_beat_start_time = 0.0
    beat_divisors = []
    while len(raw_onsets) + len(raw_terminations) > 0:
        # move forward one beat at a time
        # get the beat scheme for this beat
        this_beat_scheme = beat_schemes[current_beat_scheme]
        assert isinstance(this_beat_scheme, BeatQuantizationScheme)
        current_beat_scheme += 1

        # get the beat length and end time in quarters and seconds
        quarters_beat_length = this_beat_scheme.beat_length
        seconds_beat_length = this_beat_scheme.beat_length * 60.0 / this_beat_scheme.tempo
        quarters_beat_end_time = quarters_beat_start_time + this_beat_scheme.beat_length
        seconds_beat_end_time = seconds_beat_start_time + seconds_beat_length

        # find the onsets in this beat
        onsets_to_quantize = []
        while len(raw_onsets) > 0 and raw_onsets[0][0] < seconds_beat_end_time:
            onsets_to_quantize.append(raw_onsets.pop(0))

        # find the terminations in this beat
        terminations_to_quantize = []
        while len(raw_terminations) > 0 and raw_terminations[0][0] < seconds_beat_end_time:
            terminations_to_quantize.append(raw_terminations.pop(0))

        if len(onsets_to_quantize) + len(terminations_to_quantize) == 0:
            # an empty beat, nothing to see here
            beat_divisors.append(None)
        else:
            # try out each quantization division
            best_divisor = None
            best_error = float("inf")
            for divisor, undesirability in this_beat_scheme.quantization_divisions:
                seconds_piece_length = seconds_beat_length / divisor
                total_squared_onset_error = 0
                for onset in onsets_to_quantize:
                    time_since_beat_start = onset[0] - seconds_beat_start_time
                    total_squared_onset_error += (time_since_beat_start - utilities.round_to_multiple(time_since_beat_start, seconds_piece_length)) ** 2
                total_squared_term_error = 0
                for term in terminations_to_quantize:
                    time_since_beat_start = term[0] - seconds_beat_start_time
                    total_squared_term_error += (time_since_beat_start - utilities.round_to_multiple(time_since_beat_start, seconds_piece_length)) ** 2
                this_div_error_score = undesirability * (onset_termination_weighting * total_squared_term_error +
                                                         (1 - onset_termination_weighting) * total_squared_onset_error)
                if this_div_error_score < best_error:
                    best_divisor = divisor
                    best_error = this_div_error_score

            best_piece_length_quarters = this_beat_scheme.beat_length / best_divisor
            best_piece_length_seconds = seconds_beat_length / best_divisor

            for onset, pc_note in onsets_to_quantize:
                pieces_past_beat_start = round((onset - seconds_beat_start_time) / best_piece_length_seconds)
                pc_note_to_quantize_start_time[pc_note] = quarters_beat_start_time + pieces_past_beat_start * best_piece_length_quarters
                # save this info for later, when we need to assure they all have the same Tuplet
                pc_note.start_time_divisor = best_divisor

            for termination, pc_note in terminations_to_quantize:
                pieces_past_beat_start = round((termination - seconds_beat_start_time) / best_piece_length_seconds)
                pc_note_to_quantize_end_time[pc_note] = quarters_beat_start_time + pieces_past_beat_start * best_piece_length_quarters
                if pc_note_to_quantize_end_time[pc_note] == pc_note_to_quantize_start_time[pc_note]:
                    # if the quantization collapses the start and end times of a note to the same point, adjust the
                    # end time so the the note is a single piece_length long.
                    if pc_note_to_quantize_end_time[pc_note] + best_piece_length_quarters <= quarters_beat_end_time:
                        # unless both are quantized to the start of the next beat, just move the end one piece forward
                        pc_note_to_quantize_end_time[pc_note] += best_piece_length_quarters
                    else:
                        # if they're at the start of the next beat, move the start one piece back
                        pc_note_to_quantize_start_time[pc_note] -= best_piece_length_quarters
                # save this info for later, when we need to assure they all have the same Tuplet
                pc_note.end_time_divisor = best_divisor

            beat_divisors.append(best_divisor)

        quarters_beat_start_time += quarters_beat_length
        seconds_beat_start_time += seconds_beat_length

    quantized_recording = []
    for pc_note in recording_in_seconds:
        quantized_recording.append(MPNote(start_time=pc_note_to_quantize_start_time[pc_note],
                                   length=pc_note_to_quantize_end_time[pc_note] - pc_note_to_quantize_start_time[pc_note],
                                   pitch=pc_note.pitch, volume=pc_note.volume, variant=pc_note.variant, tie=pc_note.tie))

    return quantized_recording, beat_divisors


def _collapse_recording_chords(recording):
    # sort it
    out = sorted(recording, key=lambda x: x.start_time)
    # combine contemporaneous notes into chords
    i = 0
    while i + 1 < len(out):
        if out[i].start_time == out[i+1].start_time and out[i].length == out[i+1].length \
                and out[i].volume == out[i+1].volume and out[i].variant == out[i+1].variant:
            chord_pitches = utilities.make_flat_list([out[i].pitch, out[i+1].pitch])
            out = out[:i] + [MPNote(start_time=out[i].start_time, length=out[i].length, pitch=chord_pitches,
                             volume=out[i].volume, variant=out[i].variant, tie=out[i].tie)] + out[i+2:]
        else:
            i += 1
    # Now split it into non-overlapping voices, and then we're good.
    return out


def _separate_into_non_overlapping_voices(recording, max_overlap):
    # takes a recording of MPNotes and breaks it up into separate voices that don't overlap more than max_overlap
    assert isinstance(recording, list)
    recording.sort(key=lambda note: note.start_time)
    voices = []
    for pc_note in recording:
        # find the first non-conflicting voices
        voice_to_add_to = None
        for voice in voices:
            voice_end_time = voice[-1].start_time + voice[-1].length
            if voice_end_time - pc_note.start_time < max_overlap:
                voice_to_add_to = voice
                break
        if voice_to_add_to is None:
            voice_to_add_to = []
            voices.append(voice_to_add_to)
        voice_to_add_to.append(pc_note)

    return voices

# [ ------- Voice Pre-Processing ------- ]


def _raw_voice_to_pretty_looking_voice(pc_voice, beat_schemes):
    pc_voice = _add_rests(pc_voice, beat_schemes)
    pc_voice = _break_into_ties(pc_voice, beat_schemes)
    return pc_voice


def _break_into_ties(recording_in_seconds, beat_schemes):
    # first, create an array of beat lengths that repeats the length of
    # the last beat_scheme until we reach the end of the voice

    for beat_scheme in beat_schemes:
        beat_start_time = beat_scheme.start_time
        for i in range(len(recording_in_seconds)):
            this_pc_note = recording_in_seconds[i]
            if this_pc_note.start_time < beat_start_time < this_pc_note.start_time + this_pc_note.length:
                # split it in two
                first_half_tie = "continue" if this_pc_note.tie is "stop" or this_pc_note.tie is "continue" else "start"
                second_half_tie = "continue" if this_pc_note.tie is "start" or this_pc_note.tie is "continue" else "stop"
                first_half = MPNote(this_pc_note.start_time, beat_start_time - this_pc_note.start_time,
                                    this_pc_note.pitch, this_pc_note.volume, this_pc_note.variant, first_half_tie)
                second_half = MPNote(beat_start_time, this_pc_note.start_time + this_pc_note.length - beat_start_time,
                                     this_pc_note.pitch, this_pc_note.volume, this_pc_note.variant, second_half_tie)
                recording_in_seconds[i] = [first_half, second_half]
        recording_in_seconds = utilities.make_flat_list(recording_in_seconds, indivisible_type=MPNote)

    return recording_in_seconds


def _add_rests(recording_in_seconds, beat_schemes):
    new_recording = list(recording_in_seconds)
    # first, create all the intervals representing the beats
    beat_intervals = [IntervalSet.between(beat_scheme.start_time, beat_scheme.end_time) for beat_scheme in beat_schemes]

    # subtract out all the time occupied by a note already
    for pc_note in recording_in_seconds:
        note_interval = IntervalSet.between(pc_note.start_time, pc_note.start_time + pc_note.length)
        for i in range(len(beat_intervals)):
            beat_intervals[i] -= note_interval

    # add in rests to fill out each beat
    for beat_interval in beat_intervals:
        for rest_range in beat_interval:
            new_recording.append(MPNote(start_time=rest_range.lower_bound,
                                        length=rest_range.upper_bound-rest_range.lower_bound,
                                        pitch=None, volume=None, variant=None, tie=None))
    new_recording.sort(key=lambda x: x.start_time)
    return new_recording


def _combine_tied_quarters_and_longer(recording_in_seconds, measure_schemes):
    # _break_into_ties has broken some long notes into tied quarters, which is ugly and unnecessary
    # so we'll recombine them
    return recording_in_seconds


def _get_tuplet_type(beat_length, beat_div):
    if beat_div is None:
        # the beat was empty...
        return None

    # preference is to express the
    beat_length_fraction = Fraction(beat_length).limit_denominator()
    normal_number = beat_length_fraction.numerator
    # if denominator is 1, normal type is quarter note, 2 -> eighth note, etc.
    normal_type = 4 * beat_length_fraction.denominator
    while normal_number * 2 <= beat_div:
        normal_number *= 2
        normal_type *= 2

    # now we have beat_div in the space of normal_number normal_type-th notes
    if normal_number == beat_div:
        return None
    else:
        return beat_div, normal_number, 4.0/normal_type


def _set_tuplets_for_notes_in_voice(voice, beat_schemes, beat_divisors):
    # we assume notes_and_rests is in order
    voice = list(voice)
    for beat_scheme, beat_div in zip(beat_schemes, beat_divisors):
        tuplet_type = _get_tuplet_type(beat_scheme.beat_length, beat_div)
        while len(voice) > 0 and voice[0].start_time < beat_scheme.end_time:
            this_note = voice.pop(0)
            assert isinstance(this_note, MPNote)
            if tuplet_type is not None:
                this_note.time_modification = tuplet_type
                this_note.length_without_tuplet = this_note.length * float(tuplet_type[0]) / tuplet_type[1]
                if this_note.start_time == beat_scheme.start_time:
                    this_note.notations.append(Tuplet("start"))
                if this_note.start_time + this_note.length == beat_scheme.end_time:
                    this_note.notations.append(Tuplet("end"))
            else:
                this_note.length_without_tuplet = this_note.length

    # there may be still a few notes left: these will be trailing rests that have been added since quantization
    # and for which no beat divisor has been calculated. We can safely set their length_without_tuplet to their length
    for remaining_rest in voice:
        assert isinstance(remaining_rest, MPNote)
        remaining_rest.length_without_tuplet = remaining_rest.length


def _break_notes_into_undotted_constituents(voice, beat_schemes):
    for pc_note in voice:
        pc_note.length_without_tuplet = MPNote.length_to_undotted_constituents(pc_note.length_without_tuplet)