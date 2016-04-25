__author__ = 'mpevans'


import xml.etree.ElementTree as ET
import math
from datetime import date

#  -------------------------------------------------- GLOBALS ----------------------------------------------------- #

num_beat_divisions = 10080
max_dots_allowed = 4

#  -------------------------------------------------- PITCH ----------------------------------------------------- #

pc_number_to_step_and_sharp_alteration = {0: ("C", 0), 1: ("C", 1), 2: ("D", 0), 3: ("D", 1),
                                          4: ("E", 0), 5: ("F", 0), 6: ("F", 1), 7: ("G", 0),
                                          8: ("G", 1), 9: ("A", 0), 10: ("A", 1), 11: ("B", 0)}

pc_number_to_step_and_flat_alteration = {0: ("C", 0), 1: ("D", -1), 2: ("D", 0), 3: ("E", -1),
                                         4: ("E", 0), 5: ("F", 0), 6: ("G", -1), 7: ("G", 0),
                                         8: ("A", -1), 9: ("A", 0), 10: ("B", -1), 11: ("B", 0)}

pc_number_to_step_and_standard_alteration = {0: ("C", 0), 1: ("C", 1), 2: ("D", 0), 3: ("E", -1),
                                             4: ("E", 0), 5: ("F", 0), 6: ("F", 1), 7: ("G", 0),
                                             8: ("A", -1), 9: ("A", 0), 10: ("B", -1), 11: ("B", 0)}


def get_pitch_step_alter_and_octave(pitch, accidental_preference="standard"):

    if accidental_preference == "sharp":
        rounded_pitch = math.floor(pitch)
        step, alteration = pc_number_to_step_and_sharp_alteration[rounded_pitch % 12]
    elif accidental_preference == "flat":
        rounded_pitch = math.ceil(pitch)
        step, alteration = pc_number_to_step_and_flat_alteration[rounded_pitch % 12]
    else:
        rounded_pitch = round(pitch)
        step, alteration = pc_number_to_step_and_standard_alteration[rounded_pitch % 12]
    octave = int(pitch/12) - 1

    # if a quarter-tone, adjust the accidental
    if pitch != rounded_pitch:
        alteration += pitch - rounded_pitch
        alteration = round(alteration, ndigits=3)
    return step, alteration, octave


class Pitch(ET.Element):

    def __init__(self, midi_val, accidental_preference="standard"):
        super(Pitch, self).__init__("pitch")
        self.step, self.alter, self.octave = get_pitch_step_alter_and_octave(midi_val, accidental_preference=accidental_preference)
        step_el = ET.Element("step")
        step_el.text = self.step
        alter_el = ET.Element("alter")
        alter_el.text = str(self.alter)
        octave_el = ET.Element("octave")
        octave_el.text = str(self.octave)
        self.append(step_el)
        self.append(alter_el)
        self.append(octave_el)

    def __repr__(self):
        return "{}{}, {}".format(self.step, self.octave, self.alter)

#  -------------------------------------------------- DURATION ----------------------------------------------------- #

length_to_note_type = {
    8.0: "breve",
    4.0: "whole",
    2.0: "half",
    1.0: "quarter",
    0.5: "eighth",
    0.25: "16th",
    1.0/8: "32nd",
    1.0/16: "64th",
    1.0/32: "128th"
}


class Duration:

    def __init__(self, length_without_tuplet, tuplet=None):
        # expresses a length that can be written as a single note head.
        # Optionally, a tuplet ratio, e.g. (4, 3).
        # The tuplet ratio can also include the normal type, e.g. (4, 3, 0.5) for 4 in the space of 3 eighths
        self.actual_length = float(length_without_tuplet)
        if tuplet is not None:
            self.actual_length *= tuplet[1] / tuplet[0]
        if length_without_tuplet in length_to_note_type:
            self.type = length_to_note_type[length_without_tuplet]
            self.dots = 0
        else:
            dots_multiplier = 1.5
            self.dots = 1
            while length_without_tuplet / dots_multiplier not in length_to_note_type:
                self.dots += 1
                dots_multiplier = (2.0 ** (self.dots + 1) - 1) / 2.0 ** self.dots
                if self.dots > max_dots_allowed:
                    raise ValueError("Duration does not resolve to single note type.")
            self.type = length_to_note_type[length_without_tuplet / dots_multiplier]
        if tuplet is not None:
            self.time_modification = ET.Element("time-modification")
            ET.SubElement(self.time_modification, "actual-notes").text = str(tuplet[0])
            ET.SubElement(self.time_modification, "normal-notes").text = str(tuplet[1])
            if len(tuplet) > 2:
                if tuplet[2] not in length_to_note_type:
                    ValueError("Tuplet normal note type is not a standard power of two length.")
                ET.SubElement(self.time_modification, "normal-type").text = length_to_note_type[tuplet[2]]
        else:
            self.time_modification = None


