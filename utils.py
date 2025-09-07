import sys
import datetime
from typing import NoReturn


def logError(message: str, exit_code: int) -> NoReturn:
    sys.stderr.write(
        f'{datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}: {message}\n'
    )
    sys.exit(exit_code)
