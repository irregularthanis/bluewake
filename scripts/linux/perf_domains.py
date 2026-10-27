#!/usr/bin/env python3
"""Summarize a Linux perf capture by BlueWake architecture domain and thread."""

from __future__ import annotations

import argparse
import collections
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


DOMAINS = (
    "Translated game",
    "Native replacements",
    "Host coordination",
    "Guest state and dispatch",
    "Compatibility services",
    "GX and Aurora",
    "GPU and presentation",
    "Other BlueWake",
    "System libraries",
    "Kernel",
    "Unknown",
)


@dataclass(frozen=True)
class Sample:
    command: str
    tid: int
    dso: str
    symbol: str


def classify(dso: str, symbol: str) -> str:
    dso_lower = dso.lower()
    symbol_lower = symbol.lower()
    value = f"{dso_lower} {symbol_lower}"
    if "[kernel.kallsyms]" in value or "[kernel" in value:
        return "Kernel"
    if any(token in symbol_lower for token in ("native_", "bluewake_native", "recomp_native")):
        return "Native replacements"
    if any(token in symbol_lower for token in (
        "gxcore::", "aurora_recomp::", "retailgx", "gxruntime", "aurora_backend_gx",
        "host_graphics_", "dol_platform_gx_", "dol_gx_recomp", "gx_write", "gx_flush",
        "build_draw_plan_into", "fill_render_packet", "submit_packet", "emit_new_packets",
    )):
        return "GX and Aurora"
    if any(token in value for token in (
        "dawn::", "wgpu", "vulkan", "libvulkan", "radeon", "amdgpu", "mesa",
        "present", "swapchain", "sdl", "gamescope",
    )):
        return "GPU and presentation"
    if any(token in symbol_lower for token in (
        "dol_interrupt", "dol_alarm", "dol_audio", "dol_dsp", "dol_dvd", "dol_aram",
        "dol_card", "dol_vi_", "dol_input", "haptic", "memory_card", "disc_", "dsp_",
    )):
        return "Compatibility services"
    if any(token in symbol_lower for token in (
        "chassis_dispatch", "guest_alias", "guest_memory", "mem_read", "mem_write",
        "direct_can_skip", "direct_call", "requires_full", "cpu_state", "dispatch_loop",
    )):
        return "Guest state and dispatch"
    if any(token in symbol_lower for token in (
        "bluewake", "host_", "module_", "dispatch", "edge_intercept", "fps_watch",
    )):
        return "Host coordination"
    if "ggzle01_recomp" in dso_lower or re.search(r"\bfunc_[0-9a-f]{6,}\b", symbol_lower):
        return "Translated game"
    if dso in ("[unknown]", "unknown", "") or symbol in ("[unknown]", "unknown", ""):
        return "Unknown"
    if Path(dso).name == "bluewake":
        return "Other BlueWake"
    if any(token in value for token in (
        ".so", "libc", "libm", "libstdc", "libc++", "ld-linux", "libpthread",
    )):
        return "System libraries"
    return "Unknown"


def parse_line(line: str) -> Sample | None:
    # perf script -F comm,tid,ip,sym,dso emits:
    #   bluewake 12345 7f123456 symbol name (/path/to/dso)
    # Accept an ip-less fixture too, so classification tests stay readable.
    match = re.match(r"^\s*(.+?)\s+(\d+)\s+(.+?)\s+\((.*)\)\s*$", line)
    if not match:
        return None
    symbol = re.sub(r"^(?:0x)?[0-9a-fA-F]+\s+", "", match.group(3), count=1)
    return Sample(match.group(1), int(match.group(2)), match.group(4), symbol)


def parse_samples(lines: list[str]) -> tuple[list[Sample], int]:
    """Accept one-line perf output and the Deck's header-plus-callchain form."""
    samples: list[Sample] = []
    pending: tuple[str, int] | None = None
    in_callchain = False
    malformed = 0
    for line in lines:
        if not line.strip():
            pending = None
            in_callchain = False
            continue
        if line.lstrip().startswith("#"):
            continue
        header = re.match(r"^\s*(.+?)\s+(\d+)\s*$", line)
        if header:
            pending = (header.group(1), int(header.group(2)))
            in_callchain = True
            continue
        if pending is not None:
            frame = re.match(r"^\s*(?:0x)?[0-9a-fA-F]+\s+(.+?)\s+\((.*)\)\s*$", line)
            if frame:
                samples.append(Sample(pending[0], pending[1], frame.group(2), frame.group(1)))
                pending = None
                continue
            malformed += 1
            pending = None
        if in_callchain:
            continue
        sample = parse_line(line)
        if sample is None:
            malformed += 1
        else:
            samples.append(sample)
    return samples, malformed


