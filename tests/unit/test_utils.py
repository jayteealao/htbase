from app.core.utils import sanitize_filename


def test_sanitize_filename_basic():
    assert sanitize_filename("Hello-World_1.2.html") == "Hello-World_1.2.html"


def test_sanitize_filename_strips_bad_chars_and_leading_dot():
    # "../" becomes "__", then leading "." is stripped, leaving "_"
    assert sanitize_filename("../a b/c?d*e|.html") == "_a_b_c_d_e_.html"
    # Leading dots are stripped (hidden files), but not underscores/dashes
    assert sanitize_filename(".hidden") == "hidden"


def test_sanitize_filename_length_limit():
    long = "a" * 500 + ".html"
    out = sanitize_filename(long)
    assert len(out) == 200


def test_sanitize_filename_preserves_leading_underscores_and_dashes():
    """Verify that leading underscores and dashes are preserved for itemId integrity."""
    # Pocket itemIds can start with _ or -
    assert sanitize_filename("_rTiop7zSM5kqO") == "_rTiop7zSM5kqO"
    assert sanitize_filename("-EBHiBxyCIhu8R") == "-EBHiBxyCIhu8R"
    assert sanitize_filename("__5KPS_vjn1i46") == "__5KPS_vjn1i46"
    assert sanitize_filename("_0Dt7_x-ycTcxX") == "_0Dt7_x-ycTcxX"
    assert sanitize_filename("-1LJVdIN6UhsZu") == "-1LJVdIN6UhsZu"
    # But still strip leading dots (hidden files)
    assert sanitize_filename(".hidden") == "hidden"
    assert sanitize_filename("._file") == "_file"
