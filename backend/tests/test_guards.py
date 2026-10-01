"""Cross-cutting guard tests: the logger JSON shape and the billing semantics must
stay identical across the Python and TypeScript sides."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from app_logger import create_memory_transport, create_logger

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.unit
def test_logger_json_shape_matches_typescript():
    # Python side: the emitted entry has exactly the contract keys.
    transport, memory = create_memory_transport()
    logger = create_logger(transport=transport, base_context={"component": "test"})
    logger.info("some.event", {"k": "v"})
    entry = memory.entries[0]
    assert set(entry.keys()) >= {"ts", "level", "event", "context"}
    assert entry["event"] == "some.event"
    assert entry["context"]["component"] == "test" and entry["context"]["k"] == "v"

    # TypeScript side declares the same LogEntry shape.
    ts = (REPO_ROOT / "packages" / "logger" / "src" / "index.ts").read_text()
    for key in ("ts:", "level:", "event:", "message?:", "context:", "error?:"):
        assert key in ts, f"packages/logger LogEntry missing '{key}'"


@pytest.mark.unit
def test_billing_semantics_parity_python_vs_node():
    """Run the same classify/normalize inputs through the Python plan catalog and
    the Node billing.shared.mjs; the results must match."""
    node = shutil.which("node")
    if not node:
        pytest.skip("node not available")

    from app.billing.plan_catalog import classify_change, normalize_shopify_plan_name

    classify_inputs = [("free", "pro"), ("pro", "free"), ("free", "free"), ("pro", "pro")]
    normalize_inputs = ["Pro", "free", "MyApp Pro", "nonsense", ""]

    py = {
        "classify": [classify_change(a, b) for a, b in classify_inputs],
        "normalize": [normalize_shopify_plan_name(x) for x in normalize_inputs],
    }

    script = r"""
      import { readFileSync } from "node:fs";
      import { classifyChange, normalizeShopifyPlanName } from "./shopify/app/billing.shared.mjs";
      const cfg = JSON.parse(readFileSync("./app.config.json", "utf8"));
      const plans = (cfg.billing.plans || []).map(p => ({
        handle: p.handle, name: p.name, rank: p.rank, shopifyPlanName: p.shopifyPlanName,
      }));
      const classifyInputs = [["free","pro"],["pro","free"],["free","free"],["pro","pro"]];
      const normalizeInputs = ["Pro","free","MyApp Pro","nonsense",""];
      console.log(JSON.stringify({
        classify: classifyInputs.map(([a,b]) => classifyChange(plans,a,b)),
        normalize: normalizeInputs.map(x => normalizeShopifyPlanName(plans,x)),
      }));
    """
    out = subprocess.run(
        [node, "--input-type=module", "-e", script],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
    )
    assert out.returncode == 0, out.stderr
    node_result = json.loads(out.stdout.strip())
    assert node_result == py, f"parity mismatch:\n python={py}\n node={node_result}"