def collect(lines: list[str]) -> dict:
    domain_counts: collections.Counter[str] = collections.Counter()
    thread_counts: dict[tuple[str, int], collections.Counter[str]] = {}
    symbol_counts: dict[str, collections.Counter[str]] = {
        domain: collections.Counter() for domain in DOMAINS
    }
    samples, malformed = parse_samples(lines)
    for sample in samples:
        domain = classify(sample.dso, sample.symbol)
        domain_counts[domain] += 1
        thread_counts.setdefault((sample.command, sample.tid), collections.Counter())[domain] += 1
        symbol_counts[domain][sample.symbol] += 1

    total = sum(domain_counts.values())
    return {
        "total_samples": total,
        "unparsed_lines": malformed,
        "domains": [
            {
                "domain": domain,
                "samples": domain_counts[domain],
                "percent": 100.0 * domain_counts[domain] / total if total else 0.0,
                "top_symbols": [
                    {"symbol": symbol, "samples": count}
                    for symbol, count in symbol_counts[domain].most_common(8)
                ],
            }
            for domain in DOMAINS if domain_counts[domain]
        ],
        "threads": [
            {
                "command": command,
                "tid": tid,
                "samples": sum(counts.values()),
                "domains": [
                    {
                        "domain": domain,
                        "samples": counts[domain],
                        "percent": 100.0 * counts[domain] / sum(counts.values()),
                    }
                    for domain in DOMAINS if counts[domain]
                ],
            }
            for (command, tid), counts in sorted(
                thread_counts.items(), key=lambda item: sum(item[1].values()), reverse=True
            )
        ],
    }


def table(result: dict, markdown: bool = False) -> str:
    lines = []
    if markdown:
        lines.extend(("| Domain | Samples | CPU sample share |", "| --- | ---: | ---: |"))
        for row in result["domains"]:
            lines.append(f"| {row['domain']} | {row['samples']:,} | {row['percent']:.1f}% |")
    else:
        lines.append("CPU distribution by architecture domain")
        width = max((len(row["domain"]) for row in result["domains"]), default=6)
        for row in result["domains"]:
            lines.append(f"  {row['domain']:<{width}}  {row['samples']:>8,}  {row['percent']:>6.1f}%")
    lines.append("")
    lines.append("Per-thread distribution" if not markdown else "### Per-thread distribution")
    for thread in result["threads"]:
        shares = ", ".join(
            f"{row['domain']} {row['percent']:.1f}%" for row in thread["domains"][:5]
        )
        lines.append(f"- {thread['command']} ({thread['tid']}): {thread['samples']:,} samples — {shares}")
    lines.append("")
    lines.append("Top symbols by domain" if not markdown else "### Top symbols by domain")
    for row in result["domains"]:
        symbols = ", ".join(
            f"`{entry['symbol']}` ({entry['samples']})" if markdown else
            f"{entry['symbol']} ({entry['samples']})"
            for entry in row["top_symbols"][:5]
        )
        lines.append(f"- {row['domain']}: {symbols}")
    lines.append("")
    lines.append(
        f"Statistical self-time estimate from {result['total_samples']:,} perf samples; "
        "percentages are not wall-clock time and overlapping call stacks are not double-counted."
    )
    if result["unparsed_lines"]:
        lines.append(f"Warning: ignored {result['unparsed_lines']} unrecognized perf-script lines.")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("perf_data", type=Path, nargs="?", help="perf.data capture")
    parser.add_argument("--script-input", type=Path, help="pre-rendered perf script text")
    parser.add_argument("--json", type=Path, help="write machine-readable output")
    parser.add_argument("--markdown", type=Path, help="write GitHub-friendly report")
    args = parser.parse_args()
    if bool(args.perf_data) == bool(args.script_input):
        parser.error("provide exactly one of perf_data or --script-input")

    if args.script_input:
        lines = args.script_input.read_text(encoding="utf-8", errors="replace").splitlines()
    else:
        run = subprocess.run(
            ["perf", "script", "-i", str(args.perf_data), "-F", "comm,tid,ip,sym,dso"],
            check=True, text=True, stdout=subprocess.PIPE,
        )
        lines = run.stdout.splitlines()
    result = collect(lines)
    if not result["total_samples"]:
        print("perf_domains: no samples parsed", file=sys.stderr)
        return 1
    if args.json:
        args.json.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if args.markdown:
        args.markdown.write_text(table(result, markdown=True) + "\n", encoding="utf-8")
    print(table(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
