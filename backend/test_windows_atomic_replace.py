from __future__ import annotations


def main() -> None:
    import process_utils

    original_replace = process_utils._ORIGINAL_OS_REPLACE
    original_name = process_utils.os.name
    original_delays = process_utils._WINDOWS_REPLACE_DELAYS
    attempts = {"count": 0}

    def flaky(source, destination):
        attempts["count"] += 1
        if attempts["count"] < 4:
            raise PermissionError(13, "simulated transient destination lock")
        return (source, destination)

    try:
        process_utils._ORIGINAL_OS_REPLACE = flaky
        process_utils.os.name = "nt"
        process_utils._WINDOWS_REPLACE_DELAYS = (0, 0, 0, 0)
        result = process_utils.atomic_replace_with_retry("source.tmp", "launcher_v2.json")
        assert result == ("source.tmp", "launcher_v2.json")
        assert attempts["count"] == 4

        attempts["count"] = 0
        process_utils.os.name = "posix"
        try:
            process_utils.atomic_replace_with_retry("source.tmp", "launcher_v2.json")
        except PermissionError:
            pass
        else:
            raise AssertionError("non-Windows replacement errors must not be retried/swallowed")
        assert attempts["count"] == 1
    finally:
        process_utils._ORIGINAL_OS_REPLACE = original_replace
        process_utils.os.name = original_name
        process_utils._WINDOWS_REPLACE_DELAYS = original_delays

    print("Windows atomic replace retry regression passed")


if __name__ == "__main__":
    main()
