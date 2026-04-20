from __future__ import annotations

import re
import subprocess
import time
from typing import Any
from urllib.parse import urlparse

import requests


def measure_ping(host: str = "google.com", count: int = 4, timeout_s: int = 15) -> float:
    """
    Measure average latency (ms) using the system `ping` command.

    Beginner note:
    - We call the OS `ping` via subprocess (so this works without extra libraries).
    - Then we parse the `time=XX ms` numbers from the output.
    """
    host = host.strip()
    if not host:
        raise ValueError("Host cannot be empty.")

    # Matches: time=12.3 ms  OR  time<1 ms
    time_re = re.compile(r"time[=<]([\d.]+)\s*ms")

    try:
        completed = subprocess.run(
            ["ping", "-c", str(count), host],
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except FileNotFoundError as e:
        raise RuntimeError("`ping` command not found on this system.") from e
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"Ping timed out after {timeout_s} seconds.") from e

    samples = [float(x) for x in time_re.findall(completed.stdout or "")]
    if not samples:
        err = (completed.stderr or "").strip()
        raise RuntimeError(err or f"Could not measure latency for host '{host}'.")

    return sum(samples) / len(samples)


def measure_download_speed(url: str, timeout_s: int = 20) -> float:
    """
    Download a file and calculate throughput in Mbps.

    Formula:
    Download Speed (Mbps) = (file_size_bytes * 8) / (time_seconds * 1e6)
    """
    url = url.strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Invalid URL. Please provide a full http(s) URL (example: https://example.com/file.bin).")

    try:
        start = time.perf_counter()
        total_bytes = 0
        with requests.get(url, stream=True, timeout=timeout_s) as resp:
            resp.raise_for_status()
            for chunk in resp.iter_content(chunk_size=64 * 1024):
                if chunk:
                    total_bytes += len(chunk)
        seconds = max(time.perf_counter() - start, 1e-9)
    except requests.exceptions.Timeout as e:
        raise RuntimeError(f"Download timed out after {timeout_s} seconds.") from e
    except requests.exceptions.ConnectionError as e:
        raise RuntimeError(
            "Network connection error while downloading.\n"
            "- Common causes: blocked domain/firewall, captive portal, proxy required, DNS issues.\n"
            "- Try: open the URL in a browser, or try a different direct file URL."
        ) from e
    except requests.HTTPError as e:
        status = getattr(getattr(e, "response", None), "status_code", None)
        code = f" (HTTP {status})" if status else ""
        raise RuntimeError(f"Server returned an error{code}. Try a different URL.") from e

    if total_bytes <= 0:
        raise RuntimeError("Downloaded 0 bytes. The URL may not be a direct file download.")

    mbps = (total_bytes * 8) / (seconds * 1e6)
    return mbps


def get_external_results() -> dict[str, float]:
    """
    Ask the user to enter results from an external speed test website/app.
    """
    print("\nEnter External Tool Results (manual input)")
    ext_latency = _prompt_float("External latency (ms): ", minimum=0.0)
    ext_speed = _prompt_float("External download speed (Mbps): ", minimum=0.0)
    return {"latency_ms": ext_latency, "download_mbps": ext_speed}


def compare_results(my_latency_ms: float, my_download_mbps: float, ext_latency_ms: float, ext_download_mbps: float) -> dict[str, Any]:
    """
    Compute absolute difference and percentage difference for latency and download speed.

    Percentage difference is relative to the external result:
      percent = (abs_diff / external) * 100
    If external is 0, we avoid division-by-zero and return None for percent.
    """
    lat_abs = abs(my_latency_ms - ext_latency_ms)
    spd_abs = abs(my_download_mbps - ext_download_mbps)

    lat_pct = None if ext_latency_ms == 0 else (lat_abs / ext_latency_ms) * 100
    spd_pct = None if ext_download_mbps == 0 else (spd_abs / ext_download_mbps) * 100

    return {
        "latency_abs_ms": lat_abs,
        "latency_pct": lat_pct,
        "download_abs_mbps": spd_abs,
        "download_pct": spd_pct,
    }


def generate_analysis(comparison: dict[str, Any]) -> str:
    """
    Produce a human-readable explanation based on how big the differences are.

    Simple rule (beginner-friendly):
    - Small differences if both percent diffs are <= 15% (or percent diff is unavailable)
    - Otherwise, "large differences" with likely reasons
    """
    lat_pct = comparison.get("latency_pct")
    spd_pct = comparison.get("download_pct")

    def _is_small(pct: float | None) -> bool:
        return pct is None or pct <= 15.0

    if _is_small(lat_pct) and _is_small(spd_pct):
        return "Results are consistent."

    reasons = [
        "- Server distance (external tool may use a closer/farther server)",
        "- Network congestion (Wi‑Fi interference, busy network, peak hours)",
        "- Different testing methodologies (file size, warm-up, parallel connections, CDN caching)",
    ]
    return "Differences are large. Possible reasons:\n" + "\n".join(reasons)


def print_report(
    my_latency_ms: float,
    my_download_mbps: float,
    ext_latency_ms: float,
    ext_download_mbps: float,
    comparison: dict[str, Any],
    analysis: str,
) -> None:
    """
    Print the report in the exact requested format.
    """
    lat_abs = comparison["latency_abs_ms"]
    spd_abs = comparison["download_abs_mbps"]

    lat_pct = comparison["latency_pct"]
    spd_pct = comparison["download_pct"]

    lat_pct_str = "N/A" if lat_pct is None else f"{lat_pct:.1f}%"
    spd_pct_str = "N/A" if spd_pct is None else f"{spd_pct:.1f}%"

    print("\n--- Comparison Report ---\n")
    print("My Tool:")
    print(f"Ping: {my_latency_ms:.2f} ms")
    print(f"Download: {my_download_mbps:.2f} Mbps\n")

    print("External Tool:")
    print(f"Ping: {ext_latency_ms:.2f} ms")
    print(f"Download: {ext_download_mbps:.2f} Mbps\n")

    print("Difference:")
    print(f"Ping: {lat_abs:.2f} ms ({lat_pct_str})")
    print(f"Download: {spd_abs:.2f} Mbps ({spd_pct_str})\n")

    print("Analysis:")
    print(analysis)


def main() -> None:
    print("Network Comparison Analyzer (proj3.1)\n")

    host = input("Host to ping [google.com]: ").strip() or "google.com"
    url = (
        input("Direct file URL to download (for speed test) [https://speed.hetzner.de/10MB.bin]: ").strip()
        or "https://speed.hetzner.de/10MB.bin"
    )

    print("\nMeasuring with My Tool...")
    my_latency = measure_ping(host=host)
    my_speed = measure_download_speed(url=url)

    external = get_external_results()
    comparison = compare_results(
        my_latency_ms=my_latency,
        my_download_mbps=my_speed,
        ext_latency_ms=external["latency_ms"],
        ext_download_mbps=external["download_mbps"],
    )
    analysis = generate_analysis(comparison)
    print_report(
        my_latency_ms=my_latency,
        my_download_mbps=my_speed,
        ext_latency_ms=external["latency_ms"],
        ext_download_mbps=external["download_mbps"],
        comparison=comparison,
        analysis=analysis,
    )


def _prompt_float(prompt: str, minimum: float | None = None) -> float:
    while True:
        raw = input(prompt).strip()
        try:
            value = float(raw)
        except ValueError:
            print("Please enter a number (example: 42.5).")
            continue
        if minimum is not None and value < minimum:
            print(f"Please enter a value >= {minimum}.")
            continue
        return value


if __name__ == "__main__":
    main()

