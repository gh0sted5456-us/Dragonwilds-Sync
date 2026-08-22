import map_updater
from player_tracker import world_to_map


def test_wiki_map_contract():
    assert map_updater.WIKI_TILE_URL.endswith("/{zoom}/{x}_{y}.png")
    assert map_updater.WIKI_GRID_SIZE == 12
    assert map_updater.WORLD_BOUNDS == {
        "world_min_x": -11075.0, "world_max_x": 408925.0,
        "world_min_y": -117685.0, "world_max_y": 302315.0,
        "invert_y": False,
    }
    # https://dragonwildscodex.com/map/?at=171547%2C37995%2C1
    # ``at`` is X,Y,map zoom; the game Z/elevation remains separate.
    point = world_to_map(171547, 37995, map_updater.WORLD_BOUNDS)
    assert point == {"x": 0.4348142857142857, "y": 0.37066666666666664}


if __name__ == "__main__":
    test_wiki_map_contract()
    print("V1.1.2 map contract tests passed")
