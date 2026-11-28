from pydantic import TypeAdapter

from tomarr.services.settings import registry

# Stored as plain text, like every setting (ADR 0008).
GOOGLE_BOOKS_API_KEY = registry.declare("google_books.api_key", TypeAdapter(str), "")
