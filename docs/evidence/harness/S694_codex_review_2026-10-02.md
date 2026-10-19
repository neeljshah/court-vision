- **S694 -- HOLD.** A raw decode failure returns no event and leaves an already valid book quoteable (`book_stream.py:154-164`; `book_stream.py:89-102`). A malformed known-ticker delta with duplicate `seq` keys is tested only for an empty event list (`test_book_stream.py:234`). Fail closed when malformed book data cannot be safely routed, and assert that the quote gate refuses it.

| S694 | HOLD | None | Malformed frame leaves book valid | M |
