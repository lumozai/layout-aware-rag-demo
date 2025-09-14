import json
import hashlib
import subprocess
import tempfile
import logging
from pathlib import Path
from typing import List, Dict, Any
from sentence_transformers import SentenceTransformer
from docling.chunking import HybridChunker
from docling_core.transforms.chunker.tokenizer.huggingface import HuggingFaceTokenizer
from transformers import AutoTokenizer
from docling.document_converter import DocumentConverter
from models import ChunkData, DocumentMeta, PageMeta

# Set up logging
logger = logging.getLogger(__name__)


class DoclingProcessor:
    def __init__(self):
        self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
        # Initialize tokenizer-aware chunker aligned with embedding model
        tokenizer = HuggingFaceTokenizer(
            tokenizer=AutoTokenizer.from_pretrained('sentence-transformers/all-MiniLM-L6-v2')
        )
        self.chunker = HybridChunker(tokenizer=tokenizer)
        self.converter = DocumentConverter()

    def parse_pdf_with_docling(self, pdf_path: str) -> Dict[str, Any]:
        """Parse PDF using Docling CLI with bounding boxes and structure"""
        logger.info(f"Starting Docling processing for: {pdf_path}")

        with tempfile.TemporaryDirectory() as temp_dir:
            cmd = [
                'docling', pdf_path,
                '--output', temp_dir,
                '--ocr', '--to', 'json'
            ]
            logger.info(f"Running Docling command: {' '.join(cmd)}")
            logger.info(f"Output directory: {temp_dir}")

            result = subprocess.run(cmd, capture_output=True, text=True)

            logger.info(f"Docling command completed with return code: {result.returncode}")
            if result.stdout:
                logger.info(f"Docling stdout: {result.stdout}")
            if result.stderr:
                logger.error(f"Docling stderr: {result.stderr}")

            if result.returncode != 0:
                error_msg = f"Docling parsing failed with return code {result.returncode}. Stderr: {result.stderr}. Stdout: {result.stdout}"
                logger.error(error_msg)
                raise RuntimeError(error_msg)

            # Find the generated JSON file in the output directory
            pdf_name = Path(pdf_path).stem
            json_file = Path(temp_dir) / f"{pdf_name}.json"
            logger.info(f"Looking for JSON file: {json_file}")

            if not json_file.exists():
                # List all files in temp directory for debugging
                all_files = list(Path(temp_dir).iterdir())
                logger.warning(f"Expected JSON file {json_file} not found. Files in directory: {[str(f) for f in all_files]}")

                # Fallback: look for any JSON file in the directory
                json_files = list(Path(temp_dir).glob("*.json"))
                logger.info(f"Found JSON files: {[str(f) for f in json_files]}")
                if json_files:
                    json_file = json_files[0]
                    logger.info(f"Using JSON file: {json_file}")
                else:
                    error_msg = f"No JSON output file found in {temp_dir}. Available files: {[str(f) for f in all_files]}"
                    logger.error(error_msg)
                    raise RuntimeError(error_msg)

            logger.info(f"Reading JSON file: {json_file} (size: {json_file.stat().st_size} bytes)")
            with open(json_file, 'r') as f:
                data = json.load(f)
                logger.info(f"Successfully loaded JSON data. Top-level keys: {list(data.keys())}")
                if 'texts' in data:
                    logger.info(f"Found {len(data['texts'])} text items")
                if 'pages' in data:
                    logger.info(f"Found pages data with keys: {list(data['pages'].keys()) if isinstance(data['pages'], dict) else 'not a dict'}")
                return data

    def make_id(self, text: str, page: int) -> str:
        """Generate unique chunk ID from text and page number"""
        return hashlib.sha1(f"{page}:{text[:160]}".encode("utf-8")).hexdigest()

    def get_embedding(self, text: str) -> List[float]:
        """Generate 768-dimensional embedding vector"""
        embedding = self.embedding_model.encode(text)
        return embedding.tolist()

    def structure_aware_chunking(self, pdf_path: str) -> List[ChunkData]:
        """
        Create chunks using Docling's native HybridChunker that respects document structure
        """
        logger.info("Starting structure-aware chunking with Docling HybridChunker")

        # Convert PDF to DoclingDocument using native converter
        result = self.converter.convert(pdf_path)
        doc = result.document

        # Use Docling's native chunker
        chunks_data = []
        for chunk in self.chunker.chunk(doc):
            # Extract metadata from chunk
            chunk_meta = chunk.meta
            page_num = 1
            bbox = [0, 0, 0, 0]
            headings = []

            # Extract page and bbox from chunk metadata
            if hasattr(chunk_meta, 'doc_items') and chunk_meta.doc_items:
                logger.debug(f"Chunk has {len(chunk_meta.doc_items)} doc_items")

                # Collect all bounding boxes from all doc items
                all_bboxes = []
                for i, doc_item in enumerate(chunk_meta.doc_items):
                    if hasattr(doc_item, 'prov') and doc_item.prov:
                        prov = doc_item.prov[0]
                        page_num = getattr(prov, 'page_no', 1)
                        if hasattr(prov, 'bbox'):
                            bbox_obj = prov.bbox
                            item_bbox = [bbox_obj.l, bbox_obj.t, bbox_obj.r, bbox_obj.b]
                            all_bboxes.append(item_bbox)
                            logger.debug(f"Doc item {i}: bbox {item_bbox}")

                # Merge all bounding boxes into one
                if all_bboxes:
                    # Calculate merged bbox: min left/bottom, max right/top
                    min_l = min(b[0] for b in all_bboxes)
                    max_t = max(b[1] for b in all_bboxes)  # top is higher Y in bottom-left system
                    max_r = max(b[2] for b in all_bboxes)
                    min_b = min(b[3] for b in all_bboxes)  # bottom is lower Y in bottom-left system
                    bbox = [min_l, max_t, max_r, min_b]
                    logger.debug(f"Merged bbox: {bbox} (from {len(all_bboxes)} individual boxes)")

            # Extract headings from chunk metadata
            if hasattr(chunk_meta, 'headings') and chunk_meta.headings:
                headings = [h.text if hasattr(h, 'text') else str(h) for h in chunk_meta.headings]

            chunk_text = chunk.text.strip()
            if not chunk_text:
                continue

            chunk_id = self.make_id(chunk_text, page_num)
            logger.debug(f"Creating chunk {len(chunks_data)+1} with ID {chunk_id[:8]}... on page {page_num} with {len(chunk_text)} chars")

            chunks_data.append(ChunkData(
                id=chunk_id,
                text=chunk_text,
                page_num=page_num,
                bbox=bbox,
                headings=headings,
                embedding=self.get_embedding(chunk_text)
            ))

        logger.info(f"Chunking completed using HybridChunker. Built {len(chunks_data)} chunks")
        return chunks_data

    def extract_document_metadata(self, docling_data: Dict[str, Any],
                                doc_id: str, source_path: str) -> DocumentMeta:
        """Extract document metadata from parsed content"""
        title = docling_data.get("title", Path(source_path).stem)
        return DocumentMeta(
            id=doc_id,
            title=title,
            source_uri=f"file://{source_path}",
            family="general"
        )

    def extract_page_metadata(self, docling_data: Dict[str, Any],
                            doc_id: str) -> List[PageMeta]:
        """Extract page metadata with dimensions"""
        pages = []
        page_dims = {}

        # Extract page dimensions from the new format
        pages_data = docling_data.get("pages", {})
        if isinstance(pages_data, dict):
            for page_key, page_info in pages_data.items():
                if isinstance(page_info, dict):
                    page_num = int(page_key)
                    size = page_info.get("size", {})
                    width = size.get("width", 612)
                    height = size.get("height", 792)
                    page_dims[page_num] = {"width": width, "height": height}

        # If no pages data, try to extract from texts
        if not page_dims:
            for item in docling_data.get("texts", []):
                if isinstance(item, dict):
                    prov = item.get("prov", [])
                    if prov and isinstance(prov, list) and len(prov) > 0:
                        first_prov = prov[0]
                        if isinstance(first_prov, dict):
                            page_num = first_prov.get("page_no", 1)
                            if page_num not in page_dims:
                                page_dims[page_num] = {"width": 612, "height": 792}

        # Create PageMeta objects
        for page_num, dims in page_dims.items():
            pages.append(PageMeta(
                docId=doc_id,
                page_num=page_num,
                width=dims["width"],
                height=dims["height"]
            ))

        return pages