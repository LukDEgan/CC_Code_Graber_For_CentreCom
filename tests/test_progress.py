import json

import pytest

import progress


@pytest.fixture
def paths(tmp_path, monkeypatch):
    output_dir = tmp_path / "output"
    sale_file = output_dir / "sale_cc_numbers.txt"
    not_sale_file = output_dir / "not_sale_cc_numbers.txt"
    fail_file = output_dir / "failed_products.txt"
    progress_file = tmp_path / "progress.json"

    monkeypatch.setattr(progress, "OUTPUT_DIR", str(output_dir))
    monkeypatch.setattr(progress, "SALE_FILE", str(sale_file))
    monkeypatch.setattr(progress, "NOT_SALE_FILE", str(not_sale_file))
    monkeypatch.setattr(progress, "FAIL_FILE", str(fail_file))
    monkeypatch.setattr(progress, "PROGRESS_FILE", str(progress_file))

    return {
        "output_dir": output_dir,
        "sale_file": sale_file,
        "not_sale_file": not_sale_file,
        "fail_file": fail_file,
        "progress_file": progress_file,
    }


def test_save_and_load_progress_round_trip(paths):
    progress.save_progress(
        "https://www.centrecom.com.au/cat", "All items", 5, 3, 1, completed=False
    )

    data = progress.load_progress()

    assert data == {
        "category_url": "https://www.centrecom.com.au/cat",
        "sale_filter": "All items",
        "next_index": 5,
        "cc_count": 3,
        "fail_count": 1,
        "completed": False,
    }


def test_load_progress_missing_file_returns_none(paths):
    assert progress.load_progress() is None


def test_load_progress_corrupt_json_returns_none(paths):
    paths["progress_file"].write_text("{not valid json", encoding="utf-8")

    assert progress.load_progress() is None


def test_load_progress_wrong_shape_list_returns_none(paths):
    paths["progress_file"].write_text(json.dumps([1, 2, 3]), encoding="utf-8")

    assert progress.load_progress() is None


def test_load_progress_missing_keys_returns_none(paths):
    paths["progress_file"].write_text(json.dumps({"category_url": "x"}), encoding="utf-8")

    assert progress.load_progress() is None


def test_save_progress_is_atomic_leaves_no_tmp_file(paths):
    progress.save_progress("https://example.com/cat", "All items", 0, 0, 0)

    tmp_file = paths["progress_file"].parent / (paths["progress_file"].name + ".tmp")
    assert not tmp_file.exists()
    assert paths["progress_file"].exists()
    assert progress.load_progress() is not None


def test_start_new_run_truncates_all_three_files_and_resets_progress(paths):
    paths["output_dir"].mkdir()
    paths["sale_file"].write_text("111111\n", encoding="utf-8")
    paths["not_sale_file"].write_text("222222\n", encoding="utf-8")
    paths["fail_file"].write_text("http://example.com/p\n", encoding="utf-8")

    progress.start_new_run("https://example.com/cat", "All items")

    assert paths["sale_file"].read_text(encoding="utf-8") == ""
    assert paths["not_sale_file"].read_text(encoding="utf-8") == ""
    assert paths["fail_file"].read_text(encoding="utf-8") == ""

    data = progress.load_progress()
    assert data["next_index"] == 0
    assert data["cc_count"] == 0
    assert data["fail_count"] == 0
    assert data["completed"] is False


def test_clear_opposite_file_on_sale_clears_not_sale_only(paths):
    paths["output_dir"].mkdir()
    paths["sale_file"].write_text("111111\n", encoding="utf-8")
    paths["not_sale_file"].write_text("222222\n", encoding="utf-8")

    progress.clear_opposite_file("On sale")

    assert paths["sale_file"].read_text(encoding="utf-8") == "111111\n"
    assert paths["not_sale_file"].read_text(encoding="utf-8") == ""


