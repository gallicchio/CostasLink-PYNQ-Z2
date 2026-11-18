# Design reviews of rev A

Every review the design had before it was ordered, each in its reviewer's directory, as received.
The brief the reviewers worked from is [`../DESIGN_REVIEW_PROMPT.md`](../DESIGN_REVIEW_PROMPT.md);
what was done about each finding is [`../DESIGN_REVIEW_RESPONSE.md`](../DESIGN_REVIEW_RESPONSE.md).

| directory | reviewer | reviewed |
|---|---|---|
| [`Claude/`](Claude/) | the author's own self-review (2026-10-09) | an early build, before the brief |
| [`Gemini3.8Flash/`](Gemini3.8Flash/) | Gemini 3.8 Flash | build 17 |
| [`GPT-5.6Terra/`](GPT-5.6Terra/) | GPT-5.6 Terra | build 17 |
| [`Grok4.7/`](Grok4.7/) | Grok 4.7 | build 17 |
| [`KimiK3/`](KimiK3/) | Kimi K3 | build 17 |
| [`Claude_Prompt31/`](Claude_Prompt31/) | three independent reviews by fresh Claude agents (2026-10-14) | build 33, the routed board before the order |

Reading them:

- **Old paths.** Until the public release these directories were `design_review_<name>/` at the top of the
  project. The reports, the chat logs and the commit history use those names.
- **No datasheets.** The reviewers' copies of vendor datasheets (PDFs, their text, renders of their pages) are
  not published: they are the vendors' copyright. A report that cites `build/txt/<part>.txt` or one of its own
  datasheet crops is citing the vendor's datasheet; `tools/jlc_datasheet.py` and `tools/adi_datasheet.py`
  fetch them.
- **`<name>/repo/`** is a reviewer's private working copy of the project. It is not in git.
