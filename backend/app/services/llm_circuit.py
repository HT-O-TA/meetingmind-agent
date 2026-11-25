"""Event-loop-local circuit breaker for model provider calls."""
import asyncio
import time

from openai import APIConnectionError, APIStatusError


class LLMCircuitOpen(RuntimeError):
    pass


class LLMCircuitBreaker:
    def __init__(self, threshold=3, cooldown=30, clock=time.monotonic):
        self.threshold = threshold
        self.cooldown = cooldown
        self.clock = clock
        self.state = "closed"
        self.failures = 0
        self.open_until = 0.0
        self.generation = 0

    def _open(self):
        self.state = "open"
        self.open_until = self.clock() + self.cooldown
        self.generation += 1

    async def call(self, operation, **kwargs):
        if self.state == "half-open" or (self.state == "open" and self.clock() < self.open_until):
            raise LLMCircuitOpen("Model provider circuit is open")
        if self.state == "open":
            self.state = "half-open"
        probe = self.state == "half-open"
        generation = self.generation
        try:
            result = await operation(**kwargs)
        except asyncio.CancelledError:
            if probe:
                self._open()
            raise
        except Exception as error:
            transient = isinstance(error, APIConnectionError) or (
                isinstance(error, APIStatusError) and error.status_code >= 500
            )
            if generation == self.generation:
                if transient:
                    self.failures += 1
                elif not probe:
                    self.failures = 0
                if probe or self.failures >= self.threshold:
                    self._open()
            raise
        if generation == self.generation:
            self.state = "closed"
            self.failures = 0
        return result
