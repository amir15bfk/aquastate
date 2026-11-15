"""
AquaState — original 30s score.

Minimal documentary cue in D minor that resolves to D major.
Synthesised from scratch (sine/additive/noise) so the film carries no
music licensing burden. 48 kHz stereo WAV.
"""

import os
import numpy as np
from scipy.signal import butter, sosfilt, fftconvolve

SR = 48000
DUR = 30.0
N = int(SR * DUR)
HERE = os.path.dirname(os.path.abspath(__file__))
rng = np.random.default_rng(11)


def t_axis(dur):
    return np.arange(int(dur * SR), dtype=np.float64) / SR


def lowpass(x, cutoff, order=2):
    sos = butter(order, min(cutoff, SR * 0.49) / (SR / 2), btype="low", output="sos")
    return sosfilt(sos, x)


def highpass(x, cutoff, order=2):
    sos = butter(order, max(8, cutoff) / (SR / 2), btype="high", output="sos")
    return sosfilt(sos, x)


def bandpass(x, lo, hi, order=2):
    sos = butter(order, [max(8, lo) / (SR / 2), min(hi, SR * 0.49) / (SR / 2)], btype="band", output="sos")
    return sosfilt(sos, x)


def env_ad(n, attack, decay, curve=1.0):
    a = max(1, int(attack * SR))
    e = np.ones(n, dtype=np.float64)
    e[:a] = np.linspace(0, 1, a) ** 0.7
    t = np.arange(n) / SR
    return e * np.exp(-t * decay) ** curve


def note(freq, dur=3.2, amp=0.25, pan=0.0, bright=1.0):
    t = t_axis(dur)
    env = (1 - np.exp(-t * 90)) * np.exp(-t * 1.55)
    vib = 1 + 0.0015 * np.sin(2 * np.pi * 4.6 * t)
    sig = (
        0.60 * np.sin(2 * np.pi * freq * vib * t)
        + 0.24 * np.sin(2 * np.pi * freq * 2.001 * t + 0.15)
        + 0.09 * np.sin(2 * np.pi * freq * 3.003 * t + 0.4)
        + 0.035 * np.sin(2 * np.pi * freq * 4.02 * t + 0.7)
    )
    sig *= env * amp
    if bright < 1.0:
        sig = lowpass(sig, 1400 * bright + 400)
    return stereo(sig, pan)


def pad(freqs, dur, amp=0.06, attack=1.3, release=1.8, pan=0.0, cutoff=1100):
    t = t_axis(dur)
    n = len(t)
    env = np.ones(n)
    a = int(attack * SR)
    r = int(release * SR)
    env[:a] = np.linspace(0, 1, a) ** 1.4
    env[-r:] *= np.linspace(1, 0, r) ** 1.2
    lfo = 0.85 + 0.15 * np.sin(2 * np.pi * 0.11 * t + 0.4)
    sig = np.zeros(n)
    for i, f in enumerate(freqs):
        detune = 1 + (i - 1) * 0.0018
        sig += np.sin(2 * np.pi * f * detune * t + i * 0.6)
        sig += 0.22 * np.sin(2 * np.pi * f * 2 * detune * t + i * 0.9)
    sig = lowpass(sig, cutoff) * env * lfo * amp
    return stereo(sig, pan, width=0.35)


def drone(dur):
    t = t_axis(dur)
    n = len(t)
    sig = (
        0.55 * np.sin(2 * np.pi * 36.71 * t)
        + 0.50 * np.sin(2 * np.pi * 55.0 * t + 0.2)
        + 0.38 * np.sin(2 * np.pi * 73.42 * t + 1.1)
        + 0.12 * np.sin(2 * np.pi * 110.0 * t + 2.0)
    )
    lfo = 0.72 + 0.28 * np.sin(2 * np.pi * 0.045 * t - 0.6)
    env = np.ones(n)
    env[: int(2.5 * SR)] = np.linspace(0, 1, int(2.5 * SR)) ** 1.5
    env[-int(3.0 * SR):] *= np.linspace(1, 0, int(3.0 * SR)) ** 1.2
    return lowpass(sig * lfo * env, 190)


