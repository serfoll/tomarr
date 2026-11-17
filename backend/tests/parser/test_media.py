# ruff: noqa: E501
# Release names are copied verbatim from the raw corpus, so some lines run long.
import pytest

from tomarr.parser.media import rejection_reason
from tomarr.parser.release import UnparseableReason

VIDEO = UnparseableReason.VIDEO
AUDIOBOOK = UnparseableReason.AUDIOBOOK
GAME = UnparseableReason.GAME

VIDEO_NAMES = [
    # SxxExx, with and without a range
    "Blue Box S02E01 Deja Vu 1080p NF WEB-DL DUAL DDP5.1 H.264-VARYG (Ao no Hako Season 2, Dual-Audio, Multi-Subs)",
    "Solo Leveling S02e01-13 [720p Ita Eng Spa Jap SubS] byMe7alh [MIRCrew]",
    "One Piece (2000) Remastered s01e31-45 [Mkv-1080p H264-MultiLang Aac 2.0-MultiSub",
    # resolution
    "Demon Slayer Kimetsu no Yaiba Infinity Castle 2025 REPACK3 720p CR WEB-DL D",
    "Monster (Naoki Urasawa anime) 960p dvd upscale",
    "Demon Slayer: Kimetsu no Yaiba Infinity Castle 4K",
    "Naoki Urasawa's Monster (2004-2005) BD-Remux 1080P ENG",
    # codec
    "Blue Box S02E03 1080p HEVC x265-MeGusta",
    "Blue Box S02E01 MULTi 1080p NF WEB-DL DDP5.1 AV1-Tsundere-Raws (VF, FRENCH, SUBFRENCH, VOSTFR, Ao no Hako Season 2, Blue Box Season 2)",
    "[CRUCiBLE] DAN DA DAN S2 (S02) (BD Remux 1080p FLAC H.264) [Dual Audio] | DanDaDan 2nd Season S2 | ダンダダン 第2期",
    "LEGO ONE PIECE S01 1080p NF WEB-DL DDP5 1 Atmos H 264-playWEB",
    "Blue Box S02E01 MULTi 1080p NF WEB-DL DDP5.1 H.265-Tsundere-Raws (VF, FRENCH, SUBFRENCH, VOSTFR, Ao no Hako Season 2, Blue Box Season 2)",
    # source
    "Gekijo-ban Kimetsu No Yaiba Mugen Jo-hen (2025) 720p WEBRip-WORLD",
    "Kimetsu no Yaiba Movie: Infinity Castle (1080p BDRip AV1 EAC3) [Anime Land]",
    "[PMR] [BDMV][Witch Hat Atelier][Vol.1][JPN]",
    "[PMR] S01 [BDMV][Witch Hat Atelier][Vol.2][JPN]",
    "Fullmetal Alchemist + OVA (High Quality)(Tri Audio) MKV [1080p] Blu-Ray Rip (Debanded Version)",
    "Jujutsu.Kaisen.S01.2160p.HDTV.MULTi.AAC.2.0.8bit.x264-NAKO",
    "Demon Slayer Kimetsu no Yaiba The Movie Mugen Train 2020 1080p BD (Audio Multi-Español, Sub Español) (Multi-Audio Spanish, Spanish Subbed)",
    # separators other than spaces
    "Demon.Slayer.Kimetsu.No.Yaiba.Infinity.Castle.2025.720p.WEB.H264-SKYFiRE",
    "[Kashikoi]_Dandadan_S2_-_01~12_ [WebRip_1080p_x264_10bit_AAC][Sub_Esp][MP4]",
    "[shincaps] Tongari Boushi no Atelier - 13 (BS11 1920x1080 MPEG2 AAC).ts",
    "Chi. Chikyuu no Undou ni Tsuite - Orb On the Movements of the Earth [BDRemux]",
    "[Exiled-Destiny] Fullmetal Alchemist Brotherhood [Dual Audio]",
    "[Furretar] 台中粤配 - 胆大党 (Dandadan) (S1-2) (Mainland + Taiwanese Mandarin + Cantonese Chinese Dub) (Matching Soft Subs) [國語][粵語][国语][中配版] (膽大黨)",
    # container only
    "[Fansly] Octokuro Seiko Ayase Cosplay DANDADAN (2026)[720p][x264][xFans].mp4",
]

# One marker per name, so removing any single token or pair from the matcher fails a case.
# The titles are synthetic; the markers are spelled as they appear in real names.
SINGLE_VIDEO_MARKERS = [
    "S02E03",
    "s01e31-45",
    "S1E5",
    "480p",
    "720p",
    "1080P",
    "2160p",
    "960p",
    "1280x720",
    "1920x1080",
    "4K",
    "x264",
    "x265",
    "H264",
    "H265",
    "H.264",
    "H.265",
    "H 264",
    "HEVC",
    "AV1",
    "AVC",
    "XviD",
    "DivX",
    "WEBDL",
    "WEB-DL",
    "WEB DL",
    "WEBRip",
    "BDRip",
    "BDRemux",
    "BD-Remux",
    "Remux",
    "BDMV",
    "BluRay",
    "Blu-Ray",
    "DVDRip",
    "HDTV",
    "MKV",
    "MP4",
    "Dual Audio",
    "Dual-Audio",
    "Multi-Audio",
    "Multi-Subs",
    "Soft Subs",
    "Dub",
    "DUBBED",
    "SUBS",
    "Lektor",
    "sub eng",
    "Music Video",
    "Audio Description",
    "Full Animation",
]

