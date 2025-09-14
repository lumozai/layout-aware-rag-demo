from neo4j import GraphDatabase
from typing import List, Dict, Any
from models import ChunkData, DocumentMeta, PageMeta, QueryResult
import os
import logging
import traceback

logger = logging.getLogger(__name__)


class Neo4jHandler:
    def __init__(self):
        self.uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self.user = os.getenv("NEO4J_USER", "neo4j")
        self.password = os.getenv("NEO4J_PASSWORD", "password")
        self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))

    def close(self):
        self.driver.close()

    def setup_constraints_and_indexes(self):
        """Create constraints and vector index"""
        with self.driver.session() as session:
            session.run("""
                CREATE CONSTRAINT doc_id IF NOT EXISTS
                FOR (d:Document) REQUIRE d.id IS UNIQUE
            """)

            session.run("""
                CREATE CONSTRAINT page_key IF NOT EXISTS
                FOR (p:Page) REQUIRE (p.docId, p.page_num) IS UNIQUE
            """)

            session.run("""
                CREATE CONSTRAINT chunk_id IF NOT EXISTS
                FOR (c:Chunk) REQUIRE c.id IS UNIQUE
            """)

            try:
                session.run("""
                    CREATE VECTOR INDEX chunk_vec IF NOT EXISTS
                    FOR (c:Chunk) ON (c.embedding)
                    OPTIONS {
                      indexConfig: {
                        `vector.dimensions`: 384,
                        `vector.similarity_function`: 'cosine'
                      }
                    }
                """)
                print("✅ Vector index created successfully")
            except Exception as e:
                print(f"Vector index creation failed: {e}")

    def upsert_document(self, doc: DocumentMeta, pages: List[PageMeta], chunks: List[ChunkData]):
        """Store document, pages, and chunks in Neo4j"""
        with self.driver.session() as session:
            session.execute_write(self._upsert_document_tx, doc, pages, chunks)

    def _upsert_document_tx(self, tx, doc: DocumentMeta, pages: List[PageMeta], chunks: List[ChunkData]):
        """Transaction for upserting document data"""
        tx.run("""
            MERGE (d:Document {id: $id})
            SET d.title = $title, d.source_uri = $src, d.family = $family
        """, id=doc.id, title=doc.title, src=doc.source_uri, family=doc.family)

        for page in pages:
            tx.run("""
                MERGE (p:Page {docId: $docId, page_num: $n})
                SET p.width = $w, p.height = $h
                WITH p
                MATCH (d:Document {id: $docId})
                MERGE (p)-[:OF]->(d)
            """, docId=page.docId, n=page.page_num, w=page.width, h=page.height)

        for chunk in chunks:
            tx.run("""
                MERGE (c:Chunk {id: $id})
                SET c.text = $text, c.page_num = $page, c.bbox = $bbox,
                    c.headings = $headings, c.embedding = $emb
                WITH c
                MATCH (p:Page {docId: $docId, page_num: $page})
                MERGE (c)-[:IN_PAGE]->(p)
            """,
                id=chunk.id, text=chunk.text, page=chunk.page_num,
                bbox=chunk.bbox, headings=chunk.headings, emb=chunk.embedding,
                docId=doc.id)

    def vector_search(self, query_embedding: List[float], k: int = 10,
                     doc_type: str = None, limit: int = 5) -> List[QueryResult]:
        """Perform vector search with optional document type filter"""
        logger.info(f"Neo4j vector search: k={k}, limit={limit}, doc_type={doc_type}, embedding_dim={len(query_embedding)}")

        with self.driver.session() as session:
            # First check how many chunks exist
            try:
                count_result = session.run("MATCH (c:Chunk) RETURN count(c) as total").single()
                total_chunks = count_result["total"] if count_result else 0
                logger.info(f"Total chunks in Neo4j: {total_chunks}")

                # Check vector index status
                index_check = list(session.run("SHOW INDEXES YIELD name, state WHERE name = 'chunk_vec'"))
                logger.info(f"Vector index 'chunk_vec' status: {index_check}")

            except Exception as e:
                logger.error(f"Error checking database status: {e}")

            query = """
                CALL db.index.vector.queryNodes('chunk_vec', $k, $queryEmbedding)
                YIELD node AS c, score
            """

            if doc_type and doc_type != "general":
                query += " WHERE c.family = $docType OR EXISTS((c)-[:IN_PAGE]->(:Page)-[:OF]->(:Document {family: $docType})) "

            query += """
                MATCH (c)-[:IN_PAGE]->(p:Page)-[:OF]->(d:Document)
                RETURN c {.id, .text, .bbox, .page_num, .headings} AS chunk,
                       d {.id, .title} AS doc,
                       p.page_num AS page,
                       score
                ORDER BY score DESC
                LIMIT $limit
            """

            params = {
                "k": k,
                "queryEmbedding": query_embedding,
                "limit": limit
            }

            if doc_type and doc_type != "general":
                params["docType"] = doc_type

            logger.info(f"Executing Neo4j vector query with params: {list(params.keys())}")

            try:
                results = []
                for record in session.run(query, params):
                    results.append(QueryResult(
                        chunk=record["chunk"],
                        doc=record["doc"],
                        page=record["page"],
                        score=record["score"]
                    ))

                logger.info(f"Neo4j vector search returned {len(results)} results")
                if results:
                    for i, result in enumerate(results[:3]):
                        logger.info(f"Result {i+1}: score={result.score:.3f}, chunk_id={result.chunk['id'][:8]}...")

                return results

            except Exception as e:
                logger.error(f"Neo4j vector search failed: {str(e)}")
                logger.error(f"Full traceback: {traceback.format_exc()}")
                logger.info("Vector search failed - returning empty results")
                return []

    def get_chunk_by_id(self, chunk_id: str) -> Dict[str, Any]:
        """Retrieve chunk details by ID for citation linking"""
        with self.driver.session() as session:
            result = session.run("""
                MATCH (c:Chunk {id: $id})-[:IN_PAGE]->(p:Page)-[:OF]->(d:Document)
                RETURN c {.id, .text, .bbox, .page_num, .headings} AS chunk,
                       d {.id, .title} AS doc,
                       p.page_num AS page
            """, id=chunk_id)

            record = result.single()
            if record:
                return {
                    "chunk": record["chunk"],
                    "doc": record["doc"],
                    "page": record["page"]
                }
            return None