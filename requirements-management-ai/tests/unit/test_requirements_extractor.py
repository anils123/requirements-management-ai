def test_requirements_extractor_stub():
    from src.lambda.requirements_extractor import requirements_extractor
    assert callable(requirements_extractor.handler)