#  -------------------------------------------------- NOTATIONS ----------------------------------------------------- #


class Tuplet(ET.Element):
    def __init__(self, start_or_end, number=1, placement="above"):
        super(Tuplet, self).__init__("tuplet", {"type": start_or_end, "number": str(number), "placement": placement})


#  ---------------------------------------------------- NOTE ------------------------------------------------------- #


class Note(ET.Element):
    # represents notes, or rests by setting pitch to 0
    # to build a chord include several Notes, and set is_chord_member to True on all but the first

    def __init__(self, pitch, duration, ties=None, notations=(), articulations=(),
                 is_chord_member=False, voice=None):
        super(Note, self).__init__("note")

        if pitch == "bar rest":
            # special case: a bar rest. Here, duration is just the length in quarters rather than
            # a duration object, since that requires a note expressible as a single note head, and
            # we might be dealing with a bar of length, say 2.5
            duration = float(duration)
            self.append(ET.Element("rest", {"measure": "yes"}))
            duration_el = ET.Element("duration")
            duration_el.text = str(int(round(duration * num_beat_divisions)))
            self.append(duration_el)
            type_el = ET.Element("type")
            type_el.text = "whole"
            self.append(type_el)
            # okay, no need for the rest of this stuff, so return now
            return

        assert isinstance(duration, Duration)

        notations, articulations = list(notations), list(articulations)
        if pitch is None:
            self.append(ET.Element("rest"))
        else:
            assert isinstance(pitch, Pitch)
            self.append(pitch)
        duration_el = ET.Element("duration")
        duration_el.text = str(int(round(duration.actual_length * num_beat_divisions)))
        self.append(duration_el)

        if is_chord_member:
            self.append(ET.Element("chord"))

        if voice is not None:
            voice_el = ET.Element("voice")
            voice_el.text = str(voice)
            self.append(voice_el)

        if ties is not None:
            if ties.lower() == "start" or ties.lower() == "thru":
                self.append(ET.Element("tie", {"type": "start"}))
                notations.append(ET.Element("tied", {"type": "start"}))
            if ties.lower() == "stop" or ties.lower() == "thru":
                self.append(ET.Element("tie", {"type": "stop"}))
                notations.append(ET.Element("tied", {"type": "stop"}))

        type_el = ET.Element("type")
        type_el.text = duration.type
        self.append(type_el)
        for _ in range(duration.dots):
            self.append(ET.Element("dot"))

        if duration.time_modification is not None:
            self.append(duration.time_modification)

        if len(notations) + len(articulations) > 0:
            # there is either a notation or an articulation, so we'll add a notations tag
            notations_el = ET.Element("notations")
            for notation in notations:
                if isinstance(notation, ET.Element):
                    notations_el.append(notation)
                else:
                    notations_el.append(ET.Element(notation))
            if len(articulations) > 0:
                articulations_el = ET.SubElement(notations_el, "articulations")
                for articulation in articulations:
                    if isinstance(articulation, ET.Element):
                        articulations_el.append(articulation)
                    else:
                        articulations_el.append(ET.Element(articulation))
            self.append(notations_el)

    @classmethod
    def make_chord(cls, pitches, duration, ties=None, notations=(), articulations=(), voice=None):
        out = []
        chord_switch = False
        for pitch in pitches:
            out.append(cls(pitch, duration, ties=ties, notations=notations, articulations=articulations,
                           is_chord_member=chord_switch, voice=voice))
            chord_switch = True
        return out

    @classmethod
    def bar_rest(cls, duration_of_bar):
        return cls("bar rest", duration_of_bar)

#  -------------------------------------------------- MEASURE ------------------------------------------------------ #

clef_name_to_letter_and_line = {
    "treble": ("G", 2),
    "bass": ("F", 4),
    "alto": ("C", 3),
    "tenor": ("C", 4)
}

