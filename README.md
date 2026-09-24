# Building My Own Coding Agent 🤖

A small Python coding agent that I am building while working through the [Build Your Own Claude Code](https://codecrafters.io) challenge from CodeCrafters.

The goal is to understand what actually happens inside tools like Claude Code or Cursor: how a model is handed a set of tools, how it decides to call one, who actually runs the code, and how a single prompt turns into a loop that keeps working until the task is finished.

No LangChain. No LlamaIndex. No agent framework. Just an OpenAI-compatible client, a plain Python loop, and a handful of functions the model is allowed to call. I wanted to find out how much of an agent is real engineering and how much of it is a `while` loop wearing a suit.

Small note before the agent starts talking: this README is the only part AI wrote. The agent loop, the tool schemas, the tool registry, the dispatch logic, and the iteration control are all code I wrote myself. AI handled the typing cardio; I handled the agent workout. Fair deal.

## What It Does

Right now, this agent can:

- take a task from the command line with `-p "your task"`
- send that task to an LLM together with the list of tools it is allowed to use
- read the model's tool calls, run the real Python functions behind them, and feed the results back
- keep looping until the model says it is done, instead of answering after one shot
- read a file from any path
- write a file, creating it if it does not exist
- detect whether it is running on Windows, Linux, or macOS
- run real shell commands through the correct shell for that OS
- chain all of the above, so "find where `read_file` is defined and tell me what it does" becomes several tool calls in a row without me scripting them
- cap how long it is allowed to think with `low`, `medium`, and `high` modes

It is still a learning project, but the core flow is real: prompt in, tools offered, tools called, results fed back, loop until solved.

## Quick Demo

```bash
$ python -m app.main -p "what OS am I on?"
Windows

$ python -m app.main -p "read README.md and tell me what this project does"
This project is a small coding agent built in Python...

$ python -m app.main -p "create a file test.py that prints hello"
File test.py is create successfully and content is written in it.

$ python -m app.main -p "find where read_file is defined and explain what it returns"
# agent calls bash_tool to search, then read_file on app/tools/read_tools.py,
# then answers from what it actually read

$ python -m app.main -p "list every python file under app/ and count them"
# agent calls check_platform_system first, then bash_tool with the right command
```

The second to last one is the interesting one. I never told it to search *then* read. It decided that on its own, because one tool call was not enough to answer.

## The Loop

This is the whole idea in one picture. Everything else in the repo exists to serve this loop.

```text
                    python -m app.main -p "task"
                                 |
                                 v
                 +-------------------------------+
                 |  ALL_TOOLS registry           |
                 |  READ + WRITE + BASH merged   |
                 |  name -> { schema, function } |
                 +---------------+---------------+
                                 |  schemas only
                                 v
            messages = [ system prompt , user task ]
                                 |
                                 v
        +--------------------------------------------+
        |                AGENT LOOP                  |
        |       while iteration < max_iteration      |
        +--------------------------------------------+
                                 |
                                 v
                    +------------------------+
                    |   LLM chat.completions |
                    |   (messages + tools)   |
                    +------------+-----------+
                                 |
                          finish_reason ?
                                 |
              +------------------+------------------+
              |                                     |
       "tool_calls"                               "stop"
              |                                     |
              v                                     v
   +---------------------+                 final answer returned
   | for each tool_call: |                 loop exits
   |  look up the name   |
   |  json.loads(args)   |
   |  call real function |
   +----------+----------+
              |
              v
   append to messages:
     the assistant message (the tool calls)
     one {"role": "tool", "tool_call_id", "content"} per call
              |
              +-------------> back to the LLM, one iteration older
```

The model never touches my filesystem. It only ever says *"I would like to call `read_file` with this path"*. My code decides whether that name exists in the registry, and my code runs it. That separation is the entire safety story of a tool-calling agent, and it is also the part I misunderstood before building this.

## How It Works

### 1. Entry Point

Everything starts in `app/main.py`.

It parses a single `-p` argument, merges the three tool groups into one `ALL_TOOLS` dictionary, and hands both the task and the tools to the agent handler. That is it. `main.py` stays boring on purpose, because the interesting part is one layer down.

```python
ALL_TOOLS = {**READ_TOOLS, **WRITE_TOOLS, **BASH_TOOLS}
response = _call_reactive_agent(args.p, ALL_TOOLS)
```

Adding a new capability to the agent means adding one more dictionary to that merge. Nothing else changes.

### 2. The Tool Registry

Every tool in this project has the same shape: a name mapped to a schema and a real Python function.

```python
READ_TOOLS = {
    "read_file": {
        "schema":   { ...JSON schema the model sees... },
        "function": __read_file,   # the actual Python callable
    },
}
```

This shape is the whole trick. The **schema** is the only thing that goes to the model, and it is just the description, the parameter names, and the types. The **function** never leaves my process. When a tool call comes back, the name in the response is used as a key into this same dictionary to find the callable.

The functions themselves are name mangled (`__read_file`), so they are not importable from outside their module. The registry is the only door in.

### 3. Tool Schemas Are Typed, Not Hand Written JSON

Tool schemas live in `app/schemas/base_tool_schema.py` and are built with Pydantic instead of being written out as raw dictionaries.

The reason is that the provider format uses `type` as a key in three different places, which is awkward to declare directly on a model. So the fields get safe Python names and are aliased back:

```python
class Properties(BaseModel):
    property_type: str = Field(alias="type", default="object")
    description: str
```

and then dumped with `by_alias=True` so the wire format comes out exactly as the API expects.

There is also a validator that I added after being burned once:

```python
@model_validator(mode="after")
def validate_required(self):
    missing = self.required - self.parameters.properties.keys()
    if missing:
        raise ValueError(f"Required properties not defined: {sorted(missing)}")
```

If I mark a parameter as required but forget to actually define it, this fails immediately with a clear message instead of failing later as a confusing model response. Schema bugs are silent bugs, and silent bugs are the expensive kind.

### 4. The Reactive Agent Loop

This lives in `app/handlers/reactive_agent_handlers.py`, and it is the heart of the project.

The loop is:

1. send `messages` plus the tool schemas to the model
2. read `finish_reason`
3. if it is `stop` and there are no tool calls, the task is solved, so return the content
4. if there are tool calls, run them, append the assistant message and every tool result to `messages`, and loop again
5. stop unconditionally once `max_iteration` is reached

Point 4 is why this is a **reactive** agent rather than a one shot function caller. Each result goes back into the conversation, so the model's next decision is made with everything it has learned so far.

The example that made it click for me:

> *"I want to know where the `read_file` function is and what is in it, starting from README.md."*

- **Iteration 1** - the model cannot answer yet, so it calls `read_file` on `README.md`
- **Iteration 2** - now it knows the path, so it calls `read_file` again on `app/tools/read_tools.py`
- **Iteration 3** - it finally has enough context, returns `finish_reason: "stop"`, and answers

Nobody scripted those three steps. The loop just kept asking, and the model kept getting closer.

### 5. Tool Dispatch

Dispatch is a separate function on purpose, so the loop itself stays readable.

For each tool call in the model's response it looks up the name in the registry, parses the arguments JSON, calls the function, and wraps the output in the message shape the API requires:

```python
{
    "role": "tool",
    "tool_call_id": tool_call.id,
    "content": json.dumps(tool_result, ensure_ascii=False),
}
```

The `tool_call_id` is not optional decoration. When a model requests three tools in one turn, that ID is the only thing telling the model which result belongs to which request.

A name that is not in the registry is simply skipped. The model can ask for anything it likes; it only gets what I registered.

### 6. The Tools

**`read_file`** (`app/tools/read_tools.py`) resolves the path with `os.path.abspath` and returns the file contents. A missing file or a permission error comes back as a plain sentence rather than an exception, because a crash ends the agent while a sentence lets the model try something else.

**`write_file`** (`app/tools/write_tools.py`) opens the path with `Path(...).open("w")`, creating the file if needed, and reports back whether it worked.

**`check_platform_system`** (`app/tools/bash_tools.py`) returns `platform.system()`. It is a tool that takes no parameters at all, which is why an empty `Parameters()` with `required=[]` had to be legal in the schema.

**`bash_tool`** (`app/tools/bash_tools.py`) runs a shell command and returns `stdout`, `stderr`, and `return_code` as three separate fields. It picks `cmd.exe` on Windows and `/bin/bash` elsewhere, which is exactly why `check_platform_system` exists: the model should find out which OS it is on *before* it guesses at command syntax.

Returning the return code separately matters more than it looks. A command that failed silently and a command that succeeded with no output are identical if all you hand back is stdout.

### 7. Modes and the Iteration Cap

Modes are defined in `app/config.py` and decide how many times the loop may run:

| mode | max iterations |
|---|---|
| `low` | 5 |
| `medium` | 5 |
| `high` | 15 |

An agent loop without a cap is an infinite loop with a billing address. If a model gets stuck calling the same tool over and over, the cap is the thing that stops it. Simple tasks run fine in `low`; multi file exploration is what `high` is for.

## Project Structure

```text
app/
  main.py                          # CLI entry, merges tools, calls the agent
  config.py                        # Env backed settings, model, and iteration caps
  handlers/
    reactive_agent_handlers.py     # The agent loop and tool dispatch
  schemas/
    base_tool_schema.py            # Pydantic tool schema with alias and validation
  tools/
    read_tools.py                  # read_file
    write_tools.py                 # write_file
    bash_tools.py                  # check_platform_system, bash_tool
pyproject.toml                     # Project metadata
```

## Run Locally

This project uses Python 3.14+.

Install dependencies:

```bash
uv sync
```

Set up model access in a `.env` file:

```bash
OPENROUTER_API_KEY=your_key_here
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_MODEL_NAME=nvidia/nemotron-3-ultra-550b-a55b:free
MAX_ITERATIONS_LOW_MODE=5
MAX_ITERATIONS_MEDIUM_MODE=5
MAX_ITERATIONS_HIGH_MODE=15
```

Only `OPENROUTER_API_KEY` is actually required; everything else has a default.

Run the agent:

```bash
python -m app.main -p "your task here"
```

Tasks to try:

```bash
python -m app.main -p "what operating system am I on?"
python -m app.main -p "read app/config.py and explain the settings"
python -m app.main -p "create hello.py that prints hello world"
python -m app.main -p "list all python files under app/"
python -m app.main -p "find where write_file is defined and summarise it"
```

One warning worth repeating: the agent has a `bash_tool` and a `write_file` tool, so it can genuinely change your machine. Point it at a directory you are willing to let it touch.

## What I Learned

The biggest realisation was how little magic there is. An agent is a `while` loop, a list of messages, and a dictionary of functions. Everything a framework adds on top of that is convenience, not capability, which is exactly why building it without a framework taught me more than using one would have.

The model never executes anything. It only ever returns a name and some JSON arguments. My code does the lookup, my code parses the arguments, my code calls the function. Once that landed, "how do AI agents edit files?" stopped being mysterious and became "somebody wrote an `open()` call and told the model it exists".

Tool descriptions turned out to be part of the program. The schema is not documentation the model skims past, it is the only thing the model has when deciding whether a tool fits the task. A vague description does not throw an error, it just produces an agent that quietly picks the wrong tool. That is a much worse failure than a crash.

Errors should be returned, not raised. My first instinct was to let `FileNotFoundError` propagate. But a raised exception ends the loop, while a returned sentence like *"File x does not exist"* goes into `messages` and lets the model recover on the next iteration. Error handling in an agent is not about protecting the program, it is about keeping the conversation alive.

And the iteration cap is not a nice to have. The first time I watched a model call the same tool again and again, converging on nothing, I understood why every real agent ships with a budget.

It is a small project, but it made agents feel much less mysterious. Turns out the agent was just a loop all along, and honestly, that was the reaction I was hoping for. 🤖
