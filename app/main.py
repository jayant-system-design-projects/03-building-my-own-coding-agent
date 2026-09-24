import argparse
import sys
from app.handlers.reactive_agent_handlers import _call_reactive_agent
from app.tools.read_tools import READ_TOOLS
from app.tools.write_tools import WRITE_TOOLS
from app.tools.bash_tools import BASH_TOOLS

ALL_TOOLS = {**READ_TOOLS, **WRITE_TOOLS, **BASH_TOOLS}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("-p", required=True)
    args = p.parse_args()

    try:
        response = _call_reactive_agent(args.p, ALL_TOOLS)
    except Exception as e:
        print(e.__str__())
        return

    # You can use print statements as follows for debugging, they'll be visible when running tests.
    print("Logs from your program will appear here!", file=sys.stderr)

    print(response)


if __name__ == "__main__":
    main()
