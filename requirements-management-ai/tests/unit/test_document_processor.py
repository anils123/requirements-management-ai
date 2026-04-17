# tests/unit/test_document_processor.py
import pytest
from unittest.mock import Mock, patch
import json
from src.lambda.document_processor.document_processor import (
    extract_text_with_textract,
    extract_entities_with_comprehend,
    chunk_document,
    generate_embeddings
)

class TestDocumentProcessor:
    """Test cases for document processor functionality."""
    
    @patch('boto3.client')
    def test_extract_text_with_textract_success(self, mock_boto_client):
        """Test successful text extraction with Textract."""
        
        # Mock Textract responses
        mock_textract = Mock()
        mock_boto_client.return_value = mock_textract
        
        mock_textract.start_document_text_detection.return_value = {
            'JobId': 'test-job-123'
        }
        
        mock_textract.get_document_text_detection.return_value = {
            'JobStatus': 'SUCCEEDED',
            'Blocks': [
                {
                    'BlockType': 'LINE',
                    'Text': 'This is a test requirement.'
                },
                {
                    'BlockType': 'LINE', 
                    'Text': 'Another requirement line.'
                }
            ]
        }
        
        # Test extraction
        result = extract_text_with_textract('test-document.pdf')
        
        assert 'This is a test requirement.' in result
        assert 'Another requirement line.' in result
        mock_textract.start_document_text_detection.assert_called_once()
    
    @patch('boto3.client')
    def test_extract_entities_with_comprehend(self, mock_boto_client):
        """Test entity extraction with Comprehend."""
        
        mock_comprehend = Mock()
        mock_boto_client.return_value = mock_comprehend
        
        mock_comprehend.detect_entities.return_value = {
            'Entities': [
                {
                    'Text': 'authentication',
                    'Type': 'OTHER',
                    'Score': 0.95
                },
                {
                    'Text': 'security',
                    'Type': 'OTHER',
                    'Score': 0.92
                }
            ]
        }
        
        text = "The system must implement authentication and security measures."
        entities = extract_entities_with_comprehend(text)
        
        assert len(entities) == 2
        assert entities[0]['Text'] == 'authentication'
        assert entities[1]['Text'] == 'security'
    
    def test_chunk_document(self):
        """Test document chunking functionality."""
        
        text = " ".join([f"word{i}" for i in range(100)])  # 100 words
        chunks = chunk_document(text, chunk_size=20, overlap=5)
        
        assert len(chunks) > 1
        assert chunks[0]['chunk_id'] == 0
        assert chunks[0]['start_word'] == 0
        assert chunks[0]['end_word'] == 20
        
        # Test overlap
        assert chunks[1]['start_word'] == 15  # 20 - 5 overlap
    
    @patch('boto3.client')
    def test_generate_embeddings(self, mock_boto_client):
        """Test embedding generation."""
        
        mock_bedrock = Mock()
        mock_boto_client.return_value = mock_bedrock
        
        mock_response = Mock()
        mock_response.read.return_value = json.dumps({
            'embedding': [0.1, 0.2, 0.3, 0.4, 0.5]
        }).encode()
        
        mock_bedrock.invoke_model.return_value = {
            'body': mock_response
        }
        
        chunks = [
            {'text': 'Test chunk 1'},
            {'text': 'Test chunk 2'}
        ]
        
        embeddings = generate_embeddings(chunks)
        
        assert len(embeddings) == 2
        assert len(embeddings[0]) == 5
        assert embeddings[0] == [0.1, 0.2, 0.3, 0.4, 0.5]
