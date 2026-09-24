import json
from openai import OpenAI
from openai.types.chat import ChatCompletion
from app.config import Config
from app.schemas.base_tool_schema import Tool, Mode


def __get_llm() -> OpenAI:
    try:
        if not Config.API_KEY:
            raise RuntimeError("OPENROUTER_API_KEY is not set")

        client = OpenAI(api_key=Config.API_KEY, base_url=Config.BASE_URL)

        return client
    except Exception as e:
        print(f"Unable to configure ai model client due to {e}")


def __invoke_tool_and_get_response(
    prev_response: ChatCompletion,
    available_tools: dict[str, Tool],
) -> list[dict]:
    """
    This will call all the tool necessary and return final response by llm after all tool calls.

    Parameters
    ----------
    prev_response: ChatCompletion
        This the original response from the first query asked.
    available_tools: dict[str, Tool]
        This is dict containing all available tools and there callable function.

    Returns
    -------
    tool_call_results: list[dict]
        This all the tools called in single agent loop.
    """
    tool_call_results = []
    for tool_call in prev_response.tool_calls:
        function_name = tool_call.function.name
        # If function name in available tool and is valid
        if function_name in available_tools:
            tool = available_tools[function_name]
            arguments = json.loads(tool_call.function.arguments)
            tool_result = tool["function"](**arguments)
            tool_call_results.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(tool_result, ensure_ascii=False),
                }
            )
    return tool_call_results


def _call_reactive_agent(query: str, tools: dict[str, Tool] = {}, mode: Mode = "low"):
    """
    This will call all the tool necessary and run agent loop for follow up tool calls.
    1. This end if max iterations is either reached or finish_reason is stop.
    2. As it loops we reach near response.
    3. If no tool call present will only respond.

    Why agent loop as we let say we want to tools again.
    Ex:
    I want to know where is read_file function and what is in it from README.md
    Task 1: First read README.md and get where is read_file function.
    Task 2: Again call read tool to read app\\tools\\read_tools.py file and get content/

    Note: This kind of agent is called reactive agent run until get answer.

    Parameters
    ----------
    query: str
        The query for llm.
    tools: dict[str, Tool]
        The external function which can call api or do some task available for llm.
    mode:
        This mode decide how many max loops can llm runs before reaching answer as
        we increase mode for low,medium and high we can adust as per complexity of task.

    Return
    ------
    Res
    """
    client = __get_llm()

    available_tools_schemas = []
    # Available tool schemas
    for _, tool_spec in tools.items():
        available_tools_schemas.append(tool_spec["schema"])

    # Create a agent loop where agent can loop until it find certain response and is correct
    # The initial finish reason is not solved as llm always send as finish_reason = "tool_calls" for tool call or finish_reason="stop"(if we achieve our goal).
    # Also initial follow up is first response itself form llm if tool call needed.
    finish_reason = "NOT SOLVED"
    max_iteration = Config.REACTIVE_AGENT_MODES[mode]
    iteration = 0
    messages = [
        {
            "role": "system",
            "content": (
                "You are an intelligent coding agent. "
                "Use the available tools whenever necessary to complete the task. "
                "You may call tools multiple times. "
                "Continue using tools until the task is completed."
            ),
        },
        {"role": "user", "content": query},
    ]

    while iteration < max_iteration:
        follow_up = client.chat.completions.create(
            model=Config.MODEL_NAME,
            messages=messages,
            tools=available_tools_schemas,
        )

        if not follow_up.choices or len(follow_up.choices) == 0:
            raise RuntimeError("no choices in tool call response response")

        finish_reason = follow_up.choices[0].finish_reason
        prev_follow_up = follow_up.choices[0].message

        if finish_reason == "stop" and not prev_follow_up.tool_calls:
            return prev_follow_up.content

        if prev_follow_up.tool_calls:
            tool_call_results = __invoke_tool_and_get_response(prev_follow_up, tools)
            messages = [*messages, prev_follow_up, *tool_call_results]
        else:
            messages = [*messages, prev_follow_up]

        iteration += 1

    return follow_up.choices[0].message.content
