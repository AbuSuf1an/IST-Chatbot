import time
import psycopg2
from your_project.database import get_database_connection
from your_project.ai_service import generate_embedding

def test_vector_search_performance():
    """Test vector search with different document counts"""
    conn = get_database_connection()
    cursor = conn.cursor()
    
    # Get current document count
    cursor.execute("SELECT COUNT(*) FROM documents")
    doc_count = cursor.fetchone()[0]
    
    test_queries = [
        "computer science admission",
        "engineering courses",
        "campus facilities",
        "application process",
        "fee structure"
    ]
    
    results = []
    
    for query in test_queries:
        # Generate embedding for query
        start_time = time.time()
        query_embedding = generate_embedding(query)
        embedding_time = time.time() - start_time
        
        # Perform vector search
        start_time = time.time()
        cursor.execute("""
            SELECT content, source, 1 - (embedding <=> %s) as similarity
            FROM documents 
            WHERE 1 - (embedding <=> %s) > 0.7
            ORDER BY embedding <=> %s 
            LIMIT 5
        """, (query_embedding, query_embedding, query_embedding))
        
        search_results = cursor.fetchall()
        search_time = time.time() - start_time
        
        results.append({
            "query": query,
            "embedding_time": embedding_time,
            "search_time": search_time,
            "total_time": embedding_time + search_time,
            "results_count": len(search_results),
            "avg_similarity": sum(r[2] for r in search_results) / len(search_results) if search_results else 0
        })
    
    # Print results
    print(f"Database contains {doc_count} documents")
    print("\nVector Search Performance Results:")
    print("-" * 80)
    
    total_embedding_time = sum(r["embedding_time"] for r in results)
    total_search_time = sum(r["search_time"] for r in results)
    
    print(f"Average embedding generation time: {total_embedding_time/len(results):.3f}s")
    print(f"Average search time: {total_search_time/len(results):.3f}s")
    print(f"Average total query time: {(total_embedding_time + total_search_time)/len(results):.3f}s")
    
    cursor.close()
    conn.close()

if __name__ == "__main__":
    test_vector_search_performance()