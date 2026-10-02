import pytest
@pytest.mark.parametrize("value", [1, 2, 3, 4], ids=["nested::id", "1 skipped", "1 error", "1 deselected"])
def test_parameter(value):
    assert value > 0
