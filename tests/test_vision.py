import cv2
import numpy as np
import pytest

from linkdn_connect.vision import (
    ASSETS,
    Finder,
    Match,
    Template,
    TemplateError,
    default_templates,
    order_top_to_bottom,
)


@pytest.fixture(scope="module")
def templates():
    return default_templates()


def canvas(w=900, h=500):
    return np.full((h, w, 3), 255, np.uint8)


def paste(img, name, x, y, scale=1.0):
    patch = cv2.imread(str(ASSETS / name))
    if scale != 1.0:
        patch = cv2.resize(patch, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    h, w = patch.shape[:2]
    img[y : y + h, x : x + w] = patch
    return x + w // 2, y + h // 2


def test_templates_are_the_label_not_the_whole_button(templates):
    connect, send = templates
    whole = cv2.imread(str(ASSETS / "connect_button.png")).shape[:2]
    assert connect.gray.shape[0] < whole[0] * 0.6
    assert connect.gray.shape[1] < whole[1] * 0.5
    assert send.gray.shape[1] > connect.gray.shape[1]
    assert connect.signature > 20


@pytest.mark.parametrize("scale", [0.75, 1.0, 1.3])
def test_finds_a_button_at_other_zoom_levels(templates, scale):
    img = canvas()
    cx, cy = paste(img, "connect_button.png", 300, 200, scale)
    found = Finder().find(img, templates[0], 0.75)
    assert len(found) == 1
    assert abs(found[0].center[0] - cx) <= 6 and abs(found[0].center[1] - cy) <= 6


def test_finds_the_send_button(templates):
    img = canvas()
    cx, cy = paste(img, "send_button.png", 400, 300)
    found = Finder().find(img, templates[1], 0.75)
    assert len(found) == 1
    assert abs(found[0].center[0] - cx) <= 6 and abs(found[0].center[1] - cy) <= 6


def test_connect_and_send_are_not_confused(templates):
    img = canvas()
    paste(img, "connect_button.png", 100, 100)
    paste(img, "send_button.png", 400, 300)
    finder = Finder()
    assert len(finder.find(img, templates[0], 0.75)) == 1
    assert len(finder.find(img, templates[1], 0.75)) == 1


@pytest.mark.parametrize("label,color", [("Pending", (80, 80, 80)), ("Follow", (194, 102, 10)), ("Message", (194, 102, 10))])
def test_other_outlined_buttons_are_ignored(templates, label, color):
    img = canvas()
    cv2.rectangle(img, (300, 200), (546, 242), color, 2)
    cv2.putText(img, label, (370, 229), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
    assert Finder().find(img, templates[0], 0.75) == []


def test_blank_page_has_no_matches(templates):
    assert Finder().find(canvas(), templates[0], 0.75) == []


def test_results_are_ordered_by_row_then_column(templates):
    img = canvas(900, 700)
    paste(img, "connect_button.png", 500, 100)
    paste(img, "connect_button.png", 60, 104)
    paste(img, "connect_button.png", 300, 400)
    found = Finder().find(img, templates[0], 0.75)
    assert [m.center[0] < 300 for m in found[:2]] == [True, False]
    assert found[2].center[1] > found[1].center[1]


def test_order_groups_rows_with_small_vertical_jitter():
    a = Match(500, 100, 60, 16, 0.9)
    b = Match(60, 103, 60, 16, 0.9)
    c = Match(300, 300, 60, 16, 0.9)
    assert order_top_to_bottom([c, a, b]) == [b, a, c]


def test_template_rejects_blank_and_tiny_images():
    with pytest.raises(TemplateError):
        Template.from_button_image(np.full((40, 200, 3), 255, np.uint8))
    with pytest.raises(TemplateError):
        Template.from_button_image(np.zeros((8, 8, 3), np.uint8))


def test_template_from_missing_file(tmp_path):
    with pytest.raises(TemplateError):
        Template.from_file(tmp_path / "nope.png")
