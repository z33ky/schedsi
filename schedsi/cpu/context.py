#!/usr/bin/env python3
"""Defines a :class:`Context` and :class:`Chain` thereof."""


class Context:
    """An operation context for a CPU Core.

    The context has
        * the current :class:`Thread`
        * the execution coroutine of the :class:`Thread`
        * timeout of the local timer
    """

    def __init__(self, thread):
        """Create a :class:`Context`."""
        self.thread = thread
        self.execution = thread.execute()
        self.started = False
        self.timeout = None
        self.buffer = None

    def execute(self, current_time):
        """Run the execution coroutine.

        `current_time` is sent to the coroutine,
        unless a different reply is injected (see :meth:`reply`).
        """
        if self.buffer is not None:
            value = self.execution.send(self.buffer)
            self.buffer = None
            return value
        elif self.started:
            return self.execution.send(current_time)
        else:
            self.started = True
            return next(self.execution)

    def reply(self, arg):
        """Send `arg` to the execution coroutine.

        Normally, the `current_time` as passed to :meth:`execute` is sent.
        This method can be used to inject a different argument.
        """
        assert self.started, 'Can\'t reply to a just-started context.'
        assert self.buffer is None or arg is None, 'Cannot overwrite reply.'
        assert arg is None or isinstance(arg, Chain)
        self.buffer = arg

    def restart(self, current_time):
        """Restart the thread.

        Calls :meth:`Thread.finish()` and then starts a new coroutine.
        """
        assert self.buffer is None
        assert self.started
        self.thread.finish(current_time)
        self.execution = self.thread.execute()
        self.started = False


class Chain:
    """The contexts for a scheduling-chain.

    The context chain represents the stack of contexts for a scheduling-chain.
    It may be a partial chain, i.e. the bottom is not the kernel.
    """

    def __init__(self, *, chain, next_timeout_idx=None):
        """Create a :class:`Chain`."""
        self.contexts = chain
        if next_timeout_idx is not None:
            self.next_timeout_idx = next_timeout_idx
        else:
            self._update_timeout()

    @classmethod
    def from_context(cls, start):
        """Create a :class:`Chain` with a single context."""
        return cls(chain=[start], next_timeout_idx=0)

    @classmethod
    def from_thread(cls, start):
        """Create a :class:`Chain` with a new context for `start`."""
        return cls.from_context(Context(start))

    def __len__(self):
        """Return the length of the :class:`Chain`."""
        return len(self.contexts)

    @property
    def current_context(self):
        """The current (top) context."""
        return self.contexts[-1] if self.contexts else None

    @property
    def bottom(self):
        """The bottom thread."""
        return self.thread_at(0)

    @property
    def top(self):
        """The top thread."""
        return self.thread_at(-1)

    @property
    def parent(self):
        """The parent thread."""
        return self.thread_at(-2) if len(self) > 1 else None

    @property
    def next_timeout(self):
        """The next timeout."""
        if self.next_timeout_idx is None:
            return None
        return self.contexts[self.next_timeout_idx].timeout

    def thread_at(self, idx):
        """Return the thread at index `idx` in the chain.

        Negative values are treated as an offset from the back.
        """
        return self.contexts[idx].thread

    def _update_timeout(self):
        """Find the lowest timeout in the chain and set :attr:`next_timeout`.

        This traverses the whole chain.
        """
        valid_timeouts = ((ctx.timeout, i) for i, ctx in enumerate(self.contexts)
                          if ctx.timeout is not None)
        self.next_timeout_idx = min(valid_timeouts, default=[None, None],
                                    key=lambda pair: pair[0])[1]

    def append_chain(self, tail):
        """Append a :class:`Chain`."""
        # update self.next_timeout
        tail_next_timeout = tail.next_timeout
        next_timeout = self.next_timeout
        if tail_next_timeout is not None \
           and (next_timeout is None or tail_next_timeout < next_timeout):
            self.next_timeout_idx = tail.next_timeout_idx + len(self)

        self.contexts += tail.contexts

    def set_timer(self, timeout, idx=-1):
        """Set the timeout of a context in the chain.

        If `idx` is not specified the current (top) context is used.
        """
        if idx < 0:
            idx += len(self.contexts)
        assert idx >= 0

        prev_timeout = self.next_timeout
        self.contexts[idx].timeout = timeout

        # update self.next_timeout
        # check if we can avoid calling _update_timeout()
        if self.next_timeout_idx is None:
            self.next_timeout_idx = idx
        else:
            if timeout is not None and (
                    prev_timeout is None or
                    idx != self.next_timeout_idx or prev_timeout >= timeout):
                if prev_timeout is None or prev_timeout > timeout or \
                    (prev_timeout == timeout and idx < self.next_timeout_idx):
                    self.next_timeout_idx = idx
            elif self.next_timeout_idx == idx:
                self._update_timeout()

    def elapse(self, time):
        """Elapse all timers in the chain.

        Must not be called if a timeout in the chain has elapsed.
        """
        if self.next_timeout_idx is None:
            # no time to count down then
            return
        assert self.contexts

        elapsed = self.next_timeout <= 0

        # elapse contexts up to next_timeout_idx
        for ctx in self.contexts[:self.next_timeout_idx + 1]:
            if ctx.timeout is not None:
                assert ctx.timeout > 0 or self.contexts.index(ctx) == self.next_timeout_idx
                ctx.timeout -= time

        # don't elapse contexts further than the next_timeout
        if elapsed:
            return

        # elapse the rest
        for ctx in self.contexts[self.next_timeout_idx + 1:]:
            if ctx.timeout is not None:
                assert ctx.timeout > 0
                ctx.timeout -= time

    def find_elapsed_timer(self):
        """Return the index of the first elapsed timer in the :class:`Chain`."""
        assert self.next_timeout <= 0
        return self.next_timeout_idx

    def split(self, idx):
        """Split the :class:`Chain` in two at `idx`.

        The instance keeps the chain up to and excluding `idx`.

        Returns the tail :class:`Chain`.
        """
        if idx < 0:
            idx = len(self) + idx
        assert idx > 0, 'Index for split is out of bounds.'

        tail_timeout_idx = None
        if self.next_timeout_idx is not None and idx <= self.next_timeout_idx:
            tail_timeout_idx = self.next_timeout_idx - idx

        tail = Chain(chain=self.contexts[idx:], next_timeout_idx=tail_timeout_idx)
        del self.contexts[idx:]

        if tail_timeout_idx is not None:
            self._update_timeout()

        return tail

    def finish(self, current_time):
        """Call :meth:`Thread.finish <schedsi.threads.Thread.finish>` \
        on every :class:`~schedsi.threads.Thread` in the :class:`Chain`.
        """
        for ctx in self.contexts:
            ctx.thread.finish(current_time)

    def run_background(self, current_time, time):
        """Call :meth:`Thread.run_background <schedsi.threads.Thread.run_background>` \
        on every :class:`~schedsi.threads.Thread` in the :class:`Chain` \
        except :attr:`current_context`.
        """
        for ctx in self.contexts[:-1]:
            ctx.thread.run_background(current_time, time)
