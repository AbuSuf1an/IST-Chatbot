import json

def test_chunk_index():
    """Test to see if chunk_index is being set properly"""
    
    # Simulate what your process_scraped_content should create
    test_doc = {
        'filename': 'web_test_chunk_1.txt',
        'content': 'Test content',
        'embedding': [0.1, 0.2, 0.3],  # Dummy embedding
        'metadata': json.dumps({
            'source_url': 'https://ist.edu.bd/test',
            'page_title': 'Test Page',
            'chunk_index': 1,  # This should be set
            'total_chunks': 2,
            'content_type': 'web_scraped',
            'word_count': 2
        })
    }
    
    print("Test document structure:")
    print(f"filename: {test_doc['filename']}")
    print(f"chunk_index in doc: {test_doc.get('chunk_index', 'MISSING!')}")
    print(f"chunk_index in metadata: {json.loads(test_doc['metadata']).get('chunk_index', 'MISSING!')}")
    
    # This is what your insert statement uses:
    chunk_index_value = test_doc.get('chunk_index', 0)
    print(f"chunk_index for database: {chunk_index_value}")
    
    if chunk_index_value is None:
        print("❌ ERROR: chunk_index is None!")
    else:
        print("✅ chunk_index looks good")

if __name__ == "__main__":
    test_chunk_index()