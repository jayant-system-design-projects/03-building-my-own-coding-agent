# Building My Own Coding Agent 🤖

A small Python coding agent that I am building while working through the [Build Your Own Claude Code](https://app.codecrafters.io/courses/claude-code) challenge from CodeCrafters.

Most people treat coding agents as magic. They are not. Underneath, a tool-calling agent is a message list, a dictionary of functions, and a loop, and the fastest way to prove that to yourself is to write one.

So this is a reactive agent written directly against the raw chat-completions API. No LangChain, no LlamaIndex, no agent framework of any kind — just an OpenAI-compatible client, a plain Python loop, and a handful of functions the model is allowed to ask for. Every part that makes it an agent is code in this repo.

The point of the project is the mechanism: how a model is told which tools exist, what it actually sends back when it wants one, who runs the code, and how feeding that result into the conversation turns a single prompt into an agent that keeps working until the task is finished.

Small note before the agent starts talking: this README is the only part AI wrote. The agent loop, the tool schemas, the tool registry, the dispatch logic, and the iteration control are all code I wrote myself. AI handled the typing cardio; I handled the agent workout. Fair deal.

## What It Does

Give it a task, and it will go and do the task:

- read any file on the machine
- write a file, creating it if it does not exist
- work out whether it is on Windows, Linux, or macOS
- run real shell commands through the right shell for that OS
- and, the part that makes it an *agent*, keep doing all of the above until the job is actually finished

That last point is the difference between a chatbot and an agent. A chatbot answers once. This thing reads a file, realises it needs another one, goes and gets it, and only then answers.

It is still a learning project, but nothing about the core flow is fake: prompt in, tools offered, tools called, results fed back, loop until solved.

## Quick Demo

The simple stuff works like you would expect:

```bash
$ python -m app.main -p "what OS am I on?"
Windows

$ python -m app.main -p "create a file hello.py that prints hello world"
File hello.py is create successfully and content is written in it.
```

But this is the one I actually care about:

```bash
$ python -m app.main -p "find where read_file is defined and explain what it returns"
```

Nothing about that task can be answered in one shot. The model does not know where the function lives, so here is what actually happens behind that single line:

```text
iteration 1   model: "I need to look around."     -> calls check_platform_system
              result: "Windows"

iteration 2   model: "Now I can search properly."  -> calls bash_tool
              result: app/tools/read_tools.py

iteration 3   model: "Let me read that."           -> calls read_file
              result: <the file contents>

iteration 4   model: finish_reason = "stop"
              "read_file opens the path, returns the contents, and returns a
               plain message instead of raising if the file is missing."
```

Four round trips. I wrote none of those steps. I did not write "first check the OS, then search, then read". I only wrote the loop that lets it keep going, and a dictionary of things it is allowed to ask for. The sequencing is the model's.

That is the moment this project stopped being homework and got interesting.

## The Loop

This is what "reactive agent" actually means, step by step:

1. send the model the task plus the **tool schemas** — just names, descriptions, and parameters
2. the model replies with `finish_reason: "tool_calls"` and names the tool it wants
3. my code looks that name up in the registry, parses the JSON arguments, and runs the real Python function
4. the result goes back into the message list as `{"role": "tool", ...}`
5. loop — the model now picks its next move knowing what it just learned
6. when it finally replies with `finish_reason: "stop"`, the task is done

Step 5 is the whole idea. The result does not get stashed in a variable somewhere, it goes back into the conversation. Every decision is a *reaction* to the previous result, which is exactly the difference between a chatbot and an agent.

In one picture:

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

Look at what crosses the boundary on the left: **schemas only**. The model gets descriptions of what exists. It never gets a single callable. When it wants something done it says *"I would like to call `read_file` with this path"*, and my code decides whether that name is in the registry and runs it.

That is the entire safety story of a tool-calling agent, and it is the part most explanations skip over.

## How It Works

### 1. Where it starts

`app/main.py`, and it is deliberately dull:

```python
ALL_TOOLS = {**READ_TOOLS, **WRITE_TOOLS, **BASH_TOOLS}
response = _call_reactive_agent(args.p, ALL_TOOLS)
```

Parse one `-p` argument, merge the tool groups, hand it all to the agent. Giving the agent a new power later means adding one more dictionary to that merge. Nothing else changes, which is the sort of thing you only appreciate after you have written the messy version first.

### 2. How the model finds out what it can do

Every tool here is the same two things wearing one name:

```python
READ_TOOLS = {
    "read_file": {
        "schema":   { ...what the model sees... },
        "function": __read_file,   # what actually runs
    },
}
```

The **schema** travels to the model. The **function** never leaves my process. When a tool call comes back, the name in that response is just a dictionary key, and looking it up is how a sentence from a language model turns into a Python function call.

The functions are name mangled (`__read_file`) so nothing outside the module can import them. The registry is the only door in, and I am the doorman.

### 3. Why the schemas are Pydantic and not raw JSON

I wrote them as plain dictionaries first. It was fine for one tool and awful by the third, because the format uses `type` as a key in three different nested places and every typo produced a model that behaved *slightly* wrong rather than crashing.

So they became Pydantic models in `app/schemas/base_tool_schema.py`, with safe Python names aliased back to the wire format:

```python
class Properties(BaseModel):
    property_type: str = Field(alias="type", default="object")
    description: str
```

and dumped with `by_alias=True` at the end.

Then there is the validator I added after losing an evening:

```python
@model_validator(mode="after")
def validate_required(self):
    missing = self.required - self.parameters.properties.keys()
    if missing:
        raise ValueError(f"Required properties not defined: {sorted(missing)}")
```

I had marked a parameter as required and never defined it. Nothing crashed. The agent just got quietly stupid for an hour. Now it refuses to start instead, which is the kind of loudness I have learned to appreciate.

### 4. The loop that makes it an agent

`app/handlers/reactive_agent_handlers.py`. Five lines of English:

1. send the messages and the tool schemas to the model
2. look at `finish_reason`
3. if it is `stop` and nothing was requested, we are done, return the answer
4. if tools were requested, run them, append the assistant message and every result to `messages`, go to 1
5. give up at `max_iteration` no matter what

Step 4 is the whole thing. The results do not go into a variable somewhere, they go back into the conversation. So the model's next decision is made knowing everything it has found so far. That is why it is called a *reactive* agent: every move is a reaction to what the last move turned up.

Before I wrote this I assumed there was something more sophisticated in here. There is not. It is a `while` loop and a growing list.

### 5. Who actually runs the code

Dispatch lives in its own function so the loop stays readable. For each requested tool: look up the name, `json.loads` the arguments, call the function, and hand the output back in the shape the API wants.

```python
{
    "role": "tool",
    "tool_call_id": tool_call.id,
    "content": json.dumps(tool_result, ensure_ascii=False),
}
```

That `tool_call_id` is not decoration. When the model asks for three tools at once, it is the only thing telling it which answer belongs to which question. Drop it and the model gets three results and no idea which is which.

And if the model asks for a tool that is not in my registry? Nothing happens. It gets skipped. The model can ask for `delete_everything` all day; it only ever receives what I registered.

### 6. The four tools

**`read_file`** resolves the path and returns the contents. If the file is missing it returns the sentence *"File x does not exist"* rather than raising, and that choice matters more than it looks. See below.

**`write_file`** writes, creating the file if needed, and reports back whether it worked.

**`check_platform_system`** returns `platform.system()` and takes no parameters at all, which is the tool that forced my schema code to accept an empty parameter list.

**`bash_tool`** runs a command through `cmd.exe` or `/bin/bash` and returns `stdout`, `stderr`, and `return_code` as three separate fields. It exists alongside `check_platform_system` for a reason: I want the model to *find out* which OS it is on before it starts guessing at command syntax, instead of confidently sending `ls` to `cmd.exe`.

Returning the return code separately sounds pedantic until you notice that "the command failed silently" and "the command worked and printed nothing" look identical if all you hand back is stdout.

### 7. Why there is a limit

`app/config.py` decides how many times the loop may run:

| mode       | max iterations |
| ---------- | -------------- |
| `low`    | 5              |
| `medium` | 5              |
| `high`   | 15             |

I watched a model call the same tool four times in a row once, getting the same result each time and being no closer to an answer. An agent loop with no cap is an infinite loop with a billing address. Simple tasks are happy in `low`; poking around a whole codebase is what `high` is for.

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

Python 3.14+.

```bash
uv sync
```

Put your model access in a `.env`:

```bash
OPENROUTER_API_KEY=your_key_here
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_MODEL_NAME=nvidia/nemotron-3-ultra-550b-a55b:free
MAX_ITERATIONS_LOW_MODE=5
MAX_ITERATIONS_MEDIUM_MODE=5
MAX_ITERATIONS_HIGH_MODE=15
```

Only the API key is actually required, the rest have defaults.

```bash
uv run python -m app.main -p "your task here"
```

Things worth trying, roughly in order of how much they show off:

```bash
uv run python -m app.main -p "what operating system am I on?"
uv run python -m app.main -p "read app/config.py and explain the settings"
uv run python -m app.main -p "create hello.py that prints hello world"
uv run python -m app.main -p "find where write_file is defined and summarise it"
```

One honest warning: this thing has a shell and a writer. It can genuinely change your machine. Point it at a folder you are willing to let it touch.

## What I Learned

**The model never runs anything.** It returns a name and some JSON. My code does the lookup, my code parses the arguments, my code makes the call. Seeing it written out is what turns "how do AI agents edit files?" into "somebody wrote an `open()` call and told the model it exists". Less magic than people expect, and far more controllable.

**Tool descriptions are part of the program.** The schema is not documentation the model skims, it is the only information it has when deciding whether a tool fits. A vague description does not throw an error. It produces an agent that quietly picks the wrong tool and gives you a confident wrong answer, which is a far worse failure than a crash.

**Errors should be returned, not raised.** My instinct was to let `FileNotFoundError` propagate, and it took a few dead loops to see why that is wrong. A raised exception ends the agent. A returned sentence goes into `messages`, the model reads *"that file does not exist"*, and tries a different path on the next iteration. Error handling in an agent is not about protecting the program. It is about keeping the conversation alive long enough for the model to recover.

**Frameworks sell convenience, not capability.** I went in assuming LangChain must be doing something I could not. It is a message list, a dictionary of functions, and a loop. Every abstraction on top of that is ergonomics. Worth using, absolutely, but worth building once first so you know what it is hiding.

It is a small project, but it made agents feel much less mysterious. Turns out the agent was just a loop all along, and honestly, that was the reaction I was hoping for. 🤖
