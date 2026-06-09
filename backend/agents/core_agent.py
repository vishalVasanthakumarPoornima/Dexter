from backend.memory.qdrant_memory import store_memory, query_memory
from backend.utils.logger import log_action


def run_agent(message: str) -> str:
    store_memory(message, metadata={"source": "chat"})

    top_memories = query_memory(message)
    memory_texts = [
        memory["text"]
        for memory in top_memories
        if memory.get("text") and memory["text"] != message
    ]

    response = f"Dexter received: {message}"

    if memory_texts:
        response += "\nRelated memories: " + "; ".join(memory_texts)

    log_action("chat", {"input": message, "response": response})

    return response
