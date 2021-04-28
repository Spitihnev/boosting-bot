from event_objects import Boost, Booster


def test_is_this_valid_setup():
    def generate_all_boosters():
        for tank_flag in range(2):
            for healer_flag in range(2):
                for dps_flag in range(2):
                    b = Booster('', bool(tank_flag), bool(healer_flag), bool(dps_flag))
                    if b.has_any_role():
                        yield b

    all_boosters = [booster for booster in generate_all_boosters()]
    for test_idx in range(1, 7**4 - 1, 1):
        boosters = [all_boosters[test_idx % 7]]
        if test_idx > 7:
            boosters.append(all_boosters[(test_idx % (7*7)) // 7])
        if test_idx > 7*7 - 1:
            boosters.append(all_boosters[(test_idx % (7*7*7)) // (7*7)])
        if test_idx > 7*7*7 - 1:
            boosters.append(all_boosters[test_idx // (7*7*7)])
        if not Boost(10, '', '', boosters, '', '', '', '').is_this_valid_setup():
            yield boosters
