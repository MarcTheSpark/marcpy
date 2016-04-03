__author__ = 'mpevans'


def get_triangle_wave_value(t, amplitude, frequency, offset=0):
    A = float(amplitude)
    P = (1.0/frequency) / 2
    return (A/P) * (P - abs((t + P/2) % (2*P) - P) ) - A/2 + offset