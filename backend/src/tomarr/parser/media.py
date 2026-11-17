import re
from itertools import pairwise

from tomarr.parser.release import UnparseableReason

_TOKEN = re.compile(r"[a-z0-9]+")
_EPISODE = re.compile(r"s\d{1,2}e\d{1,4}")
_RESOLUTION = re.compile(r"\d{3,4}p|\d{3,4}x(?:480|576|720|1080|1440|2160)")
# `avi` is also a given name, so only the file extension counts.
_AVI_EXTENSION = re.compile(r"\.\s?avi\s*\Z")

_VIDEO_TOKENS = frozenset(
    {
        "4k",
        "av1",
        "avc",
        "bdmv",
        "bdremux",
        "bdrip",
        "bluray",
        "brrip",
        "divx",
        "dub",
        "dubbed",
        "dvdrip",
        "h264",
        "h265",
        "hdtv",
        "hevc",
        "lektor",
        "m2ts",
        "mkv",
        "mp4",
        "remux",
        "subs",
        "webdl",
        "webrip",
        "x264",
        "x265",
        "xvid",
    }
)

# Names split on punctuation, so `WEB-DL`, `Blu-Ray` and `H.264` arrive as two tokens.
_VIDEO_PAIRS = frozenset(
    {
        ("web", "dl"),
        ("blu", "ray"),
        ("h", "264"),
        ("h", "265"),
        ("x", "264"),
        ("x", "265"),
        ("dual", "audio"),
        ("multi", "audio"),
        ("sub", "eng"),
        ("music", "video"),
        ("audio", "description"),
        ("full", "animation"),
    }
)

# Music shares the audiobook reason: it is audio too, and MP3 names either.
_AUDIO_TOKENS = frozenset({"audiobook", "m4a", "m4b", "mp3", "flac", "ost", "soundtrack"})

_GAME_TOKENS = frozenset({"dlc", "dlcs", "repack"})


def rejection_reason(name: str) -> UnparseableReason | None:
    lowered = name.lower()
    tokens = _TOKEN.findall(lowered)
    if (
        any(_is_video_token(token) for token in tokens)
        or any(pair in _VIDEO_PAIRS for pair in pairwise(tokens))
        or _AVI_EXTENSION.search(lowered)
    ):
        return UnparseableReason.VIDEO
    if any(token in _AUDIO_TOKENS for token in tokens):
        return UnparseableReason.AUDIOBOOK
    if any(token in _GAME_TOKENS for token in tokens):
        return UnparseableReason.GAME
    return None


def _is_video_token(token: str) -> bool:
    return (
        token in _VIDEO_TOKENS
        or _EPISODE.fullmatch(token) is not None
        or _RESOLUTION.fullmatch(token) is not None
    )
