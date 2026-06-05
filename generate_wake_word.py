"""
Batch-generate wake-phrase audio: \"OK Freebox\" with many different TTS voices.

Uses Microsoft Edge TTS (edge-tts, no API key). Outputs 16 kHz mono PCM WAV
(common for wake-word / keyword spotting corpora).

English Neural speakers on Edge are limited (~47). To reach 100 clips, this
script reuses the same speaker with small rate/pitch adjustments (still
natural / \"standard\" sounding). See manifest.json for each clip's voice
and prosody.

Usage:
  pip install -r requirements.txt
  python generate_ok_freebox_corpus.py
  python generate_ok_freebox_corpus.py --count 100 --out ./ok_freebox_corpus
  python generate_ok_freebox_corpus.py --text "OK Homa" --out ./ok_homa_corpus
  python generate_ok_freebox_corpus.py --text "MAGENTA" --count 50 --start-index 151 --out ./magenta
  # WAV names follow the phrase: ok_homa_001.wav … (override with --prefix my_label)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import edge_tts
import imageio_ffmpeg
from edge_tts.exceptions import NoAudioReceived

# Phrase as spoken (capitalization helps TTS articulate clearly).
DEFAULT_TEXT = "OK Freebox"

# 16 kHz mono WAV — typical for on-device keyword models.
SAMPLE_RATE = 16000
CHANNELS = 1

# Subtle prosody layers so clips stay \"standard\" but differ slightly.
PROSODY_LAYERS: list[tuple[str, str]] = [
    ("+0%", "+0Hz"),
    ("-4%", "+0Hz"),
    ("+4%", "+0Hz"),
    ("+0%", "-2Hz"),
    ("+0%", "+2Hz"),
    ("-3%", "-2Hz"),
    ("+3%", "+2Hz"),
]

# Used when a voice returns no audio (throttling, retired voice, region limits).
FALLBACK_VOICE = "en-US-AriaNeural"
MAX_ATTEMPTS_PER_VOICE = 5
RETRY_BACKOFF_SEC = (0.8, 1.6, 3.2, 6.4, 12.0)
CLIP_GAP_SEC = 0.45


def _configure_unbuffered_stdio() -> None:
    """子进程管道模式下强制行缓冲，便于主界面实时显示生成日志。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(line_buffering=True, write_through=True)
        except Exception:
            try:
                stream.reconfigure(line_buffering=True)
            except Exception:
                pass


def _log(msg: str, *, err: bool = False) -> None:
    stream = sys.stderr if err else sys.stdout
    print(msg, file=stream, flush=True)


async def move_wav_to_output(src: Path, dst: Path) -> None:
    """
    Move synthesized WAV into the corpus folder. On Windows, os.replace / rename
    in the same folder as the ffmpeg output can raise PermissionError while
    handles or AV scanners release the file; temp-dir + move + retries avoids that.
    """
    dst.parent.mkdir(parents=True, exist_ok=True)
    last_err: OSError | None = None
    for attempt in range(12):
        try:
            if dst.exists():
                dst.unlink()
            shutil.move(str(src), str(dst))
            return
        except PermissionError as e:
            last_err = e
            await asyncio.sleep(0.08 * (attempt + 1))
    raise PermissionError(
        f"Could not move {src} -> {dst} after retries: {last_err}"
    ) from last_err


def _ffmpeg() -> str:
    return imageio_ffmpeg.get_ffmpeg_exe()


def mp3_bytes_to_wav(mp3_path: Path, wav_path: Path) -> None:
    ffmpeg = _ffmpeg()
    cmd = [
        ffmpeg,
        "-y",
        "-i",
        str(mp3_path),
        "-ac",
        str(CHANNELS),
        "-ar",
        str(SAMPLE_RATE),
        "-f",
        "wav",
        str(wav_path),
    ]
    kwargs = {
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
    }
    if platform.system() == "Windows":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        kwargs["startupinfo"] = startupinfo
    r = subprocess.run(cmd, **kwargs)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {r.stderr or r.stdout}")


def corpus_file_prefix(phrase: str) -> str:
    """
    Build a safe WAV basename prefix from spoken text or a user label, e.g.
    \"OK Freebox\" -> ok_freebox, \"OK Homa\" -> ok_homa.
    """
    s = phrase.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s, flags=re.ASCII)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "corpus"


def pick_english_neural_voices(voices: list[dict]) -> list[str]:
    """Prefer en-* voices whose ShortName uses Neural (clear English)."""
    out: list[str] = []
    for v in voices:
        locale = (v.get("Locale") or "").lower()
        short = v.get("ShortName") or ""
        if locale.startswith("en") and "Neural" in short:
            out.append(short)
    return sorted(set(out))


