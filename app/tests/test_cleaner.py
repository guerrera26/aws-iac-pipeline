"""Unit tests for the CSV cleaning engine. Pure pandas, no database needed."""
import csv
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import cleaner


def run(csv_text, **options):
    return cleaner.clean_csv(csv_text, options)


def rows(result):
    """The cleaned CSV parsed back into a list of rows."""
    return list(csv.reader(io.StringIO(result["cleaned_csv"])))


def column(result, index=0):
    """One column of the cleaned CSV, without its header."""
    return [r[index] for r in rows(result)[1:]]


def step_count(result, step_id):
    return next(s["count"] for s in result["steps"] if s["id"] == step_id)


# ── headers, whitespace, placeholders, blank rows ──

def test_headers_are_normalized_and_deduplicated():
    result = run("First Name,E-mail,,First Name\nA,b,c,d\n")
    assert result["columns"] == ["first_name", "e_mail", "column_3", "first_name_2"]
    assert result["original_columns"] == ["First Name", "E-mail", "", "First Name"]


def test_trims_and_collapses_whitespace():
    assert column(run("note\n  hello    world  \n")) == ["hello world"]


def test_placeholders_become_blank_but_real_values_survive():
    result = run("a,b\nN/A,none\n-,?\n-5,None of the above\n")
    # The first two rows are nothing but placeholders, so they end up blank and drop out.
    assert rows(result) == [["a", "b"], ["-5", "None of the above"]]
    assert step_count(result, "remove_blank_rows") == 2


def test_blank_rows_and_comma_only_rows_are_removed():
    result = run("a,b\n1,2\n\n,\n3,4\n")
    assert rows(result) == [["a", "b"], ["1", "2"], ["3", "4"]]
    assert result["summary"]["blank_rows_removed"] == 2


# ── text standardization ──

def test_emails_are_lowercased():
    assert column(run("Email\n  Jane.DOE@Example.COM \n")) == ["jane.doe@example.com"]


def test_names_and_cities_fix_shouting_and_whispering_only():
    csv_text = "name,city\nJOHN SMITH,boston\nmary-jane o'neil,ST. JOHN'S\nMcDonald,DeKalb\n"
    out = rows(run(csv_text))
    assert out[1] == ["John Smith", "Boston"]
    assert out[2] == ["Mary-Jane O'Neil", "St. John's"]  # a possessive s stays lowercase
    assert out[3] == ["McDonald", "DeKalb"]  # deliberate mixed case is left alone


def test_two_letter_states_are_uppercased_but_longer_values_are_not():
    result = run("id,state\n1,ma\n2,Ma\n3,massachusetts\n")
    assert column(result, 1) == ["MA", "MA", "massachusetts"]


def test_username_columns_are_not_title_cased():
    assert column(run("username\njdoe42\n")) == ["jdoe42"]


# ── phones ──

def test_phone_numbers_are_formatted():
    csv_text = "Phone\n(617) 555-0142\n617.555.0199\n+1 617 555 0177\n16175550123\n"
    assert column(run(csv_text)) == ["617-555-0142", "617-555-0199", "617-555-0177", "617-555-0123"]


def test_phone_extensions_and_short_numbers_are_left_alone():
    assert column(run("phone\n617-555-0142 ext 12\n555-0142\n")) == ["617-555-0142 ext 12", "555-0142"]


# ── dates ──

def test_mixed_date_formats_become_iso():
    csv_text = 'date\n03/04/2025\n2025-03-11\nMar 5 2025\n"March 7, 2025"\n2025/03/06\n'
    assert column(run(csv_text)) == [
        "2025-03-04",  # ambiguous slashes are read month-first
        "2025-03-11",
        "2025-03-05",
        "2025-03-07",
        "2025-03-06",
    ]


def test_unparseable_dates_are_left_alone_and_short_values_are_not_guessed():
    csv_text = "signup_date\n03/04/2025\n03/05/2025\n03/06/2025\nsometime soon\n12\n"
    assert column(run(csv_text)) == ["2025-03-04", "2025-03-05", "2025-03-06", "sometime soon", "12"]


