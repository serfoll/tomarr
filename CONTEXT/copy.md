# Tomarr copy rules

Applies to anything a person reads: `.md` documents written for people, UI text, README and docs, PR descriptions and commit messages.

- Run it through the `/humanizer` skill before finalizing. It catches AI-writing tells: inflated vocabulary, em-dash overuse, rule-of-three padding, hedging filler and the rest.
- Never mention Claude, AI, or that something was written by an assistant in code comments, commit messages, GitHub issues or PR descriptions. Write it as a person would.
- This doesn't apply to product copy about Tomarr's own Gemini features. Those describe a feature the user turns on, and should say plainly what is sent to Google and what isn't.

## UI text

- Sentence case everywhere, including buttons and headings.
- Buttons start with a verb and name the action ("Search monitored", "Lock mapping"), never "OK" or "Submit".
- Every rejection and error says what happened and what to do next ("Language not in profile. Add Japanese to the quality profile or override this release.").
- Use the glossary terms from `CONTEXT/CONTEXT.md` exactly. A Volume is never called a book in one place and a tankōbon in another.
- No exclamation marks.
