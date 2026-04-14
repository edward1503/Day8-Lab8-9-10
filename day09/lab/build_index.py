import chromadb, os
from sentence_transformers import SentenceTransformer

def build_index():
    print("Khởi tạo PersistentClient tại ./chroma_db ...")
    client = chromadb.PersistentClient(path='./chroma_db')
    col = client.get_or_create_collection('day09_docs', metadata={"hnsw:space": "cosine"})
    
    print("Tải model SentenceTransformer ('all-MiniLM-L6-v2') ...")
    model = SentenceTransformer('all-MiniLM-L6-v2')

    docs_dir = './data/docs'
    for fname in os.listdir(docs_dir):
        if not fname.endswith('.txt'): continue
        with open(os.path.join(docs_dir, fname), encoding="utf-8") as f:
            content = f.read()
            
        print(f"Đang index file: {fname}")
        embedding = model.encode(content).tolist()
        col.upsert(
            documents=[content],
            metadatas=[{"source": fname}],
            ids=[fname],
            embeddings=[embedding]
        )
    print("Hoàn tất! Index data sẵn sàng tại thư mục ./chroma_db")

if __name__ == '__main__':
    build_index()
