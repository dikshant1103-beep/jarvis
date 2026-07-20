"""Voice input via ALSA `arecord` + faster-whisper.

Deliberately avoids sounddevice/portaudio: those need a `sudo apt install`,
and this machine has no passwordless sudo. arecord ships with the OS.
"""
import subprocess
import tempfile
import time
import config

_model = None


def _get_model():
    """Loaded lazily — the first load takes ~40s, so don't pay it at startup."""
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        print("  (loading whisper, first time takes a moment…)", flush=True)
        _model = WhisperModel(
            config.WHISPER_MODEL, device="cpu",
            compute_type="int8", cpu_threads=config.WHISPER_THREADS,
        )
    return _model


def mic_available():
    try:
        out = subprocess.run(["arecord", "-l"], capture_output=True, text=True, timeout=5)
        return "card" in out.stdout
    except Exception:
        return False


def record(seconds=15):
    """Record up to `seconds`; returns the wav path. Ctrl-C stops early."""
    wav = tempfile.mktemp(suffix=".wav")
    proc = subprocess.Popen(
        ["arecord", "-q", "-f", "S16_LE", "-r", "16000", "-c", "1", "-d", str(seconds), wav],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        proc.wait()
        time.sleep(0.2)  # let arecord flush the header before we read it
    return wav


def transcribe(wav):
    m = _get_model()
    # vad_filter drops silence, which is most of a push-to-talk clip.
    segs, _ = m.transcribe(wav, beam_size=1, vad_filter=True, language="en")
    return " ".join(s.text for s in segs).strip()


def listen(seconds=15):
    """Record then transcribe. Returns (text, seconds_of_audio, seconds_taken)."""
    wav = record(seconds)
    t0 = time.time()
    text = transcribe(wav)
    return text, seconds, time.time() - t0
