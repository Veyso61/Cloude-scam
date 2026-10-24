# -*- coding: utf-8 -*-
"""Sistem sesini (WASAPI loopback) dinler, konuşmayı keser ve İngilizce metne çevirir.

Akış:  Hoparlör çıkışı (loopback) -> çerçeveler -> VoiceSegmenter (enerji + webrtcvad)
       -> konuşma parçası -> 16 kHz'e örnekleme -> faster-whisper (yerel) / Google (çevrimiçi)
       -> on_text(metin) geri çağrısı

Arka uçlar:
  * PyAudioWPatch  (Windows, önerilen)  : pip install PyAudioWPatch
  * soundcard      (Windows/Linux yedek): pip install soundcard
"""
from __future__ import annotations

import collections
import math
import queue
import threading
import time
from typing import Callable, Deque, List, Optional, Tuple

import numpy as np

StatusCb = Callable[[str], None]


def _noop(*_a, **_k):
    return None


# ============================================================================ örnekleme

def resample(x: np.ndarray, sr: int, target: int = 16000) -> np.ndarray:
    x = np.asarray(x, dtype=np.float32)
    if sr == target or len(x) == 0:
        return x
    try:
        from scipy.signal import resample_poly  # type: ignore
        g = math.gcd(int(sr), int(target))
        return resample_poly(x, target // g, sr // g).astype(np.float32)
    except Exception:
        pass
    cutoff = 0.5 * target / sr * 0.92
    taps = 63
    n = np.arange(taps) - (taps - 1) / 2.0
    h = np.sinc(2 * cutoff * n) * np.hamming(taps)
    h /= h.sum()
    y = np.convolve(x, h, mode="same")
    n_out = int(len(x) * target / sr)
    t_out = np.arange(n_out) * (sr / float(target))
    return np.interp(t_out, np.arange(len(x)), y).astype(np.float32)


def rms_db(frame: np.ndarray) -> float:
    if frame.size == 0:
        return -120.0
    r = float(np.sqrt(np.mean(np.square(frame, dtype=np.float64))))
    return 20.0 * math.log10(r + 1e-9)


# ============================================================================ capture back-ends

class LoopbackSource:
    name = "base"

    def __init__(self, device_name: str = "", frame_ms: int = 30):
        self.device_name = (device_name or "").lower()
        self.frame_ms = frame_ms
        self.out: "queue.Queue[Tuple[np.ndarray, int]]" = queue.Queue(maxsize=2000)
        self.description = ""

    def start(self) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError

    def _push(self, mono: np.ndarray, rate: int) -> None:
        try:
            self.out.put_nowait((mono, rate))
        except queue.Full:
            try:
                self.out.get_nowait()
                self.out.put_nowait((mono, rate))
            except queue.Empty:
                pass


class PyAudioWPatchSource(LoopbackSource):
    """Windows WASAPI loopback (PyAudioWPatch)."""
    name = "pyaudiowpatch"

    def __init__(self, device_name: str = "", frame_ms: int = 30):
        super().__init__(device_name, frame_ms)
        import pyaudiowpatch as pyaudio  # type: ignore
        self.pa_mod = pyaudio
        self.pa = None
        self.stream = None

    @staticmethod
    def list_devices() -> List[str]:
        import pyaudiowpatch as pyaudio  # type: ignore
        p = pyaudio.PyAudio()
        try:
            return [d["name"] for d in p.get_loopback_device_info_generator()]
        finally:
            p.terminate()

    def _pick_device(self):
        p = self.pa
        loopbacks = list(p.get_loopback_device_info_generator())
        if not loopbacks:
            raise RuntimeError("WASAPI loopback cihazı bulunamadı.")
        if self.device_name:
            for d in loopbacks:
                if self.device_name in d["name"].lower():
                    return d
            raise RuntimeError(f"'{self.device_name}' içeren loopback cihazı yok. Mevcut: {[d['name'] for d in loopbacks]}")
        wasapi = p.get_host_api_info_by_type(self.pa_mod.paWASAPI)
        default_out = p.get_device_info_by_index(wasapi["defaultOutputDevice"])
        if default_out.get("isLoopbackDevice"):
            return default_out
        for d in loopbacks:
            if default_out["name"] in d["name"]:
                return d
        return loopbacks[0]

    def start(self) -> None:
        pyaudio = self.pa_mod
        self.pa = pyaudio.PyAudio()
        dev = self._pick_device()
        channels = max(1, int(dev["maxInputChannels"]))
        rate = int(dev["defaultSampleRate"])
        frames = max(64, int(rate * self.frame_ms / 1000))
        self.description = f"{dev['name']} @ {rate} Hz x{channels}"

        def cb(in_data, frame_count, time_info, status):
            arr = np.frombuffer(in_data, dtype=np.int16).astype(np.float32) / 32768.0
            if channels > 1:
                arr = arr.reshape(-1, channels).mean(axis=1)
            self._push(arr, rate)
            return (None, pyaudio.paContinue)

        self.stream = self.pa.open(format=pyaudio.paInt16, channels=channels, rate=rate, input=True,
                                   input_device_index=dev["index"], frames_per_buffer=frames, stream_callback=cb)
        self.stream.start_stream()

    def stop(self) -> None:
        try:
            if self.stream is not None:
                self.stream.stop_stream()
                self.stream.close()
        finally:
            self.stream = None
            if self.pa is not None:
                self.pa.terminate()
                self.pa = None


class SoundCardSource(LoopbackSource):
    """soundcard kütüphanesi ile loopback (Windows / PulseAudio)."""
    name = "soundcard"

    def __init__(self, device_name: str = "", frame_ms: int = 30, samplerate: int = 48000):
        super().__init__(device_name, frame_ms)
        import soundcard as sc  # type: ignore
        self.sc = sc
        self.samplerate = samplerate
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    @staticmethod
    def list_devices() -> List[str]:
        import soundcard as sc  # type: ignore
        return [m.name for m in sc.all_microphones(include_loopback=True) if getattr(m, "isloopback", False)]

    def _pick(self):
        sc = self.sc
        mics = sc.all_microphones(include_loopback=True)
        loop = [m for m in mics if getattr(m, "isloopback", False)]
        if self.device_name:
            for m in loop:
                if self.device_name in m.name.lower():
                    return m
        spk = sc.default_speaker()
        if spk is not None:
            try:
                return sc.get_microphone(id=str(spk.name), include_loopback=True)
            except Exception:
                pass
        if loop:
            return loop[0]
        raise RuntimeError("soundcard: loopback cihazı bulunamadı.")

    def start(self) -> None:
        mic = self._pick()
        self.description = f"{mic.name} @ {self.samplerate} Hz"
        nframes = int(self.samplerate * self.frame_ms / 1000)

        def run():
            with mic.recorder(samplerate=self.samplerate) as rec:
                while not self._stop.is_set():
                    data = rec.record(numframes=nframes)
                    if data is None or len(data) == 0:
                        continue
                    arr = np.asarray(data, dtype=np.float32)
                    if arr.ndim > 1:
                        arr = arr.mean(axis=1)
                    self._push(arr, self.samplerate)

        self._thread = threading.Thread(target=run, name="soundcard-capture", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=1.0)


def make_source(backend: str, device_name: str, frame_ms: int, status: StatusCb = _noop) -> LoopbackSource:
    order = [backend] if backend and backend != "auto" else ["pyaudiowpatch", "soundcard"]
    errors = []
    for b in order:
        try:
            if b == "pyaudiowpatch":
                return PyAudioWPatchSource(device_name, frame_ms)
            if b == "soundcard":
                return SoundCardSource(device_name, frame_ms)
        except ImportError as e:
            errors.append(f"{b}: kurulu değil ({e})")
        except Exception as e:  # noqa: BLE001
            errors.append(f"{b}: {e}")
    raise RuntimeError("Ses yakalama arka ucu açılamadı → " + " | ".join(errors) +
                       "  (pip install PyAudioWPatch  veya  pip install soundcard)")


def list_loopback_devices() -> List[str]:
    for cls in (PyAudioWPatchSource, SoundCardSource):
        try:
            return cls.list_devices()
        except Exception:
            continue
    return []


# ============================================================================ segmentasyon

class VoiceSegmenter:
    """Enerji (uyarlanır gürültü tabanı) + isteğe bağlı webrtcvad ile konuşma parçaları üretir."""

    def __init__(self, threshold_db: float = -48.0, margin_db: float = 9.0, frame_ms: int = 30,
                 min_speech_ms: int = 300, end_silence_ms: int = 650, max_segment_s: float = 12.0,
                 pre_roll_ms: int = 300, use_webrtcvad: bool = True):
        self.threshold_db = threshold_db
        self.margin_db = margin_db
        self.frame_ms = frame_ms
        self.min_speech_frames = max(1, min_speech_ms // frame_ms)
        self.end_silence_frames = max(1, end_silence_ms // frame_ms)
        self.max_frames = int(max_segment_s * 1000 / frame_ms)
        self.pre_roll: Deque[np.ndarray] = collections.deque(maxlen=max(1, pre_roll_ms // frame_ms))
        self.history: Deque[float] = collections.deque(maxlen=int(3000 / frame_ms))
        self.rate: Optional[int] = None
        self._buf = np.zeros(0, dtype=np.float32)
        self.in_speech = False
        self.speech_run = 0
        self.silence_run = 0
        self.frames: List[np.ndarray] = []
        self.last_level_db = -120.0
        self.last_frame_at = time.time()
        self.vad = None
        if use_webrtcvad:
            try:
                import webrtcvad  # type: ignore
                self.vad = webrtcvad.Vad(2)
            except Exception:
                self.vad = None

    def noise_floor(self) -> float:
        if len(self.history) < 10:
            return -70.0
        return float(np.percentile(np.array(self.history), 20))

    def _vad_speech(self, frame: np.ndarray, rate: int) -> bool:
        if self.vad is None:
            return True
        try:
            if rate in (8000, 16000, 32000, 48000):
                f, r = frame, rate
            else:
                f, r = resample(frame, rate, 16000), 16000
            n = int(r * self.frame_ms / 1000)
            pcm = (np.clip(f[:n], -1, 1) * 32767).astype(np.int16).tobytes()
            if len(pcm) != n * 2:
                return True
            return self.vad.is_speech(pcm, r)
        except Exception:
            return True

    def feed(self, chunk: np.ndarray, rate: int) -> List[Tuple[np.ndarray, int]]:
        """Ham çerçeve ekler, tamamlanan konuşma parçalarını (ses, örnekleme hızı) döndürür."""
        out: List[Tuple[np.ndarray, int]] = []
        if self.rate is None or self.rate != rate:
            self.rate = rate
            self._buf = np.zeros(0, dtype=np.float32)
        self.last_frame_at = time.time()
        self._buf = np.concatenate([self._buf, chunk.astype(np.float32)])
        n = int(rate * self.frame_ms / 1000)
        while len(self._buf) >= n:
            frame, self._buf = self._buf[:n], self._buf[n:]
            seg = self._process_frame(frame, rate)
            if seg is not None:
                out.append(seg)
        return out

    def _process_frame(self, frame: np.ndarray, rate: int) -> Optional[Tuple[np.ndarray, int]]:
        level = rms_db(frame)
        self.last_level_db = level
        floor = self.noise_floor()
        thr = max(self.threshold_db, floor + self.margin_db)
        speech = level > thr and self._vad_speech(frame, rate)
        if not self.in_speech:
            self.history.append(level)
            self.pre_roll.append(frame)
            self.speech_run = self.speech_run + 1 if speech else 0
            if self.speech_run >= self.min_speech_frames:
                self.in_speech = True
                self.frames = list(self.pre_roll)
                self.silence_run = 0
            return None
        self.frames.append(frame)
        if speech:
            self.silence_run = 0
        else:
            self.silence_run += 1
            self.history.append(level)
        if self.silence_run >= self.end_silence_frames:
            return self._emit(trim=self.silence_run - 3)
        if len(self.frames) >= self.max_frames:
            return self._emit(trim=0, keep_speaking=True)
        return None

    def _emit(self, trim: int = 0, keep_speaking: bool = False) -> Optional[Tuple[np.ndarray, int]]:
        frames = self.frames[:-trim] if trim > 0 else self.frames
        self.frames = []
        self.speech_run = 0
        self.silence_run = 0
        self.in_speech = keep_speaking
        self.pre_roll.clear()
        if not frames or self.rate is None:
            return None
        audio = np.concatenate(frames)
        if len(audio) < self.rate * 0.25:
            return None
        return audio, self.rate

    def flush_if_idle(self, idle_ms: int) -> Optional[Tuple[np.ndarray, int]]:
        """Loopback sessizken hiç çerçeve gelmeyebilir; zamanla parçayı kapat."""
        if self.in_speech and (time.time() - self.last_frame_at) * 1000 >= idle_ms:
            return self._emit(trim=0)
        return None


# ============================================================================ STT

def add_nvidia_dll_dirs() -> List[str]:
    """install_gpu.bat ile pip'ten kurulan CUDA 12 / cuDNN 9 DLL'lerini (site-packages/nvidia/*/bin) bulunur yap."""
    import os
    import site
    import sys
    if sys.platform != "win32":
        return []
    roots = list(site.getsitepackages()) + [site.getusersitepackages()]
    added = []
    for root in roots:
        nv = os.path.join(root, "nvidia")
        if not os.path.isdir(nv):
            continue
        for sub in os.listdir(nv):
            b = os.path.join(nv, sub, "bin")
            if os.path.isdir(b) and b not in added:
                try:
                    os.add_dll_directory(b)
                except (OSError, AttributeError):
                    pass
                os.environ["PATH"] = b + os.pathsep + os.environ.get("PATH", "")
                added.append(b)
    return added


class FasterWhisperTranscriber:
    name = "faster-whisper"

    def __init__(self, model: str = "auto", device: str = "auto", compute_type: str = "auto",
                 beam_size: int = 1, cpu_threads: int = 4, language: str = "en", status: StatusCb = _noop):
        add_nvidia_dll_dirs()
        from faster_whisper import WhisperModel  # type: ignore
        self._WhisperModel = WhisperModel
        self.requested_model = model
        self.beam_size = beam_size
        self.cpu_threads = cpu_threads
        self.language = language
        self.status = status
        dev = device
        if dev == "auto":
            dev = "cpu"
            try:
                import ctranslate2  # type: ignore
                if ctranslate2.get_cuda_device_count() > 0:
                    dev = "cuda"
            except Exception:
                dev = "cpu"
        self._load(model, dev, compute_type)

    def _load(self, model: str, device: str, compute_type: str) -> None:
        m = model if model != "auto" else ("small.en" if device == "cuda" else "base.en")
        ct = compute_type if compute_type != "auto" else ("float16" if device == "cuda" else "int8")
        self.status(f"Whisper modeli yükleniyor: {m} ({device}/{ct}) — ilk seferde indirilir…")
        try:
            self.model = self._WhisperModel(m, device=device, compute_type=ct, cpu_threads=self.cpu_threads)
            self.device = device
            self.model_name = m
            # transcribe() tembeldir: model ancak segmentler okununca çalışır. Eksik CUDA/cuDNN DLL'leri
            # burada ortaya çıksın diye kısa bir sesi VAD olmadan gerçekten çözdür.
            warm = (np.random.RandomState(0).randn(16000) * 0.01).astype(np.float32)
            list(self.model.transcribe(warm, language=self.language, beam_size=1, vad_filter=False,
                                       without_timestamps=True)[0])
        except Exception as e:  # noqa: BLE001  (CUDA DLL eksikse vb.)
            if device != "cpu":
                self._gpu_failed(e)
                return
            raise
        self.status(f"Whisper hazır: {self.model_name} ({self.device})")

    def _gpu_failed(self, err: Exception) -> None:
        self.status(f"⚠ Ekran kartı (CUDA) kullanılamadı → işlemciye (CPU) geçiliyor. GPU için install_gpu.bat. ({str(err)[:120]})")
        cpu_model = self.requested_model if self.requested_model != "auto" else "base.en"
        self._load(cpu_model, "cpu", "int8")

    def _run(self, audio16k: np.ndarray, prompt: str) -> str:
        segments, _info = self.model.transcribe(
            audio16k, language=self.language, beam_size=self.beam_size, vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 300}, condition_on_previous_text=False,
            initial_prompt=prompt or None, without_timestamps=True,
        )
        parts = []
        for seg in segments:
            if seg.no_speech_prob > 0.6 and seg.avg_logprob < -1.0:
                continue
            parts.append(seg.text.strip())
        return " ".join(p for p in parts if p).strip()

    def transcribe(self, audio16k: np.ndarray, prompt: str = "") -> str:
        try:
            return self._run(audio16k, prompt)
        except Exception as e:  # noqa: BLE001
            if self.device == "cpu":
                raise
            self._gpu_failed(e)
            return self._run(audio16k, prompt)


class GoogleTranscriber:
    name = "google"

    def __init__(self, language: str = "en-US", status: StatusCb = _noop):
        import speech_recognition as sr  # type: ignore
        self.sr = sr
        self.r = sr.Recognizer()
        self.language = language if "-" in language else "en-US"
        status("Google Speech (çevrimiçi) hazır.")

    def transcribe(self, audio16k: np.ndarray, prompt: str = "") -> str:
        pcm = (np.clip(audio16k, -1, 1) * 32767).astype(np.int16).tobytes()
        try:
            return self.r.recognize_google(self.sr.AudioData(pcm, 16000, 2), language=self.language)
        except self.sr.UnknownValueError:
            return ""


def make_transcriber(stt_cfg: dict, status: StatusCb = _noop):
    engine = stt_cfg.get("engine", "faster_whisper")
    errors = []
    if engine in ("faster_whisper", "auto"):
        try:
            return FasterWhisperTranscriber(stt_cfg.get("model", "auto"), stt_cfg.get("device", "auto"),
                                            stt_cfg.get("compute_type", "auto"), int(stt_cfg.get("beam_size", 1)),
                                            int(stt_cfg.get("cpu_threads", 4)), stt_cfg.get("language", "en"), status)
        except ImportError as e:
            errors.append(f"faster-whisper kurulu değil ({e})")
        except Exception as e:  # noqa: BLE001
            errors.append(f"faster-whisper: {e}")
    if engine == "google" or stt_cfg.get("google_fallback", True):
        try:
            return GoogleTranscriber(stt_cfg.get("language", "en"), status)
        except ImportError as e:
            errors.append(f"SpeechRecognition kurulu değil ({e})")
    raise RuntimeError("Konuşma tanıma başlatılamadı → " + " | ".join(errors))


# ============================================================================ orkestratör

class AudioListener:
    def __init__(self, audio_cfg: dict, stt_cfg: dict, on_text: Callable[[str, dict], None],
                 on_level: Callable[[float, bool], None] = _noop, on_status: StatusCb = _noop,
                 prompt_provider: Callable[[], str] = lambda: "", hallucinations: Optional[List[str]] = None):
        self.audio_cfg = audio_cfg
        self.stt_cfg = stt_cfg
        self.on_text = on_text
        self.on_level = on_level
        self.on_status = on_status
        self.prompt_provider = prompt_provider
        self.hallucinations = {h.lower().strip() for h in (hallucinations or [])}
        self.paused = False
        self._stop = threading.Event()
        self._segments: "queue.Queue[Tuple[np.ndarray, int, float]]" = queue.Queue()
        self._threads: List[threading.Thread] = []
        self.source: Optional[LoopbackSource] = None
        self.transcriber = None
        self.segmenter = VoiceSegmenter(
            threshold_db=float(audio_cfg.get("threshold_db", -48)), margin_db=float(audio_cfg.get("margin_db", 9)),
            frame_ms=int(audio_cfg.get("frame_ms", 30)), min_speech_ms=int(audio_cfg.get("min_speech_ms", 300)),
            end_silence_ms=int(audio_cfg.get("end_silence_ms", 650)), max_segment_s=float(audio_cfg.get("max_segment_s", 12)),
            pre_roll_ms=int(audio_cfg.get("pre_roll_ms", 300)), use_webrtcvad=bool(audio_cfg.get("use_webrtcvad", True)))

    def start(self) -> None:
        self.source = make_source(self.audio_cfg.get("backend", "auto"), self.audio_cfg.get("device_name", ""),
                                  int(self.audio_cfg.get("frame_ms", 30)), self.on_status)
        self.source.start()
        self.on_status(f"🎧 Dinleniyor: {self.source.description}")
        for target, name in ((self._capture_loop, "seg"), (self._stt_loop, "stt")):
            t = threading.Thread(target=target, name=f"audio-{name}", daemon=True)
            t.start()
            self._threads.append(t)

    def stop(self) -> None:
        self._stop.set()
        if self.source:
            try:
                self.source.stop()
            except Exception:
                pass

    def _capture_loop(self) -> None:
        last_level = 0.0
        idle_ms = int(self.audio_cfg.get("end_silence_ms", 650))
        while not self._stop.is_set():
            try:
                chunk, rate = self.source.out.get(timeout=0.1)
            except queue.Empty:
                seg = self.segmenter.flush_if_idle(idle_ms)
                if seg is not None:
                    self._segments.put((seg[0], seg[1], time.time()))
                continue
            if self.paused:
                continue
            for audio, sr in self.segmenter.feed(chunk, rate):
                self._segments.put((audio, sr, time.time()))
            now = time.time()
            if now - last_level > 0.1:
                last_level = now
                self.on_level(self.segmenter.last_level_db, self.segmenter.in_speech)

    def _stt_loop(self) -> None:
        try:
            self.transcriber = make_transcriber(self.stt_cfg, self.on_status)
        except Exception as e:  # noqa: BLE001
            self.on_status(f"❌ {e}")
            return
        while not self._stop.is_set():
            try:
                audio, sr, t_end = self._segments.get(timeout=0.2)
            except queue.Empty:
                continue
            backlog = self._segments.qsize()
            if backlog > 3:
                self.on_status(f"⚠ STT gecikiyor ({backlog} parça kuyrukta). Daha küçük model seçin.")
            audio16 = resample(audio, sr, 16000)
            dur = len(audio16) / 16000.0
            t0 = time.time()
            try:
                text = self.transcriber.transcribe(audio16, self.prompt_provider())
            except Exception as e:  # noqa: BLE001
                self.on_status(f"STT hatası: {e}")
                continue
            text = (text or "").strip()
            if not text or not any(c.isalpha() or c.isdigit() for c in text):
                continue
            if text.lower() in self.hallucinations and dur < 2.5:
                continue
            self.on_text(text, {"duration": dur, "latency": time.time() - t_end, "stt_seconds": time.time() - t0})
