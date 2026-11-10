from storage import mime


def crlf(*lines):
    return "\r\n".join(lines)


ALTERNATIVE = crlf(
    "Subject: test",
    "MIME-Version: 1.0",
    "Content-Type: multipart/alternative; boundary=BOUNDARY",
    "",
    "--BOUNDARY",
    "Content-Type: text/plain; charset=utf-8",
    "",
    "plain part",
    "second line",
    "--BOUNDARY",
    "Content-Type: text/html; charset=utf-8",
    "",
    "<p>html part</p>",
    "--BOUNDARY--",
    "",
)


def multipart(*parts, subtype="mixed"):
    lines = ["Subject: test", "MIME-Version: 1.0",
             "Content-Type: multipart/%s; boundary=B" % subtype, ""]
    for content_type, body in parts:
        lines += ["--B", "Content-Type: %s" % content_type, "", body]
    lines += ["--B--", ""]
    return crlf(*lines)


# --- get_body ---

def test_get_body_returns_everything_after_the_first_blank_line():
    assert mime.get_body(crlf("A: 1", "B: 2", "", "line 1", "", "line 3")) == crlf("line 1", "", "line 3")


def test_get_body_undoes_dot_stuffing():
    assert mime.get_body(crlf("A: 1", "", "..one", "...two", "middle.. dots")) == crlf(".one", "..two", "middle.. dots")


def test_get_body_accepts_lf_line_endings():
    assert mime.get_body("A: 1\nB: 2\n\nbody\nmore") == crlf("body", "more")


def test_get_body_without_a_blank_line_is_empty():
    assert mime.get_body(crlf("A: 1", "B: 2")) == ""


# --- get_text_message ---

def test_plain_text_message():
    msg = crlf("Content-Type: text/plain", "Subject: x", "", "hello", "..dot", "end")
    assert mime.get_text_message(msg) == crlf("hello", ".dot", "end")


def test_non_mime_message():
    msg = crlf("Subject: x", "From: someone", "", "body line", "..two")
    assert mime.get_text_message(msg) == crlf("body line", ".two")


def test_multipart_alternative_prefers_the_plain_text_part():
    # regression: multipart bodies used to come back empty, because
    # email's as_string() uses LF and get_body() only split on CRLF
    assert mime.get_text_message(ALTERNATIVE) == crlf("plain part", "second line")


def test_multipart_with_only_html_returns_the_html_part():
    msg = multipart(("text/html", "<p>only html</p>"), subtype="alternative")
    assert mime.get_text_message(msg) == "<p>only html</p>"


def test_multipart_mixed_with_an_attachment_returns_the_text():
    msg = multipart(("text/plain", "see attached"), ("image/png", "iVBORw0KGgo="))
    assert mime.get_text_message(msg) == "see attached"


def test_multipart_without_any_text_part_is_empty():
    # regression: this used to raise UnboundLocalError
    msg = multipart(("image/png", "iVBORw0KGgo="))
    assert mime.get_text_message(msg) == ""
