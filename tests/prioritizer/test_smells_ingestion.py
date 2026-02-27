from prioritizer.ingestion.smells_ingestion import add_further_context, read_and_store_relevant_smells
import pytest

@pytest.mark.skip(reason="The test takes a long time")
def test_add_further_context():
    project_path = "test_projects/simapy"
    smells = ['Long Method', 'High Cyclomatic Complexity', 'Feature Envy', 'Cyclic Dependency']

    smells_dic = read_and_store_relevant_smells(smells) 
    assert smells_dic is not None

    output = add_further_context(project_path, smells_dic)
    assert output[1]["git_analysis"] is not None