def water(dur):
    n = int(dur * SR)
    x = rng.normal(0, 1, n)
    x = bandpass(x, 260, 1500)
    t = np.arange(n) / SR
    lfo = 0.45 + 0.55 * (0.5 + 0.5 * np.sin(2 * np.pi * 0.075 * t - 1.0))
    env = np.ones(n)
    env[: int(1.5 * SR)] = np.linspace(0, 1, int(1.5 * SR))
    env[-int(2.0 * SR):] *= np.linspace(1, 0, int(2.0 * SR))
    return x * lfo * env


def impact(dur=1.8, amp=0.5):
    t = t_axis(dur)
    f = 68 * np.exp(-t * 2.2) + 32
    sig = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 3.0)
    noise = lowpass(rng.normal(0, 1, len(t)), 420) * np.exp(-t * 7.0) * 0.5
    return stereo((sig + noise) * amp, 0.0, width=0.2)


def kick(amp=0.24):
    dur = 0.35
    t = t_axis(dur)
    f = 62 * np.exp(-t * 22) + 38
    sig = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 10)
    click = highpass(rng.normal(0, 1, len(t)), 1800) * np.exp(-t * 90) * 0.12
    return stereo((sig + click) * amp, 0.0, width=0.1)


def tick(amp=0.05):
    dur = 0.06
    t = t_axis(dur)
    x = bandpass(rng.normal(0, 1, len(t)), 2400, 7500) * np.exp(-t * 90)
    return stereo(x * amp, 0.12, width=0.5)


def riser(dur=2.0, amp=0.10):
    t = t_axis(dur)
    n = len(t)
    x = rng.normal(0, 1, n)
    x = bandpass(x, 500, 5000)
    env = (t / dur) ** 2.4
    return stereo(x * env * amp, 0.0, width=0.4)


def bell(freq=1174.66, dur=3.5, amp=0.10):
    t = t_axis(dur)
    env = np.exp(-t * 1.45) * (1 - np.exp(-t * 120))
    sig = (
        np.sin(2 * np.pi * freq * t)
        + 0.4 * np.sin(2 * np.pi * freq * 2.01 * t)
        + 0.2 * np.sin(2 * np.pi * freq * 2.99 * t)
    ) * env * amp
    return stereo(sig, -0.1, width=0.5)


def stereo(mono, pan=0.0, width=0.2):
    """pan -1..1; width adds a tiny haas/detune spread."""
    l = mono * np.sqrt((1 - pan) / 2)
    r = mono * np.sqrt((1 + pan) / 2)
    if width > 0:
        d = int(0.006 * SR * width)
        if d > 0:
            r = np.concatenate([np.zeros(d), r[:-d]])
    return np.stack([l, r], axis=1)


def place(buf, sig, start, gain=1.0):
    if sig is None:
        return
    i = int(start * SR)
    if i >= N:
        return
    if sig.ndim == 1:
        sig = np.stack([sig, sig], axis=1)
    n = min(len(sig), N - i)
    buf[i:i + n] += sig[:n] * gain


def reverb(buf, amount=0.16, decay=1.8):
    dur = decay
    t = t_axis(dur)
    ir = rng.normal(0, 1, len(t)) * np.exp(-t * 3.2)
    ir = lowpass(ir, 5000)
    ir[: int(0.012 * SR)] = 0
    ir /= np.max(np.abs(ir)) + 1e-9
    wet = np.zeros_like(buf)
    for c in range(2):
        conv = fftconvolve(buf[:, c], ir)[:N]
        wet[:, c] = conv
    return buf + wet * amount