barline_name_to_xml_name = {
    "double": "light-light",
    "end": "light-heavy",
}


class Measure(ET.Element):

    def __init__(self, number, time_signature=None, clef=None, barline=None):
        super(Measure, self).__init__("measure", {"number": str(number)})

        self.has_barline = False

        attributes_el = ET.Element("attributes")
        self.append(attributes_el)
        divisions_el = ET.SubElement(attributes_el, "divisions")
        divisions_el.text = str(num_beat_divisions)

        if time_signature is not None:
            # time_signature is expressed as a tuple
            time_el = ET.SubElement(attributes_el, "time")
            ET.SubElement(time_el, "beats").text = str(time_signature[0])
            ET.SubElement(time_el, "beat-type").text = str(time_signature[1])

        if clef is not None:
            # clef is a tuple: the first element is the sign ("G" clef of "F" clef)
            # the second element is the line the sign centers on
            # an optional third element expresses the number of octaves transposition up or down
            # however, we also take words like "treble" and convert them
            if clef in clef_name_to_letter_and_line:
                clef = clef_name_to_letter_and_line[clef]
            clef_el = ET.SubElement(attributes_el, "clef")
            ET.SubElement(clef_el, "sign").text = clef[0]
            ET.SubElement(clef_el, "line").text = str(clef[1])
            if len(clef) > 2:
                ET.SubElement(clef_el, "clef-octave-change").text = str(clef[2])

        if barline is not None:
            barline_el = ET.Element("barline", {"location": "right"})
            self.append(barline_el)
            self.has_barline = True
            if barline in barline_name_to_xml_name:
                barline = barline_name_to_xml_name[barline]
            ET.SubElement(barline_el, "bar-style").text = barline

    def append(self, element):
        if self.has_barline:
            super(Measure, self).insert(-1, element)
        else:
            super(Measure, self).append(element)


#  -------------------------------------------------- Part ------------------------------------------------------ #

class PartGroup:
    next_available_number = 1

    def __init__(self, has_bracket=True, has_group_bar_line=True):
        self.number = PartGroup.next_available_number
        PartGroup.next_available_number += 1
        self.has_bracket = has_bracket
        self.has_group_bar_line = has_group_bar_line

    def get_start_element(self):
        start_element = ET.Element("part-group", {"number": str(self.number), "type": "start"})
        if self.has_bracket:
            ET.SubElement(start_element, "group-symbol").text = "bracket"
        ET.SubElement(start_element, "group-barline").text = "yes" if self.has_group_bar_line else "no"
        return start_element

    def get_stop_element(self):
        return ET.Element("part-group", {"number": str(self.number), "type": "stop"})


class Part(ET.Element):
    next_available_number = 1

    def __init__(self, part_name, manual_part_id=None):
        self.part_id = manual_part_id if manual_part_id is not None else "P" + str(Part.next_available_number)
        if manual_part_id is None:
            Part.next_available_number += 1
        super(Part, self).__init__("part", {"id": str(self.part_id)})
        self.part_name = part_name

    def get_part_list_entry(self):
        score_part_el = ET.Element("score-part", {"id": str(self.part_id)})
        ET.SubElement(score_part_el, "part-name").text = self.part_name
        return score_part_el

#  ------------------------------------------------- Score ------------------------------------------------------ #


class Score(ET.Element):

    def __init__(self, title, composer):
        super(Score, self).__init__("score-partwise")
        str(date.today())
        work_el = ET.Element("work")
        self.append(work_el)
        ET.SubElement(work_el, "work-title").text = title
        id_el = ET.Element("identification")
        self.append(id_el)
        ET.SubElement(id_el, "creator", {"type": "composer"}).text = composer
        encoding_el = ET.SubElement(id_el, "encoding")
        ET.SubElement(encoding_el, "encoding-date").text = str(date.today())
        ET.SubElement(encoding_el, "software").text = "marcpy"
        self.part_list = ET.Element("part-list")
        self.append(self.part_list)

    def add_part(self, part):
        self.append(part)
        self.part_list.append(part.get_part_list_entry())

    def add_parts_as_group(self, parts, part_group):
        self.part_list.append(part_group.get_start_element())
        for part in parts:
            self.append(part)
            self.part_list.append(part.get_part_list_entry())
        self.part_list.append(part_group.get_stop_element())

    def save_to_file(self, file_name):
        file_ = open(file_name, 'w')
        file_.write(ET.tostring(self))
        file_.close()


