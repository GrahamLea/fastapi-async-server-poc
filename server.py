# SPDX-License-Identifier: Unlicense

import asyncio
import os
import platform
import random
import tempfile
from asyncio import Queue
from pathlib import Path
from typing import Optional

import aiofiles as aiofiles
from fastapi import FastAPI
from starlette.requests import Request
from starlette.responses import PlainTextResponse, FileResponse

tmp_path = Path("/tmp" if platform.system() == "Darwin" else tempfile.gettempdir()) / "async-server-poc"
tmp_path.mkdir(exist_ok=True)

latest_file: Optional[Path] = None

app = FastAPI()


@app.get("/")
async def get_root():
    return "POST and GET on /file"


@app.get("/file")
async def get_file():
    global latest_file
    if not latest_file:
        return PlainTextResponse("No file uploaded yet", status_code=404)
    else:
        return FileResponse(latest_file)


def print_status(is_reader: bool, status: str):
    global last_status_print_was_reader
    if not last_status_print_was_reader == is_reader:
        print()
        if not is_reader:
            print("\t\t\t\t\t\t", end="")
    last_status_print_was_reader = is_reader
    print(status, end=" ")


async def write_chunks_to_file(q: Queue, file: Path):
    async with aiofiles.open(file, mode="wb") as file_out:
        while True:
            print_status(False, "-> get()")
            chunk = await q.get()
            print_status(False, "-> write()")
            try:
                await file_out.write(chunk)
            except Exception as e:
                print("Exception trying to write!")
                print(e)
            print_status(False, "-> task_done()")
            q.task_done()


last_status_print_was_reader = False


@app.post("/file", status_code=201)
async def save_file(request: Request):
    label = str(random.randint(10000, 99999))
    print_status(True, f"{label}: Starting")
    file = tmp_path / label
    q: "Queue[bytes]" = Queue(maxsize=3)
    writer = asyncio.create_task(write_chunks_to_file(q, file))

    print_status(True, "-> stream().next()")
    chunk: bytes
    async for chunk in request.stream():
        print_status(True, "-> put()")
        await q.put(chunk)
        print_status(True, "-> stream().next()")

    print("-> join()")
    await q.join()
    print("-> cancel()")
    writer.cancel()
    print(f"{label}: Done")

    global latest_file
    prev_file = latest_file
    latest_file = file
    if prev_file:
        os.remove(prev_file)
