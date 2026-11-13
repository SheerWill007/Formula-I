import hashlib

from ingestion import headshots

PLACEHOLDER = b"placeholder-image"
REAL = b"x" * 5000


def test_candidates_follow_the_cdn_naming():
    first = next(headshots.candidates("Max Verstappen", "VER"))
    assert first.endswith(
        "/M/MAXVER01_Max_Verstappen/maxver01.png.transform/4col/image.png"
    )


def test_accents_are_stripped():
    url = next(headshots.candidates("Nico Hülkenberg", "HUL"))
    assert "NICHUL01_Nico_Hulkenberg" in url


def test_known_longer_first_name_is_used():
    url = next(headshots.candidates("Kimi Antonelli", "ANT"))
    assert "ANDANT01_Andrea%20Kimi_Antonelli" in url


def test_family_name_first_is_tried_last():
    urls = list(headshots.candidates("Guanyu Zhou", "ZHO"))
    assert "GUAZHO01_Guanyu_Zhou" in urls[0]
    assert "ZHOGUA01_Zhou_Guanyu" in urls[-1]


def test_single_word_names_give_no_candidates():
    assert list(headshots.candidates("Madonna")) == []


def test_upsize_swaps_the_thumbnail_size():
    thumb = "https://media.formula1.com/x/y.png.transform/1col/image.png"
    assert headshots.upsize(thumb).endswith("/4col/image.png")
    assert headshots.upsize(None) is None


def test_the_cdn_placeholder_is_rejected_and_the_next_guess_tried():
    good = {}

    def fetch(url):
        if "ZHOGUA01" in url:
            return REAL
        return PLACEHOLDER * 400  # large enough to pass the size check

    digest = hashlib.md5(PLACEHOLDER * 400).hexdigest()
    url = headshots.resolve("Guanyu Zhou", "ZHO", fetch=fetch, placeholder=digest)
    assert url and "ZHOGUA01" in url, good


def test_no_real_image_means_none():
    digest = hashlib.md5(PLACEHOLDER * 400).hexdigest()
    assert (
        headshots.resolve(
            "Not Real", fetch=lambda _u: PLACEHOLDER * 400, placeholder=digest
        )
        is None
    )
    assert headshots.resolve("Not Real", fetch=lambda _u: None, placeholder=digest) is None