# my_score = Score("Test Score", "D. Trump")
# violin_part = Part("Violin")
# measure = Measure(1, (3, 4), "treble")
# measure.append(Note(Pitch(58.5), Duration(1.5, (3, 2, 1)), notations=[Tuplet("start")],
#                     articulations=[ET.Element("staccato"), ET.Element("tenuto")]))
# measure.append(Note(Pitch(63), Duration(0.5, (3, 2, 1)), articulations=[ET.Element("tenuto")]))
# measure.append(Note(Pitch(61), Duration(1.0, (3, 2, 1)), notations=[Tuplet("end")], ties="start"))
# measure.append(Note(Pitch(61), Duration(0.5), ties="thru"))
# measure.append(Note(Pitch(61), Duration(0.25), ties="end", articulations=["staccatissimo"]))
# measure.append(Note(None, Duration(0.25)))
# violin_part.append(measure)
# measure = Measure(2, (5, 8))
# measure.append(Note(Pitch(70), Duration(1.5), articulations=[ET.Element("tenuto")]))
# measure.append(Note(Pitch(65), Duration(1.0), ties="start"))
# violin_part.append(measure)
# measure = Measure(3, barline="end")
# measure.append(Note(Pitch(65), Duration(0.5, (4, 3, 0.5)), notations=[Tuplet("start")], ties="end"))
# measure.append(Note(Pitch(66), Duration(1, (4, 3, 0.5)), articulations=[ET.Element("tenuto")]))
# measure.append(Note(Pitch(67), Duration(0.5, (4, 3, 0.5)), notations=[Tuplet("end")], ties="start"))
# measure.append(Note(Pitch(67), Duration(0.5), notations=[Tuplet("end")], ties="end"))
# measure.append(Note(None, Duration(0.5)))
# violin_part.append(measure)
#
# viola_part = Part("Viola")
# measure = Measure(1, (3, 4), "alto")
# measure.append(Note(Pitch(58.5), Duration(1.5, (3, 2, 1)), notations=[Tuplet("start")],
#                     articulations=[ET.Element("staccato"), ET.Element("tenuto")]))
# measure.append(Note(Pitch(53), Duration(0.5, (3, 2, 1)), articulations=[ET.Element("tenuto")]))
# measure.append(Note(Pitch(51), Duration(1.0, (3, 2, 1)), notations=[Tuplet("end")], ties="start"))
# measure.append(Note(Pitch(51), Duration(0.5), ties="thru"))
# measure.append(Note(Pitch(51), Duration(0.25), ties="end", articulations=["staccatissimo"]))
# measure.append(Note(None, Duration(0.25)))
# viola_part.append(measure)
# measure = Measure(2, (5, 8))
# measure.append(Note(None, Duration(1.0)))
# measure.append(Note(Pitch(55), Duration(0.5, (4, 3, 0.5)), notations=[Tuplet("start")], ties="end"))
# measure.append(Note(Pitch(56), Duration(1, (4, 3, 0.5)), articulations=[ET.Element("tenuto")]))
# measure.append(Note(Pitch(57), Duration(0.5, (4, 3, 0.5)), notations=[Tuplet("end")]))
# viola_part.append(measure)
# measure = Measure(3, barline="end")
# measure.append(Note(Pitch(60), Duration(1.5)))
# measure.append(Note(Pitch(60), Duration(0.5), articulations=[ET.Element("tenuto")]))
# measure.append(Note(Pitch(60), Duration(0.5)))
# viola_part.append(measure)
#
# cello_part = Part("Cello")
# measure = Measure(1, (3, 4), "bass")
# measure.append(Note.bar_rest(3))
# cello_part.append(measure)
#
# measure = Measure(2, (5, 8))
# measure.extend(Note.make_chord([Pitch(41), Pitch(45), Pitch(48)], Duration(1.5)))
# measure.append(Note(Pitch(40), Duration(0.5), articulations=[ET.Element("tenuto")]))
# measure.append(Note(Pitch(40), Duration(0.5)))
# cello_part.append(measure)
#
# measure = Measure(3, barline="end")
# measure.append(Note.bar_rest(2.5))
# cello_part.append(measure)
#
# my_score.add_parts_as_group([violin_part, viola_part], PartGroup())
# my_score.add_part(cello_part)
#
#
# my_score.save_to_file("testScore.xml")