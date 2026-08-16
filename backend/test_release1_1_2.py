import map_updater


def test_wiki_map_contract():
    assert map_updater.WIKI_TILE_URL.endswith("/{zoom}/{x}_{y}.png")
    assert map_updater.WIKI_GRID_SIZE == 12
    assert map_updater.WORLD_BOUNDS == {
        "world_min_x": 0.0, "world_max_x": 302400.0,
        "world_min_y": -100800.0, "world_max_y": 201600.0,
        "invert_y": True,
    }


if __name__ == "__main__":
    test_wiki_map_contract()
    print("V1.1.2 map contract tests passed")
