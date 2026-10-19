"""Offline source-provenance and client demonstration verification."""
from __future__ import annotations

from scripts.client_acceptance_smoke import run
from scripts.benchmark_external_resume_corpus import (
    IDS, DATASET, COMMIT, normalized, assess, _truth, _actual,
)


def test_client_r7_r10_demo_is_actually_executable():
    receipts = run()
    assert receipts["functional_status"] == "PASS", receipts["failed_checks"]
    assert receipts["check_count"] >= 14
    assert receipts["passed_count"] == receipts["check_count"]
    assert receipts["real_hr_matching_validity_verified"] is False
    assert receipts["real_applicant_accuracy_verified"] is False


def test_public_corpus_is_fixed_not_posthoc_selected():
    assert DATASET == "jijunhao/SyntheticResumeData"
    assert len(COMMIT) == 40
    assert IDS == tuple([*range(1,11),*range(101,106),*range(201,206)])
    assert len(set(IDS)) == 20


def test_pinned_git_object_transport_is_binary_and_never_uses_api(monkeypatch, tmp_path):
    import subprocess
    import pytest
    from scripts import benchmark_external_resume_corpus as benchmark

    root = tmp_path / "external-readonly-clone"
    (root / ".git").mkdir(parents=True)
    monkeypatch.setattr(benchmark, "GIT_CACHE", root)
    seen = []

    def fake_git(args, **kwargs):
        seen.append(args)
        assert args[:3] == ["git", "-C", str(root)]
        if args[3] == "rev-parse":
            return subprocess.CompletedProcess(args, 0, stdout=benchmark.COMMIT + "\n")
        assert args[3:5] == ["show", benchmark.COMMIT + ":resume_list_pdf/1.pdf"]
        assert kwargs["capture_output"] and kwargs["timeout"] > 0
        return subprocess.CompletedProcess(args, 0, stdout=b"%PDF-1.7\nDUMMY BYTES")

    class NoNetwork:
        def get(self, *_args, **_kwargs):
            raise AssertionError("Pinned Git cache must not use network API fallback")

    monkeypatch.setattr(benchmark.subprocess, "run", fake_git)
    content = benchmark._fetch(NoNetwork(), "resume_list_pdf/1.pdf")
    assert content.startswith(b"%PDF-")
    assert len(seen) == 2
    assert benchmark.COMMIT in seen[-1][-1]

    def wrong_head(args, **kwargs):
        return subprocess.CompletedProcess(args, 0, stdout="a"*40+"\n")

    monkeypatch.setattr(benchmark.subprocess, "run", wrong_head)
    with pytest.raises(ValueError, match="not pinned"):
        benchmark._fetch(NoNetwork(), "resume_list_pdf/1.pdf")


def test_structured_comparison_uses_independent_source_fields():
    annotation = {
        "basicInfo":{"name":"Example Person","personalEmail":"p@example.invalid",
                     "phoneNumber":"1002003000"},
        "workExperience":[{
            "companyName":"Example Labs","position":"Engineer",
            "employmentPeriod":{"startDate":"2021.01","endDate":"2024.06"},
        }],
        "education":[{"school":"Example University"}],
    }
    exp = _truth(annotation)
    observed = _actual({"resume":{
        "name":"Example Person", "email":"p@example.invalid",
        "phone":"1002003000",
        "experience":[{"company":"Example Labs","role":"Engineer",
                       "start_date":"2021.01","end_date":"2024.06"}],
        "education":[{"heading":"Example University | Bachelor"}],
    }})
    assert all(assess(exp[k],observed[k])==(1,1) for k in exp)
    assert normalized("Example-Labs") == normalized("Example Labs")
    assert assess(["Python"],["does not mention it"]) == (0,1)
