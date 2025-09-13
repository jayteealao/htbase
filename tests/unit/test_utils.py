from core.utils import sanitize_filename


def test_sanitize_filename_basic():
    assert sanitize_filename("Hello-World_1.2.html") == "Hello-World_1.2.html"


def test_sanitize_filename_strips_bad_chars_and_leading_dot():
    assert sanitize_filename("../a b/c?d*e|.html") == "a_b_c_d_e_.html"
    assert sanitize_filename(".hidden") == "hidden"


def test_sanitize_filename_length_limit():
    long = "a" * 500 + ".html"
    out = sanitize_filename(long)
    assert len(out) == 200