def plan_clips(voice_names: list[str], count: int) -> list[tuple[str, str, str]]:
    """Map clip index -> (voice, rate, pitch). Cycles voices, then prosody layers."""
    if not voice_names:
        return []
    planned: list[tuple[str, str, str]] = []
    for i in range(count):
        voice = voice_names[i % len(voice_names)]
        layer = (i // len(voice_names)) % len(PROSODY_LAYERS)
        rate, pitch = PROSODY_LAYERS[layer]
        planned.append((voice, rate, pitch))
    return planned


async def _save_tts_to_wav(
    text: str,
    voice: str,
    rate: str,
    pitch: str,
    wav_path: Path,
) -> None:
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        await communicate.save(str(tmp_path))
        mp3_bytes_to_wav(tmp_path, wav_path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


async def synthesize_one(
    text: str,
    voice: str,
    rate: str,
    pitch: str,
    wav_path: Path,
) -> tuple[str, str | None]:
    """
    Returns (voice_used, note_or_none). note set when FALLBACK_VOICE was used.
    """
    last_err: BaseException | None = None
    for attempt in range(MAX_ATTEMPTS_PER_VOICE):
        try:
            await _save_tts_to_wav(text, voice, rate, pitch, wav_path)
            return voice, None
        except NoAudioReceived as e:
            last_err = e
            if attempt < MAX_ATTEMPTS_PER_VOICE - 1:
                wait = RETRY_BACKOFF_SEC[min(attempt, len(RETRY_BACKOFF_SEC) - 1)]
                _log(
                    f"    NoAudioReceived for {voice} (try {attempt + 1}/{MAX_ATTEMPTS_PER_VOICE}), "
                    f"sleep {wait:.1f}s ...",
                    err=True,
                )
                await asyncio.sleep(wait)

    _log(
        f"    Retries exhausted for {voice}; trying fallback {FALLBACK_VOICE} ...",
        err=True,
    )
    for attempt in range(3):
        try:
            await _save_tts_to_wav(text, FALLBACK_VOICE, rate, pitch, wav_path)
            return FALLBACK_VOICE, f"fallback_after_NoAudioReceived:{voice}"
        except NoAudioReceived as e:
            last_err = e
            await asyncio.sleep(RETRY_BACKOFF_SEC[min(attempt + 2, len(RETRY_BACKOFF_SEC) - 1)])

    raise RuntimeError(f"TTS failed for {voice} and fallback {FALLBACK_VOICE}: {last_err!r}")


async def main_async(args: argparse.Namespace) -> int:
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    start_index = max(1, int(args.start_index or 1))

    voices = await edge_tts.list_voices()
    if isinstance(voices, str):
        voices = json.loads(voices)
    voice_names = pick_english_neural_voices(voices)
    if not voice_names:
        _log("No English neural voices returned from edge-tts.", err=True)
        return 1

    if args.count > len(voice_names):
        _log(
            f"Note: {len(voice_names)} distinct English neural speakers; "
            f"extra clips use small rate/pitch changes (see manifest).",
            err=True,
        )

    plan = plan_clips(voice_names, args.count)
    manifest = []
    text = args.text
    file_prefix = corpus_file_prefix(args.prefix) if args.prefix else corpus_file_prefix(text)

    end_index = start_index + len(plan) - 1
    width = max(3, len(str(end_index)))
    for seq, (voice, rate, pitch) in enumerate(plan, start=1):
        clip_index = start_index + seq - 1
        tmp_wav = Path(tempfile.gettempdir()) / f"_{file_prefix}_{os.getpid()}_{clip_index:03d}.wav"
        _log(f"[{seq}/{len(plan)}] index={clip_index} planned={voice} {rate} {pitch} ...")
        voice_used, note = await synthesize_one(text, voice, rate, pitch, tmp_wav)
        # Short filenames: {prefix}_001.wav … details in manifest.json
        fname = f"{file_prefix}_{clip_index:0{width}d}.wav"
        wav_path = out_dir / fname
        await move_wav_to_output(tmp_wav, wav_path)
        _log(f"    -> {fname}" + (f"  [{note}]" if note else ""))
        entry: dict = {
            "index": clip_index,
            "voice": voice_used,
            "rate": rate,
            "pitch": pitch,
            "file": fname,
            "text": text,
        }
        if voice_used != voice:
            entry["voice_planned"] = voice
        if note:
            entry["note"] = note
        manifest.append(entry)
        await asyncio.sleep(CLIP_GAP_SEC)

    manifest_path = out_dir / "manifest.json"
    old_manifest = []
    if manifest_path.exists():
        try:
            old = json.loads(manifest_path.read_text(encoding="utf-8"))
            if isinstance(old, list):
                old_manifest = [x for x in old if isinstance(x, dict)]
        except Exception:
            old_manifest = []
    merged = {}
    for row in old_manifest + manifest:
        try:
            idx = int(row.get("index", 0) or 0)
        except Exception:
            idx = 0
        if idx > 0:
            merged[idx] = row
    final_manifest = [merged[k] for k in sorted(merged.keys())]
    manifest_path.write_text(json.dumps(final_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    _log(
        f"Done. Wrote {len(manifest)} WAV files "
        f"(index {start_index}..{end_index}) and merged {manifest_path.name} -> {len(final_manifest)} entries."
    )
    return 0


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate OK Freebox TTS corpus (many voices).")
    p.add_argument("--count", type=int, default=100, help="Number of clips (default 100).")
    p.add_argument(
        "--start-index",
        type=int,
        default=1,
        help="Start index for output filenames/manifest (default 1). Example: 151 for continuing 151~200.",
    )
    p.add_argument("--out", type=str, default="ok_freebox_corpus", help="Output directory.")
    p.add_argument(
        "--text",
        type=str,
        default=DEFAULT_TEXT,
        help=f'Spoken phrase (default: "{DEFAULT_TEXT}").',
    )
    p.add_argument(
        "--prefix",
        type=str,
        default="",
        help="WAV basename prefix (default: derived from --text, e.g. OK Homa -> ok_homa).",
    )
    return p.parse_args(argv)


def cli_main(argv=None) -> int:
    """命令行入口：供 main.py --wake-corpus-worker 或独立脚本调用。"""
    _configure_unbuffered_stdio()
    return int(asyncio.run(main_async(parse_args(argv))) or 0)


if __name__ == "__main__":
    sys.exit(cli_main())
