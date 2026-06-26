"""Spawn a `source | ffmpeg` pipeline as chained subprocesses and tear it down.

The thin hardware-touching layer (not unit-tested; exercised on-device). Stages
are separate processes joined by OS pipes so the source's stderr (nrsc5 metadata)
stays separate from ffmpeg's. Each runs in its own session; `stop()` terminates
them (SIGTERM, then SIGKILL after a grace period) so no rtl_fm/nrsc5 is orphaned.
"""

from __future__ import annotations

import asyncio
import os


class ProcessGroup:
    def __init__(self, procs: list[asyncio.subprocess.Process]):
        self._procs = procs
        self.stopped = False

    @property
    def stdout(self):
        """The final stage's stdout (ffmpeg MP3) — fed to the fan-out."""
        return self._procs[-1].stdout

    @property
    def source_stderr(self):
        """The source stage's stderr (nrsc5 metadata / rtl_fm info)."""
        return self._procs[0].stderr

    async def wait(self) -> int:
        """Return when any stage exits (a dead stage breaks the pipeline)."""
        tasks = [asyncio.ensure_future(p.wait()) for p in self._procs]
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        return next(iter(done)).result()

    async def stop(self) -> None:
        if self.stopped:
            return
        self.stopped = True
        for p in self._procs:
            if p.returncode is None:
                try:
                    p.terminate()
                except ProcessLookupError:
                    pass
        for p in self._procs:
            try:
                await asyncio.wait_for(p.wait(), timeout=3)
            except asyncio.TimeoutError:
                try:
                    p.kill()
                except ProcessLookupError:
                    pass
                await p.wait()


async def spawn_pipeline(pipeline: list[list[str]]) -> ProcessGroup:
    procs: list[asyncio.subprocess.Process] = []
    n = len(pipeline)
    prev_read: int | None = None
    for i, argv in enumerate(pipeline):
        if i < n - 1:
            read_fd, write_fd = os.pipe()
            stdout = write_fd
        else:
            stdout = asyncio.subprocess.PIPE
            read_fd = write_fd = None
        stderr = asyncio.subprocess.PIPE if i == 0 else asyncio.subprocess.DEVNULL
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=prev_read,
            stdout=stdout,
            stderr=stderr,
            start_new_session=True,
        )
        procs.append(proc)
        if prev_read is not None:
            os.close(prev_read)
        if i < n - 1:
            os.close(write_fd)
            prev_read = read_fd
    return ProcessGroup(procs)
