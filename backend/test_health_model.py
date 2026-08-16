from __future__ import annotations

from health_model import apply_detected_hardware_references, normalize_health_config, score_hardware


def main():
    hw = {
        "cpu": "Intel Core i9-13900K",
        "gpu": "NVIDIA GeForce RTX 4070",
        "cpu_cores": 24,
        "cpu_threads": 32,
        "ram_total_gb": 32,
        "ram_available_gb": 20,
    }
    cfg = apply_detected_hardware_references({}, hw, generated_at=123.0)
    refs = cfg["hardware_reference"]
    assert refs["provider"] == "OpenBenchmarking.org"
    assert refs["provider_url"] == "https://openbenchmarking.org/"
    assert "openbenchmarking.org/vs/Processor/" in refs["cpu_url"]
    assert "Intel+Core+i9-13900K" in refs["cpu_url"]
    assert "openbenchmarking.org/vs/Graphics/" in refs["gpu_url"]
    assert refs["cpu_model"] == hw["cpu"]
    assert refs["gpu_model"] == hw["gpu"]
    assert refs["reference_generated_at"] == 123.0

    custom = normalize_health_config({"hardware_reference": {
        "provider": "manual", "auto_links": False,
        "cpu_url": "https://example.invalid/cpu", "cpu_score_0_100": 87,
    }})
    kept = apply_detected_hardware_references(custom, hw, generated_at=456.0)
    assert kept["hardware_reference"]["cpu_url"] == "https://example.invalid/cpu"
    assert kept["hardware_reference"]["provider"] == "manual"
    scored = score_hardware(hw, kept)
    assert scored["components"]["cpu"] == 87.0
    assert scored["source"] == "benchmark"

    print("health model tests passed")


if __name__ == "__main__":
    main()
