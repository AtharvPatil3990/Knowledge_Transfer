from langchain_classic.chains.combine_documents import create_stuff_documents_chain
from langchain_community.embeddings.fastembed import FastEmbedEmbeddings
from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate, PromptTemplate
from langchain_groq import ChatGroq

from app.core.config import settings
from app.db.supabase_client import get_supabase_client

SYSTEM_PROMPT = (
    "You are the Alpha Squad Knowledge Handover AI. Summarize the team's work "
    "using ONLY the provided CONTEXT. You MUST cite your sources using the "
    "exact Source URL provided inline using Markdown format, e.g., "
    "[1](https://www.google.com/search?q=URL). Never invent URLs.\n\n"
    "CONTEXT:\n{context}"
)


async def generate_handover_response(
    team_id: str,
    question: str,
    token: str,
) -> str:
    embeddings = FastEmbedEmbeddings(model_name="BAAI/bge-small-en-v1.5")
    query_embedding = embeddings.embed_query(question)

    client = get_supabase_client()
    client.postgrest.auth(token)
    result = client.rpc(
        "match_documents",
        {
            "query_embedding": query_embedding,
            "target_team_id": team_id,
        },
    ).execute()

    documents = [
        Document(
            page_content=row["content"],
            metadata={"source_url": row["source_url"]},
        )
        for row in (result.data or [])
    ]
    
    print(f"Retrieved {len(documents)} documents: {result.data}")
    
    llm = ChatGroq(
        model_name="openai/gpt-oss-120b",
        temperature=0.2,
        api_key=settings.GROQ_API_KEY,
    )
    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        ("human", "{input}"),
    ])
    document_prompt = PromptTemplate.from_template(
        "Text: {page_content}\nSource: {source_url}"
    )
    chain = create_stuff_documents_chain(
        llm,
        prompt,
        document_prompt=document_prompt,
    )

    print(f"Retrieved {len(documents)} documents for team {team_id} and question '{question}'")
    response = await chain.ainvoke({
        "input": question,
        "context": documents,
    })
    return response