def test_clear_opposite_file_not_on_sale_clears_sale_only(paths):
    paths["output_dir"].mkdir()
    paths["sale_file"].write_text("111111\n", encoding="utf-8")
    paths["not_sale_file"].write_text("222222\n", encoding="utf-8")

    progress.clear_opposite_file("Not on sale")

    assert paths["sale_file"].read_text(encoding="utf-8") == ""
    assert paths["not_sale_file"].read_text(encoding="utf-8") == "222222\n"


@pytest.mark.parametrize("sale_filter", ["All items", "", "something else"])
def test_clear_opposite_file_other_values_are_noop(paths, sale_filter):
    paths["output_dir"].mkdir()
    paths["sale_file"].write_text("111111\n", encoding="utf-8")
    paths["not_sale_file"].write_text("222222\n", encoding="utf-8")

    progress.clear_opposite_file(sale_filter)

    assert paths["sale_file"].read_text(encoding="utf-8") == "111111\n"
    assert paths["not_sale_file"].read_text(encoding="utf-8") == "222222\n"


def test_count_lines_missing_file_returns_zero(paths):
    assert progress.count_lines(str(paths["sale_file"])) == 0


def test_count_lines_ignores_blank_lines(paths):
    paths["output_dir"].mkdir()
    paths["sale_file"].write_text("111111\n\n222222\n   \n333333\n", encoding="utf-8")

    assert progress.count_lines(str(paths["sale_file"])) == 3


def test_get_cc_file_count_sums_both_files(paths):
    paths["output_dir"].mkdir()
    paths["sale_file"].write_text("111111\n222222\n", encoding="utf-8")
    paths["not_sale_file"].write_text("333333\n", encoding="utf-8")

    assert progress.get_cc_file_count() == 3


def test_load_cc_numbers_missing_files_returns_empty_list(paths):
    assert progress.load_cc_numbers() == []


def test_load_cc_numbers_reads_both_files_stripped(paths):
    paths["output_dir"].mkdir()
    paths["sale_file"].write_text("111111\n222222\n", encoding="utf-8")
    paths["not_sale_file"].write_text("333333\n", encoding="utf-8")

    assert sorted(progress.load_cc_numbers()) == ["111111", "222222", "333333"]


def test_save_cc_number_appends_to_correct_file_by_status(paths):
    progress.save_cc_number("111111", "sale")
    progress.save_cc_number("222222", "not_sale")
    progress.save_cc_number("333333", "sale")

    assert paths["sale_file"].read_text(encoding="utf-8") == "111111\n333333\n"
    assert paths["not_sale_file"].read_text(encoding="utf-8") == "222222\n"


def test_progress_matches_none_progress_returns_false():
    assert progress.progress_matches(None, "https://x.com/cat", "All items") is False


def test_progress_matches_mismatched_category_url_returns_false():
    p = {"category_url": "https://x.com/other", "sale_filter": "All items"}
    assert progress.progress_matches(p, "https://x.com/cat", "All items") is False


def test_progress_matches_mismatched_sale_filter_returns_false():
    p = {"category_url": "https://x.com/cat", "sale_filter": "On sale"}
    assert progress.progress_matches(p, "https://x.com/cat", "All items") is False


def test_progress_matches_exact_match_returns_true():
    p = {"category_url": "https://x.com/cat", "sale_filter": "All items"}
    assert progress.progress_matches(p, "https://x.com/cat", "All items") is True


def test_progress_matches_ignores_completed_field():
    p = {"category_url": "https://x.com/cat", "sale_filter": "All items", "completed": True}
    assert progress.progress_matches(p, "https://x.com/cat", "All items") is True


def test_is_completed_none_progress_returns_false():
    assert progress.is_completed(None) is False


def test_is_completed_missing_key_defaults_false():
    assert progress.is_completed({"category_url": "x"}) is False


def test_is_completed_true_when_flag_set():
    assert progress.is_completed({"completed": True}) is True


def test_is_completed_false_when_flag_explicitly_false():
    assert progress.is_completed({"completed": False}) is False
