import pandas as pd

from fhirlearn.patients import has_name, patients_to_df


def test_has_name_variants():
    assert has_name({"name": [{"family": "Smith"}]})
    assert has_name({"name": [{"given": ["Ann"]}]})
    assert has_name({"name": [{"text": "Ann Smith"}]})
    assert not has_name({})
    assert not has_name({"name": []})
    assert not has_name({"name": [{"use": "official"}]})
    assert not has_name({"name": [{"given": [""]}]})


def test_patients_to_df_handles_missing_fields():
    df = patients_to_df([
        {"id": "1", "gender": "female", "birthDate": "1980-01-01", "name": [{"family": "X"}]},
        {"id": "2"},
    ])
    assert list(df.columns) == ["id", "gender", "birthDate", "has_name"]
    assert pd.isna(df.loc[1, "gender"]) and not df.loc[1, "has_name"]


def test_patients_to_df_empty():
    assert patients_to_df([]).empty
