import unicodedata


def normalize_name(text: str) -> str:
    """Return the Alias dedupe key for a name.

    Casefolding can leave a string that is no longer NFKC, so the form is applied again after it.
    Punctuation is kept, so ``Re:Zero`` and ``Re Zero`` stay two names.
    """
    folded = unicodedata.normalize("NFKC", unicodedata.normalize("NFKC", text).casefold())
    return " ".join(folded.split())
