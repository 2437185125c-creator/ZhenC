"""Unit tests for git diff parsing."""
from __future__ import annotations

from code_review_harness.review.diff import parse_diff

SAMPLE_DIFF = """diff --git a/app.py b/app.py
index 1a2b3c4..5d6e7f8 100644
--- a/app.py
+++ b/app.py
@@ -1,3 +1,4 @@
 def add(a, b):
-    return a + b
+    # better implementation
+    return a + b
diff --git a/new_file.py b/new_file.py
new file mode 100644
index 0000000..abc1234
--- /dev/null
+++ b/new_file.py
@@ -0,0 +1,3 @@
+def helper():
+    return 42
"""


def test_parse_diff_extracts_files():
    files = parse_diff(SAMPLE_DIFF)
    assert len(files) == 2
    assert files[0].path.as_posix() == "app.py"
    assert files[1].path.as_posix() == "new_file.py"
    assert files[1].status == "A"


def test_parse_diff_hunks():
    files = parse_diff(SAMPLE_DIFF)
    app = files[0]
    assert len(app.hunks) == 1
    hunk = app.hunks[0]
    assert hunk.old_start == 1
    assert hunk.old_count == 3
    assert hunk.new_start == 1
    assert hunk.new_count == 4


def test_changed_file_is_python():
    files = parse_diff(SAMPLE_DIFF)
    assert files[0].is_python
    assert not files[1].path.suffix == ".txt"


def test_added_line_numbers_span():
    files = parse_diff(SAMPLE_DIFF)
    lines = files[0].added_line_numbers
    assert lines == [1, 2, 3, 4]
