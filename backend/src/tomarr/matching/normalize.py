import unicodedata


def normalize_name(text: str) -> str:
    """Return the Alias dedupe key for a name.

    Casefolding can leave a string that is no longer NFKC, so the form is applied again after it.
    Punctuation is kept, so ``Re:Zero`` and ``Re Zero`` stay two names. Invisible format
    characters (Unicode category Cf, such as zero-width space, BOM and soft hyphen) are
    dropped, since NFKC keeps them and they are not whitespace.
    """
    folded = unicodedata.normalize("NFKC", unicodedata.normalize("NFKC", text).casefold())
    visible = "".join(char for char in folded if unicodedata.category(char) != "Cf")
    return " ".join(visible.split())
