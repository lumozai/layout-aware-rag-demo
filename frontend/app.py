import chainlit as cl
import httpx
import os
from dotenv import load_dotenv

load_dotenv()

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8001")

@cl.on_chat_start
async def start():
    """Initialize the chat session"""
    await cl.Message(
        content="""# Layout Aware RAG with Evidence Pins

Welcome! This demo showcases a RAG system that provides clickable citations linking directly to PDF regions.

**How to use:**
1. Upload a PDF document using the file upload button
2. Ask questions about the document content
3. Get answers with clickable citations that highlight exact regions in the PDF

Upload a PDF to get started!
        """,
    ).send()

@cl.on_message
async def main(message: cl.Message):
    """Handle incoming messages"""

    if message.elements:
        await handle_file_upload(message)
    else:
        await handle_query(message.content)

async def handle_file_upload(message: cl.Message):
    """Process uploaded PDF files"""
    files = [file for file in message.elements if file.type == "file"]

    if not files:
        await cl.Message(content="No files detected. Please upload a PDF file.").send()
        return

    pdf_file = files[0]

    if not pdf_file.name.lower().endswith('.pdf'):
        await cl.Message(content="Please upload a PDF file only.").send()
        return

    # Send initial processing message
    loading_msg = await cl.Message(content="🔄 Processing PDF... This may take a moment.").send()

    try:
        async with httpx.AsyncClient() as client:
            with open(pdf_file.path, 'rb') as f:
                files_data = {"file": (pdf_file.name, f, "application/pdf")}
                response = await client.post(f"{BACKEND_URL}/upload", files=files_data, timeout=120.0)

        if response.status_code == 200:
            result = response.json()
            # Send success message
            await cl.Message(content=f"""✅ **PDF Processed Successfully!**

**Document:** {result['title']}
**Pages:** {result['pages']}
**Chunks created:** {result['chunks']}

You can now ask questions about this document. The system will provide answers with clickable citations that link to exact regions in the PDF.

Try asking something like:
- "What are the main topics covered?"
- "Tell me about [specific topic]"
- "What requirements are mentioned?"
            """).send()
        else:
            error_msg = response.json().get('detail', 'Unknown error occurred')
            await cl.Message(content=f"❌ **Upload failed:** {error_msg}").send()

    except httpx.TimeoutException:
        await cl.Message(content="❌ **Timeout:** PDF processing took too long. Please try a smaller file.").send()
    except Exception as e:
        await cl.Message(content=f"❌ **Error:** {str(e)}").send()

async def handle_query(query: str):
    """Process user queries"""
    if not query.strip():
        await cl.Message(content="Please enter a question about your uploaded document.").send()
        return

    # Send initial searching message
    loading_msg = await cl.Message(content="🔍 Searching documents...").send()

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{BACKEND_URL}/query",
                json={
                    "query": query,
                    "doc_type": "general",
                    "k": 10,
                    "limit": 5
                },
                timeout=30.0
            )

        if response.status_code == 200:
            result = response.json()
            answer = result['answer']
            chunks = result['chunks']
            cited_chunks = result['cited_chunks']

            formatted_answer = format_answer_with_links(answer, cited_chunks)

            elements = []
            if chunks:
                chunks_text = "**Retrieved chunks:**\n\n"
                for i, chunk in enumerate(chunks[:3], 1):
                    chunk_data = chunk['chunk']
                    score = chunk['score']
                    text_preview = chunk_data['text'][:200] + "..." if len(chunk_data['text']) > 200 else chunk_data['text']
                    chunks_text += f"**{i}.** (Score: {score:.3f}) {text_preview}\n\n"

                elements.append(
                    cl.Text(name="retrieved_chunks", content=chunks_text, display="side")
                )

            # Send result message
            await cl.Message(content=formatted_answer, elements=elements).send()
        else:
            error_msg = response.json().get('detail', 'Unknown error occurred')
            await cl.Message(content=f"❌ **Query failed:** {error_msg}").send()

    except Exception as e:
        await cl.Message(content=f"❌ **Error:** {str(e)}").send()

def format_answer_with_links(answer: str, cited_chunks: dict) -> str:
    """Format answer with clickable citation links"""
    if not cited_chunks:
        return answer

    formatted_answer = answer

    for chunk_id, chunk_info in cited_chunks.items():
        bbox = chunk_info['bbox']
        doc_id = chunk_info['docId']
        page = chunk_info['page']

        viewer_url = f"{BACKEND_URL}/viewer?doc={doc_id}&page={page}&bbox={bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}"

        citation_link = f"[📍 {chunk_id[:8]}...]({viewer_url})"
        formatted_answer = formatted_answer.replace(f"[{chunk_id}]", citation_link)

    if cited_chunks:
        formatted_answer += "\n\n---\n**💡 Click the 📍 links above to view the exact regions in the PDF that support this answer.**"

    return formatted_answer

if __name__ == "__main__":
    cl.run()