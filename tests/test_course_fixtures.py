from __future__ import annotations

import csv
import io

from tests.course_fixtures import CSV_HEADER, csv_row


def test_csv_row_round_trips_through_csv_dictreader():
    text = CSV_HEADER + "\n" + csv_row(item_no=1, item_text="Hello.") + "\n"
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    assert len(rows) == 1
    assert rows[0]["item_no"] == "1"
    assert rows[0]["item_text"] == "Hello."
    assert set(rows[0].keys()) == set(CSV_HEADER.split(","))
