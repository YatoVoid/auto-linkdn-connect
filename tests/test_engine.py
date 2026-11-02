import random
import threading

import numpy as np
import pytest

from linkdn_connect.engine import Callbacks, Engine, screen_changed
from linkdn_connect.settings import Settings
from linkdn_connect.vision import default_templates
from sim import FakeClock, SimPointer, SimScreen, SimWorld, grid


@pytest.fixture(scope="module")
def templates():
    return default_templates()


def make(templates, buttons, height, scale=1.0, **settings):
    world = SimWorld(buttons, height)
    stop = threading.Event()
    log, progress = [], []
    pointer = SimPointer(world, scale)
    engine = Engine(
        Settings(pause_min=0.5, pause_max=1.0, **settings),
        SimScreen(world, scale),
        pointer,
        *templates,
        stop,
        Callbacks(log.append, progress.append),
        clock=FakeClock(stop),
        rng=random.Random(1),
    )
    return world, engine, stop, pointer, log, progress


def test_sends_every_button_top_to_bottom_and_stops_at_page_end(templates):
    buttons, height = grid(4)
    world, engine, _, _, _, progress = make(templates, buttons, height)
    reason = engine.run()
    assert reason == "Reached the end of the page."
    assert not world.remaining()
    assert engine.sent == 8
    assert progress == list(range(1, 9))
    assert [(b.y, b.x) for b in world.order] == sorted((b.y, b.x) for b in buttons)


def test_never_clicks_pending_buttons(templates):
    buttons, height = grid(2, kinds={(0, 0): "pending", (0, 1): "pending"})
    world, engine, *_ = make(templates, buttons, height)
    engine.run()
    assert engine.sent == 2
    assert all(b.clicks == 0 for b in buttons if b.kind == "pending")


def test_stops_at_the_invitation_limit(templates):
    buttons, height = grid(4)
    world, engine, *_ = make(templates, buttons, height, max_invites=3)
    reason = engine.run()
    assert engine.sent == 3
    assert "limit of 3" in reason
    assert len(world.remaining()) == 5


def test_invite_that_sends_without_a_dialog_counts(templates):
    buttons, height = grid(1, kinds={(0, 0): "direct"})
    world, engine, *_ = make(templates, buttons, height)
    engine.run()
    assert engine.sent == 2
    assert not world.remaining()


def test_unexpected_dialog_is_closed_and_skipped(templates):
    buttons, height = grid(2, kinds={(0, 0): "stuck"})
    world, engine, _, _, log, _ = make(templates, buttons, height)
    reason = engine.run()
    assert engine.sent == 3
    assert world.escapes >= 1
    assert world.modal is None
    assert [b.kind for b in world.remaining()] == ["stuck"]
    assert any("Skipped" in line for line in log)
    assert reason == "Reached the end of the page."


def test_gives_up_after_repeated_failures(templates):
    kinds = {(r, c): "stuck" for r in range(2) for c in range(2)}
    buttons, height = grid(2, kinds=kinds)
    world, engine, *_ = make(templates, buttons, height)
    reason = engine.run()
    assert engine.sent == 0
    assert "failed attempts in a row" in reason


def test_page_without_buttons_scrolls_to_the_end(templates):
    world, engine, *_ = make(templates, [], 2000)
    assert engine.run() == "Reached the end of the page."
    assert world.scroll == 2000 - 540
    assert engine.sent == 0


def test_stop_event_ends_the_run(templates):
    buttons, height = grid(4)
    world, engine, stop, _, _, progress = make(templates, buttons, height)
    engine.cb.progress = lambda n: (progress.append(n), stop.set())
    assert engine.run() == "Stopped."
    assert engine.sent == 1


def test_stops_when_the_user_moves_the_mouse(templates):
    buttons, height = grid(2)
    world, engine, _, pointer, *_ = make(templates, buttons, height)
    original_click = pointer.click

    def click_then_drift():
        original_click()
        pointer.drift = (300, 300)

    pointer.click = click_then_drift
    assert "mouse was moved" in engine.run()
    assert engine.sent == 0


def test_screen_changed_tells_scrolled_from_static():
    rng = np.random.default_rng(0)
    page = rng.integers(0, 255, (1200, 800, 3), dtype=np.uint8)
    top, down = page[:540], page[100:640]
    assert not screen_changed(top, top.copy())
    assert screen_changed(top, down)


def test_detect_once_reports_scores(templates):
    buttons, height = grid(1)
    world, engine, *_ = make(templates, buttons, height)
    lines = engine.detect_once()
    assert lines[0] == "Connect: 2 found"
    assert any("accepted" in line for line in lines)


@pytest.mark.parametrize("scale", [2.0, 1.5])
def test_clicks_land_on_high_density_screens(templates, scale):
    buttons, height = grid(2)
    world, engine, *_ = make(templates, buttons, height, scale=scale)
    engine.run()
    assert engine.sent == 4
    assert not world.remaining()
