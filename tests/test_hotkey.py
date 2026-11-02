from linkdn_connect.hotkey import Gate


def test_gate_drops_triggers_that_arrive_together():
    now = [100.0]
    gate = Gate(0.35, lambda: now[0])
    assert gate.allow()
    now[0] += 0.01
    assert not gate.allow()
    now[0] += 0.2
    assert not gate.allow()


def test_gate_allows_the_next_real_press():
    now = [100.0]
    gate = Gate(0.35, lambda: now[0])
    assert gate.allow()
    now[0] += 1.0
    assert gate.allow()
