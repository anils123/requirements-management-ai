def test_document_processor_stub():
    from src.lambda.document_processor import document_processor
    assert callable(document_processor.handler)
