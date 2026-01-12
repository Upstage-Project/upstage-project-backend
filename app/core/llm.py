from app.repository.client.llm_client import UpstageClient

_client = UpstageClient()

def get_solar_chat():
    return _client.get_chat_model()

def get_upstage_embeddings():
    return _client.get_embedding_model()