def main():
    mix = np.zeros((N, 2), dtype=np.float64)
    t = np.arange(N) / SR

    # bed
    d = drone(DUR)
    place(mix, d, 0.0, 0.34)
    w = water(DUR)
    wl = np.stack([w, np.roll(w, int(0.013 * SR))], axis=1)
    place(mix, wl, 0.0, 0.055)

    # opening notes
    place(mix, note(146.83, 4.0, 0.11, -0.15), 0.35)
    place(mix, note(220.00, 4.5, 0.075, 0.15), 2.60)
    place(mix, note(174.61, 4.0, 0.08, -0.1), 4.10)
    place(mix, note(146.83, 4.0, 0.07, 0.1), 6.50)
    place(mix, note(233.08, 5.0, 0.09, -0.05, bright=0.7), 8.55)

    # pads: tension then lift
    place(mix, pad([146.83, 174.61, 220.00], 4.3, 0.050, 1.2, 1.0, -0.15), 0.0)
    place(mix, pad([146.83, 174.61, 220.00, 155.56], 5.0, 0.040, 1.4, 1.4, 0.1), 3.7)
    place(mix, pad([116.54, 146.83, 174.61], 6.0, 0.050, 1.2, 1.2, -0.1), 8.6)
    place(mix, pad([146.83, 174.61, 220.00, 293.66], 4.8, 0.060, 0.9, 1.6, 0.0, cutoff=1500), 11.44)
    place(mix, pad([116.54, 146.83, 174.61, 233.08], 5.6, 0.045, 1.2, 1.6, 0.1), 16.1)
    place(mix, pad([174.61, 220.00, 261.63], 3.0, 0.045, 0.8, 1.2, -0.1), 19.0)
    place(mix, pad([174.61, 220.00, 261.63], 2.2, 0.035, 0.8, 1.2, 0.0), 21.85)
    place(mix, pad([146.83, 174.61, 220.00], 3.6, 0.045, 1.0, 1.4, 0.0), 23.51)
    place(mix, pad([110.00, 138.59, 164.81], 3.4, 0.055, 1.2, 1.0, 0.05), 24.4)
    place(mix, pad([146.83, 185.00, 220.00, 293.66], 4.6, 0.070, 0.8, 2.4, 0.0, cutoff=1800), 26.42)

    # pulse
    for x in np.arange(8.61, 11.44, 0.76):
        place(mix, kick(0.20), float(x))
    for x in np.arange(11.44, 26.35, 0.50):
        place(mix, kick(0.17 if x < 16.1 else 0.15), float(x))
    for x in np.arange(16.1, 26.35, 0.50):
        place(mix, tick(0.035), float(x) + 0.25)

    # hits
    place(mix, impact(1.8, 0.62), 8.60)
    place(mix, impact(2.0, 0.55), 11.44)
    place(mix, riser(2.1, 0.11), 24.35)
    place(mix, bell(1174.66, 3.4, 0.075), 26.42)
    place(mix, note(293.66, 4.2, 0.10, 0.0), 27.3)
    place(mix, note(220.00, 4.0, 0.06, -0.2), 28.6)

    # dissolve
    mix = reverb(mix, 0.14, 1.6)
    fade_in = np.ones(N)
    fade_in[: int(0.25 * SR)] = np.linspace(0, 1, int(0.25 * SR))
    fade_out = np.ones(N)
    fo = int(2.6 * SR)
    fade_out[-fo:] = np.linspace(1, 0, fo) ** 1.3
    mix *= fade_in[:, None] * fade_out[:, None]

    # gentle bus glue / limiter
    mix = highpass(mix.T, 28).T
    peak = np.max(np.abs(mix))
    mix = mix / (peak + 1e-9) * 0.80
    # soft clip
    mix = np.tanh(mix * 1.15) / np.tanh(1.15) * 0.80

    out = (np.clip(mix, -1, 1) * 32767).astype(np.int16)
    path = os.path.join(HERE, "audio", "score.wav")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    from scipy.io import wavfile
    wavfile.write(path, SR, out)
    print("wrote", path, out.shape, "peak", np.max(np.abs(out)))


if __name__ == "__main__":
    main()
