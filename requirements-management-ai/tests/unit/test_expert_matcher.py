def test_expert_matcher_stub():
    from src.lambda.expert_matcher import expert_matcher
    assert callable(expert_matcher.handler)
