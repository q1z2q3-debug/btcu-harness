"""
BTCU-LangChain Integration Demo.

Shows how to create a LangChain agent enhanced with BTCU cognitive middleware.
Requires OPENAI_API_KEY environment variable for LLM calls.
"""

import os
import sys

from langchain_core.messages import HumanMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI

from btcu_harness.langchain_integration import create_btcu_agent_from_env


@tool
def calculator(expression: str) -> str:
    """Evaluate a mathematical expression and return the result.
    Use this for any math calculations.
    """
    try:
        result = eval(expression, {"__builtins__": {}}, {})
        return f"{expression} = {result}"
    except Exception as e:
        return f"Error calculating '{expression}': {e}"


@tool
def search(query: str) -> str:
    """Search for information. Use this when you need to look up facts.
    (Demo: returns mock results.)
    """
    mock_results = {
        "python": "Python is a high-level programming language.",
        "btcu": "BTCU Harness is a structured cognitive architecture.",
        "default": f"Search results for '{query}': No results found.",
    }
    return mock_results.get(query.lower(), mock_results["default"])


def main() -> None:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY not set")
        sys.exit(1)

    tools = [calculator, search]
    # ChatOpenAI reads OPENAI_API_KEY from env automatically
    model = ChatOpenAI(model="gpt-4o-mini")

    # Create BTCU-enhanced agent
    agent = create_btcu_agent_from_env(
        model=model,
        tools=tools,
        verbose=True,
    )

    queries = [
        "What is 25 * 17 + 33?",
        "Search for information about Python, then calculate 100 / 7.",
        "What is the square root of 144?",
    ]

    for query in queries:
        print(f"\n{'='*60}")
        print(f"Query: {query}")
        print(f"{'='*60}")

        result = agent.invoke({"messages": [HumanMessage(query)]})

        # Extract final response
        messages = result.get("messages", [])
        if messages:
            last = messages[-1]
            print(f"Response: {getattr(last, 'content', str(last))}")

    # Print BTCU stats
    for mw in agent.middlewares if hasattr(agent, "middlewares") else []:
        if hasattr(mw, "get_stats"):
            print(f"\n{'='*60}")
            print("BTCU Statistics:")
            print(f"{'='*60}")
            stats = mw.get_stats()
            for k, v in stats.items():
                print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