def test_a_column_that_is_mostly_not_dates_is_skipped_entirely():
    csv_text = "event_date\nlater this year\nTBD pending\nsee notes please\n03/04/2025\n"
    assert column(run(csv_text)) == ["later this year", "TBD pending", "see notes please", "03/04/2025"]


def test_date_columns_are_detected_by_header():
    for header in ("Signup Date", "signup_date", "signupDate", "DOB"):
        assert column(run(f"{header}\n03/04/2025\n")) == ["2025-03-04"], header


def test_headers_that_merely_end_in_date_are_not_dates():
    for header in ("update", "candidate"):
        assert column(run(f"{header}\n03/04/2025\n")) == ["03/04/2025"], header


def test_datetimes_keep_their_time():
    assert column(run("created_date\n03/04/2025 2:30 PM\n")) == ["2025-03-04 14:30:00"]


# ── numbers ──

def test_currency_and_thousands_separators_are_stripped():
    csv_text = 'amount\n"$1,250.00"\n$980\n"(1,200.50)"\n42\n'
    assert column(run(csv_text)) == ["1250.00", "980", "-1200.50", "42"]


def test_malformed_thousands_grouping_is_not_misread():
    # "1,5" looks like a European decimal. It must stay as written, never become 15.
    csv_text = 'amount\n"1,5"\n"$2,000"\n"$3,000"\n"$4,000"\n"$5,000"\n'
    assert column(run(csv_text)) == ["1,5", "2000", "3000", "4000", "5000"]


def test_identifier_columns_keep_leading_zeros():
    assert rows(run("zip,id\n02134,007\n01001,042\n"))[1:] == [["02134", "007"], ["01001", "042"]]


def test_text_columns_with_numbers_inside_are_untouched():
    assert column(run('address\n"1,000 Main St"\n"22 Elm St"\n')) == ["1,000 Main St", "22 Elm St"]


# ── duplicates and fills ──

def test_duplicates_are_found_after_cleaning():
    result = run("name,phone\n john smith ,(617) 555-0142\nJohn Smith,617-555-0142\n")
    assert result["summary"]["duplicates_removed"] == 1
    assert result["summary"]["rows_out"] == 1


def test_duplicates_are_kept_when_the_option_is_off():
    result = run("a\n1\n1\n", remove_duplicates=False)
    assert result["summary"]["rows_out"] == 2
    assert all(s["id"] != "remove_duplicates" for s in result["steps"])


def test_median_fill_is_off_by_default():
    assert column(run("id,amount\na,10\nb,\nc,30\n"), 1) == ["10", "", "30"]


def test_median_fill_ignores_duplicate_rows_when_computing_the_median():
    # Values 10, 10 (a duplicate row), 40 and one blank. After de-duplication the
    # median of [10, 40] is 25. If the duplicate counted, it would be 10.
    result = run("id,amount\na,10\na,10\nb,40\nc,\n", fill_numeric_median=True)
    assert rows(result)[-1] == ["c", "25"]
    assert step_count(result, "fill_numeric_median") == 1


def test_median_fill_skips_identifier_columns():
    out = rows(run("zip,amount\n02134,10\n,20\n02135,\n", fill_numeric_median=True))
    assert out[1:] == [["02134", "10"], ["", "20"], ["02135", "15"]]  # blank zip stays blank


# ── options, preview, summary ──

def test_each_step_can_be_switched_off():
    off = {
        "normalize_headers": False,
        "trim_whitespace": False,
        "standardize_nulls": False,
        "standardize_text": False,
        "normalize_phones": False,
        "normalize_dates": False,
        "parse_numbers": False,
        "remove_duplicates": False,
    }
    result = run("Name,Phone\n JOHN ,(617) 555-0142\n", **off)
    assert result["columns"] == ["Name", "Phone"]
    assert rows(result)[1] == [" JOHN ", "(617) 555-0142"]
    assert result["summary"]["cells_changed"] == 0