AUDIOBOOK_NAMES = [
    "Omniscient Reader's Viewpoint, Vol. 1 by singNsong [ENG / M4B]",
    "Doctor Who: Short Trips - Blue Boxes by Erin Horakova [ENG / MP3]",
    "Omniscient Reader's Viewpoint, Vol. 1 [Audiobook] [Yen Audio]",
    "The Beginning After The End, Book 12 - Apotheosis (Audiobook) [Troglodyte]",
]

# Music is refused with the audiobook reason: it is audio, and MP3 already covers both.
SINGLE_AUDIO_MARKERS = ["M4B", "MP3", "Audiobook", "FLAC", "OST", "Original Soundtrack"]

SINGLE_GAME_MARKERS = ["DLC", "DLCs", "REPACK"]

COMIC_NAMES = [
    "Jujutsu Kaisen, Vol. 27 by Viz Media, Gege Akutami [ENG / CBZ]",
    "One Piece 1190 (Digital)",
    "2001 Nights, Vol. 1 (Digital) (Yuki Kuji)",
    "Monster - Naoki Urasawa (1995-2001) [CBZ ITA] [1,85GB] [ImFilippo]",
    "Monster: The Perfect Edition, Vol. 01-09 (2014-2016) (Scan) (HQ) by Naoki Urasawa [ENG / CBZ]",
    "ONE PIECE magazine Vol.1-17",
    "ONE PIECE カラー版 105巻 ONE PIECE Volume 105 Colour",
    "Solo Leveling, Vol.1 - Vol.13 by DUBU [ENG / CBZ]",
    "Solo Leveling #151-179 (Webtoon, 2021-2022) by Dubo [ENG / CBZ]",
]

NOT_WHOLE_TOKENS = [
    "Bluebox Vol. 1 (Digital)",
    "Sp1080 Chapter 4",
    "Fort1080p Chapter 4",
    "Axe264 Vol. 2",
    "Cubes01e02 Vol. 3",
    "Webdlike Vol. 5",
    "Mp3player Chapter 9",
    "Hevcast Chapter 9",
    "Fort1920x1080 Vol. 2",
    "Mydual Audio Vol. 2",
    "Dubai Detective Vol. 2",
    "Subspace Chapter 4",
    "Ghost Hunt Vol. 3",
    "Flacco Chapter 2",
    "Repackaged Hearts Vol. 2",
    "Blue Box, Vol. 5 by Kouji Miura [ENG / CBZ]",
]


@pytest.mark.parametrize("name", VIDEO_NAMES)
def test_video_name_is_rejected_as_video(name: str) -> None:
    assert rejection_reason(name) == VIDEO


@pytest.mark.parametrize("marker", SINGLE_VIDEO_MARKERS)
def test_a_single_video_marker_is_enough_to_reject(marker: str) -> None:
    assert rejection_reason(f"Some Title Vol. 3 [{marker}]") == VIDEO


@pytest.mark.parametrize("name", AUDIOBOOK_NAMES)
def test_audiobook_name_is_rejected_as_audiobook(name: str) -> None:
    assert rejection_reason(name) == AUDIOBOOK


@pytest.mark.parametrize("marker", SINGLE_AUDIO_MARKERS)
def test_a_single_audio_marker_is_enough_to_reject(marker: str) -> None:
    assert rejection_reason(f"Some Title Vol. 3 [{marker}]") == AUDIOBOOK


@pytest.mark.parametrize("marker", SINGLE_GAME_MARKERS)
def test_a_single_game_marker_is_enough_to_reject(marker: str) -> None:
    assert rejection_reason(f"Some Title (v1.83 & {marker})") == GAME


def test_audio_marker_wins_over_game_marker() -> None:
    assert rejection_reason("Some Title OST (All DLCs)") == AUDIOBOOK


@pytest.mark.parametrize("name", COMIC_NAMES)
def test_comic_name_passes_through(name: str) -> None:
    assert rejection_reason(name) is None


@pytest.mark.parametrize("name", NOT_WHOLE_TOKENS)
def test_marker_inside_a_longer_word_does_not_reject(name: str) -> None:
    assert rejection_reason(name) is None


def test_video_marker_wins_over_audio_marker() -> None:
    assert rejection_reason("Blue Box S01E01 1080p FLAC [Audiobook]") == VIDEO
