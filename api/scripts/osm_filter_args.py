"""AI-CONTEXT: prints the osmium `tags-filter` selectors for `make osm-extract`.

The Makefile used to carry its own hand-kept copy of this list, and it drifted from
the ingest rules completely — six of eight service rules read tags the extract never
passed, so they had never fired. This exists so there is one list and the extract is
rendered FROM the rules rather than kept beside them.
"""

from app.foundation.f02_facility.domain.ingest.adapters import osm_extract_filter_args


def main() -> None:
    print(" ".join(osm_extract_filter_args()))


if __name__ == "__main__":
    main()
