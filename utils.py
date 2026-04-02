import sys
import datetime


def logError(message: str):
    sys.stderr.write(
        f'{datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}: {message}\n'
    )


def log(message: str):
    sys.stdout.write(
        f'{datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}: {message}\n'
    )
