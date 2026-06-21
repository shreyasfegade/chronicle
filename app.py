"""Chronicle launcher.

A thin entry point so ``python app.py`` keeps working. All logic lives in the
``chronicle`` package; this just hands off to it. Equivalent to
``python -m chronicle``.
"""

from chronicle.app import main

if __name__ == "__main__":
    main()
