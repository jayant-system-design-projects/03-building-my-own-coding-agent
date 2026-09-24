import argparse
import sys
from openai import OpenAI
from app.config import Config


def main():
    p = argparse.ArgumentParser()
    p.add_argument("-p", required=True)
    args = p.parse_args()

    if not Config.API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is not set")

    client = OpenAI(api_key=Config.API_KEY, base_url=Config.BASE_URL)

    chat = client.chat.completions.create(
        model=Config.MODEL_NAME,
        messages=[{"role": "user", "content": args.p}],
    )

    if not chat.choices or len(chat.choices) == 0:
        raise RuntimeError("no choices in response")

    # You can use print statements as follows for debugging, they'll be visible when running tests.
    print("Logs from your program will appear here!", file=sys.stderr)

    print(chat.choices[0].message.content)


if __name__ == "__main__":
    main()
