import pandas as pd
import pytest

from fhirlearn.client import active_servers
from fhirlearn.labs import ifcc_to_ngsp, normalize_hba1c, observations_to_df, summarize


def obs(value, unit="%", code="%", system="http://unitsofmeasure.org", pid="1", **extra):
    q = {"value": value, "unit": unit, "code": code, "system": system, **extra}
    return {"resourceType": "Observation", "id": f"o{value}", "subject": {"reference": f"Patient/{pid}"},
            "valueQuantity": {k: v for k, v in q.items() if v is not None}}


def test_percent_variants_ok():
    assert normalize_hba1c(obs(7.1)) == (7.1, "ok")
    assert normalize_hba1c(obs(7.1, unit="percent")) == (7.1, "ok")
    assert normalize_hba1c(obs(7.1, code=None, system=None)) == (7.1, "ok")


def test_mmol_mol_converted():
    assert ifcc_to_ngsp(48) == pytest.approx(6.54, abs=0.01)  # 48 mmol/mol is the 6.5% threshold
    pct, status = normalize_hba1c(obs(64, unit="mmol/mol", code=None, system=None))
    assert status == "converted" and pct == pytest.approx(8.01, abs=0.01)


def test_implausible_and_odd_values():
    assert normalize_hba1c(obs(45, unit="percent"))[1] == "implausible % value"
    assert normalize_hba1c(obs(112))[1] == "implausible % value"
    assert normalize_hba1c(obs(14, comparator=">"))[1] == "comparator >"
    assert normalize_hba1c(obs(7, unit="mg/dL", code="mg/dL"))[1] == "unknown unit 'mg/dL'"
    assert normalize_hba1c({"valueString": "6.8%"})[1] == "no valueQuantity"


def test_summarize_counts_patients_not_observations():
    df = observations_to_df([obs(7.0, pid="a"), obs(8.0, pid="a"), obs(5.0, pid="b"), obs(45, unit="percent", pid="c")])
    assert summarize(df) == {"observations": 4, "patients": 3, "patients_ge_6_5": 1, "unusable_observations": 1}


def test_active_servers(monkeypatch):
    monkeypatch.delenv("FHIRLEARN_SERVERS", raising=False)
    assert active_servers() == ["smart", "hapi"]
    monkeypatch.setenv("FHIRLEARN_SERVERS", "hapi")
    assert active_servers() == ["hapi"]
    monkeypatch.setenv("FHIRLEARN_SERVERS", "nope")
    with pytest.raises(ValueError):
        active_servers()
