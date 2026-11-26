from services.follow_ups import FollowUpSplitter, parse_follow_ups


def run(chunks):
    splitter = FollowUpSplitter()
    shown = "".join(splitter.feed(c) for c in chunks)
    rest, follow_ups = splitter.finish()
    return shown + rest, follow_ups


def test_no_marker_passes_everything_through():
    assert run(["Hello ", "there <3"]) == ("Hello there <3", [])


def test_marker_split_across_chunks_is_never_shown():
    splitter = FollowUpSplitter()
    assert splitter.feed("We ship.\n<<FOLLOW") == "We ship."
    assert splitter.feed("_UPS>>\nDo you print logos?") == ""
    assert splitter.finish() == ("", ["Do you print logos?"])


def test_text_that_only_looks_like_the_marker_is_released():
    assert run(["a <<FOLL", "OW me"]) == ("a <<FOLLOW me", [])


def test_parse_strips_bullets_numbers_blanks_duplicates_and_caps_at_three():
    text = "\n- One?\n2. Two?\n\n* One?\n• Three?\nFour?\n" + "x" * 200
    assert parse_follow_ups(text) == ["One?", "Two?", "Three?"]
