"""Gating for tests that record where the SDK departs from a specification."""

import os

import pytest

RUN_DEVIATIONS = 'RUN_DEVIATIONS'

deviation = pytest.mark.skipif(
    not os.environ.get(RUN_DEVIATIONS),
    reason=f'Departs from the specification; see test/uts/deviations.md. Set {RUN_DEVIATIONS}=1 to run.',
)

spec_error = pytest.mark.skipif(
    not os.environ.get(RUN_DEVIATIONS),
    reason=(
        'The specification is at fault, not the SDK; see test/uts/spec-inconsistencies.md. '
        f'Set {RUN_DEVIATIONS}=1 to run.'
    ),
)