def test_preview_flags_changed_cells_with_their_original_value():
    result = run("name,city\nJOHN,Boston\nJane,Cambridge\n")
    preview = result["preview"]["rows"]
    assert len(preview) == 1  # only the row that changed is shown
    assert preview[0]["source_line"] == 2  # line 2 of the original file
    assert preview[0]["cells"] == [{"v": "John", "was": "JOHN"}, {"v": "Boston"}]
    assert result["preview"]["rows_changed"] == 1


def test_preview_falls_back_to_the_first_rows_when_nothing_changed():
    result = run("a,b\n1,2\n3,4\n")
    assert len(result["preview"]["rows"]) == 2
    assert result["summary"]["cells_changed"] == 0


def test_source_line_numbers_survive_removed_rows():
    # Line 3 is blank and gets dropped. JOHN, on line 4, must still say line 4.
    result = run("name\nJane Doe\n\nJOHN\n")
    assert result["preview"]["rows"][0]["source_line"] == 4


def test_summary_counts_add_up():
    summary = run("a\n1\n1\n\n2\n")["summary"]
    assert summary["rows_in"] == 4
    assert summary["blank_rows_removed"] == 1
    assert summary["duplicates_removed"] == 1
    assert summary["rows_out"] == 2


def test_long_cells_are_truncated_in_the_preview_only():
    result = run("name\n" + "x" * 500 + "\n")
    assert len(result["preview"]["rows"][0]["cells"][0]["v"]) == cleaner.MAX_PREVIEW_CELL_CHARS
    assert len(result["cleaned_csv"].split("\n")[1]) == 500  # the download keeps everything


# ── input handling and errors ──

def test_semicolon_and_tab_delimiters_are_detected():
    assert rows(run("a;b\n1;2\n"))[1] == ["1", "2"]
    assert rows(run("a\tb\n1\t2\n"))[1] == ["1", "2"]


def test_decode_bytes_handles_a_bom_and_windows_1252():
    assert cleaner.decode_bytes(b"\xef\xbb\xbfa,b\n") == "a,b\n"
    assert cleaner.decode_bytes("café".encode("cp1252")) == "café"


def test_empty_and_header_only_files_are_rejected():
    for bad in ("", "   \n\n", "a,b,c\n"):
        with pytest.raises(cleaner.CleanerError):
            run(bad)


def test_ragged_rows_give_a_readable_error():
    with pytest.raises(cleaner.CleanerError) as excinfo:
        run("a,b\n1,2,3\n")
    assert "could not parse" in str(excinfo.value)
    assert "line 2 has 3 columns but the header (line 1) has 2" in str(excinfo.value)


def test_too_many_rows_are_rejected():
    with pytest.raises(cleaner.CleanerError, match="too many rows"):
        run("a\n" + "1\n" * (cleaner.MAX_ROWS + 1))


def test_too_many_columns_are_rejected():
    width = cleaner.MAX_COLUMNS + 1
    with pytest.raises(cleaner.CleanerError, match="too many columns"):
        run(",".join(f"c{i}" for i in range(width)) + "\n" + ",".join(["x"] * width) + "\n")


def test_parse_options_validates_input():
    assert cleaner.parse_options(None) == cleaner.DEFAULT_OPTIONS
    assert cleaner.parse_options('{"fill_numeric_median": true}')["fill_numeric_median"] is True
    for bad in ("not json", "[]", '{"nope": true}', '{"trim_whitespace": "yes"}'):
        with pytest.raises(cleaner.CleanerError):
            cleaner.parse_options(bad)


# ── the built-in sample ──

def test_sample_csv_gives_every_default_step_something_to_fix():
    """The sample is the demo. If a cleaner change makes a step do nothing on it, fail."""
    result = cleaner.clean_csv(cleaner.SAMPLE_CSV, cleaner.DEFAULT_OPTIONS)
    for step in result["steps"]:
        assert step["count"] > 0, f"the sample data no longer exercises {step['id']}"
    assert result["summary"]["rows_in"] == 13
    assert result["summary"]["rows_out"] == 10
