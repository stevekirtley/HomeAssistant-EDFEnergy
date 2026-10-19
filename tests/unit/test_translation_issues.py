"""Every repair issue has to be either fixable or static, not both.

hassfest treats `description` and `fix_flow` as mutually exclusive on an issue - a fixable
one says what it needs inside its flow rather than twice - and rejects the manifest with
"two or more values in the same group of exclusion 'fixable'". That failed the release
validation for 20.1.0 and is an easy thing to do again, so it is checked here where it costs
nothing rather than waiting for the CI run after a tag has been pushed.
"""
import json
from pathlib import Path

import pytest

TRANSLATIONS = Path("custom_components/edf_energy/translations/en.json")


def _issues():
  return json.loads(TRANSLATIONS.read_text())["issues"]


def test_the_translations_file_is_readable():
  assert _issues(), "no issues found, so the checks below would pass vacuously"


@pytest.mark.parametrize("issue_id", sorted(_issues()))
def test_an_issue_is_fixable_or_static_but_not_both(issue_id):
  issue = _issues()[issue_id]
  has_description = "description" in issue
  has_fix_flow = "fix_flow" in issue

  assert has_description or has_fix_flow, f"{issue_id} says nothing at all"
  assert not (has_description and has_fix_flow), (
    f"{issue_id} has both a description and a fix_flow; hassfest refuses that. Put the "
    f"wording in the flow's step and drop the description."
  )


@pytest.mark.parametrize("issue_id", sorted(_issues()))
def test_every_issue_has_a_title(issue_id):
  assert _issues()[issue_id].get("title"), f"{issue_id} has no title"
