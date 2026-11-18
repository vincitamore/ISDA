# nonascii-word-coverage

**Role.** The tokenizer-coverage specimen: prose dense in non-ASCII letters, where a word pattern limited to ASCII would drop every accented word from the count.

**Topic and source.** A short essay on loanwords retaining their diacritics, written for this corpus. The scripts are space-delimited only: accented Latin (French, Spanish, German, Swedish, Polish, Portuguese, Vietnamese, Turkish), Greek, Cyrillic. CJK is absent because an unsegmented script makes "words within 10% of whitespace tokens" false by construction, and the claim under test is about non-ASCII *letters* being counted, not about segmentation.

**Telos.** *Explain to a general reader why borrowed words keep their accents.* **Substrate:** public.

**Ledger.** Scored against the measured 1,878 bytes. Rhetorica-Selected dominant: the piece's work is choosing and ordering examples across languages, and every fact is retrievable. Musica-Selected minor: the food-list cadences are a chosen device from a known inventory.

**Measured.** 307 prose words against 305 whitespace tokens (ratio 1.007). The assertion band is ±10% of the token count.
