import subprocess
import platform
from app.schemas.base_tool_schema import ToolBase, Function, Parameters, Properties


def __check_platform_system() -> str:
    """
    This will return system of platform be windows,linux or macos.

    Parameters
    ----------
    None

    Returns
    -------
    platform: str
        The system/OS name, e.g. 'Linux', 'Windows' or 'Java'.
    """
    return platform.system()


def __bash_command_executor(command: str, system: str) -> str:
    """
    This will write content in file if exist else create one and write.

    Parameters
    ----------
    file_path: str
        This is file path for file to access and get content.
    system: str
        The system/OS name, e.g. 'Linux', 'Windows' or 'Java'.

    Returns
    -------
    str:
        Return message as if file created or else not created.

    Raises
    ------
    FileNotFoundError:
        If the file is not found on system.
    PermissionError:
        If we do no have permission to open file.
    """
    if system == "Windows":
        shell = "cmd.exe"
    else:
        shell = "/bin/bash"

    result = subprocess.run(
        command,
        shell=True,
        executable=shell if system != "Windows" else None,
        capture_output=True,
        text=True,
    )

    return {
        "result": result.stdout,
        "error": result.stderr,
        "return_code": result.returncode,
    }


BASH_TOOLS = {
    "check_platform_system": {
        "schema": ToolBase(
            function=Function(
                name="check_platform_system",
                description="This tool let you know os is windows,linux or mac to run bash commands.",
                parameters=Parameters(),
                required=[],
            )
        ).model_dump(mode="python", by_alias=True),
        "function": __check_platform_system,
    },
    "bash_tool": {
        "schema": ToolBase(
            function=Function(
                name="bash_tool",
                description="Execute a shell command",
                parameters=Parameters(
                    properties={
                        "command": Properties(
                            type="string",
                            description="The command to execute",
                        ),
                        "system": Properties(
                            type="string",
                            description="The system/OS name, e.g. 'Linux', 'Windows' or 'Java'.",
                        ),
                    }
                ),
                required=["command", "system"],
            )
        ).model_dump(mode="python", by_alias=True),
        "function": __bash_command_executor,
    },
}
