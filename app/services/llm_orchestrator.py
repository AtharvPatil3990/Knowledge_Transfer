from langchain_community.embeddings.fastembed import FastEmbedEmbeddings


# BGE-small produces 384-dimensional vectors.
embeddings_model = FastEmbedEmbeddings(model_name="BAAI/bge-small-en-v1.5")
