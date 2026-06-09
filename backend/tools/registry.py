TOOLS = {
    "file_read": {
        "description": "Read approved local files",
        "enabled": True,
    },
    "project_search": {
        "description": "Search project folders",
        "enabled": True,
    },
    "terminal_command": {
        "description": "Execute approved shell commands",
        "enabled": False,
    },
    "memory_store": {
        "description": "Store long-term memory",
        "enabled": True,
    },
}


def list_tools():
    return TOOLS
