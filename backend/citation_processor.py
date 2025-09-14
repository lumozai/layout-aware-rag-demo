import re
from typing import List, Dict, Any
from models import QueryResult


class CitationProcessor:
    def __init__(self, neo4j_handler):
        self.neo4j_handler = neo4j_handler

    def generate_answer_with_citations(self, query: str, search_results: List[QueryResult]) -> str:
        """
        Generate an answer using retrieved chunks with inline citations.
        This is a simplified implementation - in production you'd use an LLM.
        """
        if not search_results:
            return "No relevant information found to answer your query."

        # Simple keyword-based answer generation for demonstration
        if "handicap" in query.lower():
            # Look for handicap definition in the chunks
            for result in search_results:
                chunk_text = result.chunk['text'].lower()
                if "handicap" in chunk_text and ("means" in chunk_text or "defined" in chunk_text or "definition" in chunk_text):
                    # Extract the relevant part
                    lines = result.chunk['text'].split('\n')
                    for line in lines:
                        if "handicap" in line.lower():
                            return f"According to the document: {line.strip()} [{result.chunk['id']}]"

            # Fallback to general information
            relevant_chunks = []
            for result in search_results[:2]:
                if "handicap" in result.chunk['text'].lower():
                    relevant_chunks.append(result)

            if relevant_chunks:
                answer = f"Based on the Fair Housing Act documents, the term 'handicap' appears in the following context:\n\n"
                for result in relevant_chunks:
                    # Find sentences containing handicap
                    sentences = result.chunk['text'].split('.')
                    for sentence in sentences:
                        if "handicap" in sentence.lower() and len(sentence.strip()) > 10:
                            answer += f"• {sentence.strip()}. [{result.chunk['id']}]\n\n"
                            break
                return answer.strip()

        # General fallback for other queries
        answer = f"Based on the retrieved documents:\n\n"
        for i, result in enumerate(search_results[:2]):
            chunk_text = result.chunk['text']
            # Take first meaningful sentence or paragraph
            if len(chunk_text) > 100:
                # Try to find a complete sentence
                sentences = chunk_text.split('.')
                first_sentence = sentences[0].strip()
                if len(first_sentence) > 50:
                    answer += f"• {first_sentence}. [{result.chunk['id']}]\n\n"
                else:
                    text_preview = chunk_text[:200] + "..."
                    answer += f"• {text_preview} [{result.chunk['id']}]\n\n"
            else:
                answer += f"• {chunk_text} [{result.chunk['id']}]\n\n"

        return answer.strip()

    def extract_cited_chunks(self, answer_text: str, search_results: List[QueryResult]) -> Dict[str, Dict[str, Any]]:
        """Extract chunks that were cited in the answer"""
        cited_chunks = {}

        chunk_pattern = r'\[([^\]]+)\]'
        cited_ids = re.findall(chunk_pattern, answer_text)

        for result in search_results:
            chunk_id = result.chunk['id']
            if chunk_id in cited_ids:
                cited_chunks[chunk_id] = {
                    "docId": result.doc['id'],
                    "page": result.chunk['page_num'],
                    "bbox": result.chunk['bbox'],
                    "text": result.chunk['text']
                }

        return cited_chunks

    def linkify_citations(self, text: str, id_to_payload: Dict[str, Dict[str, Any]]) -> str:
        """Convert citation IDs to clickable evidence links"""
        def repl(match):
            chunk_id = match.group(1).strip()
            payload = id_to_payload.get(chunk_id)

            if not payload:
                return f"[{chunk_id}]"

            bbox = payload['bbox']
            url = (
                f"/viewer?doc={payload['docId']}&page={payload['page']}"
                f"&bbox={bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}"
            )

            return f"[<a href='{url}' target='_blank' rel='noopener'>{chunk_id}</a>]"

        return re.sub(r'\[([^\]]+)\]', repl, text)