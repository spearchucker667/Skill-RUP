echo "=== RUP-AUD-001 (Capability Mapping) ==="
grep -n "def test_capability" scripts/build_capability_map.py tests/test_capability_map.py || echo "Not semantic"
echo "=== RUP-AUD-002 (generate_runtime.py) ==="
ls scripts/generate_runtime.py || echo "Deleted"
echo "=== RUP-AUD-003 (generate_ci_docs.py) ==="
ls scripts/generate_ci_docs.py || echo "Deleted"
echo "=== RUP-AUD-004 (Execution) ==="
grep "def execute_plan" runtime/execution.py
echo "=== RUP-AUD-005 (Verification) ==="
grep -A 3 "def verify" runtime/verification.py
echo "=== RUP-AUD-006 (Schema Path) ==="
grep "validate_rup.py" .github/workflows/*.yml
echo "=== RUP-AUD-007 (Stubs) ==="
wc -l runtime/*.py
echo "=== RUP-AUD-008 (Discovery) ==="
grep -i "detector" runtime/discovery.py
echo "=== P1 Security (Prompt Injection) ==="
grep -rn "check_prompt_injection" runtime/
echo "=== P1 Security (Redaction) ==="
cat runtime/redaction.py | grep "TODO" || echo "No TODO"
echo "=== P1 Security (Audit Sources) ==="
grep -i "/Users/" scripts/audit_sources.py || echo "No hardcoded paths"
