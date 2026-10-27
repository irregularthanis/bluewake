#!/usr/bin/env python3

import importlib.util
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "perf_domains", ROOT / "scripts/linux/perf_domains.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class PerfDomainsTest(unittest.TestCase):
    def test_classifies_bluewake_domains(self):
        lines = [
            "bluewake 10 7f123456 func_802456E0 (/tmp/gGZLE01_recomp.so)",
            "bluewake 10 native_vec_transform (/tmp/bluewake)",
            "bluewake 10 host_prepare_guest_dispatch (/tmp/bluewake)",
            "bluewake 10 ppc_guest_alias_resolve (/tmp/gGZLE01_recomp.so)",
            "bluewake 10 dol_dvd_tick (/tmp/bluewake)",
            "GX worker 11 gxcore::GxCoreState::apply() (/tmp/bluewake)",
            "render 12 dawn::native::vulkan::Queue::Submit() (/tmp/bluewake)",
            "bluewake 10 allocator_detail (/tmp/bluewake)",
            "bluewake 10 memcpy (/usr/lib/libc.so.6)",
            "bluewake 10 schedule ([kernel.kallsyms])",
        ]
        result = MODULE.collect(lines)
        counts = {row["domain"]: row["samples"] for row in result["domains"]}
        self.assertEqual(result["total_samples"], 10)
        self.assertEqual(counts, {domain: 1 for domain in MODULE.DOMAINS[:-1]})

    def test_reports_process_and_thread_percentages(self):
        result = MODULE.collect([
            "bluewake 20 func_80000000 (/tmp/gGZLE01_recomp.so)",
            "bluewake 20 func_80000004 (/tmp/gGZLE01_recomp.so)",
            "gx-worker 21 gxcore::GxCoreState::apply() (/tmp/bluewake)",
            "ignored perf line",
        ])
        self.assertEqual(result["total_samples"], 3)
        self.assertEqual(result["unparsed_lines"], 1)
        self.assertAlmostEqual(result["domains"][0]["percent"], 200.0 / 3.0)
        self.assertEqual(result["threads"][0]["tid"], 20)
        self.assertEqual(result["threads"][0]["domains"][0]["percent"], 100.0)

    def test_parses_deck_multiline_callchains_as_one_sample_each(self):
        result = MODULE.collect([
            "bluewake   44 ",
            "    7f001234 func_802456E0 (/tmp/gGZLE01_recomp.so)",
            "    7f005678 caller (/tmp/gGZLE01_recomp.so)",
            "",
            "GX worker   45 ",
            "    7f009abc gxcore::GxCoreState::apply() (/tmp/bluewake)",
            "    7f00def0 caller (/tmp/bluewake)",
            "",
        ])
        self.assertEqual(result["total_samples"], 2)
        self.assertEqual(result["unparsed_lines"], 0)
        self.assertEqual(result["threads"][0]["tid"], 44)


if __name__ == "__main__":
    unittest.main()
