#!/usr/bin/env python3
"""Defines the :class:`ModuleGraphLog`."""

from . import graphlog


pyx_color = graphlog.pyx_color
outlined_fill = graphlog.outlined_fill


class ModuleGraphLog:
    """A :class:`GraphLog` with a limited view.

    Instead of drawing the whole hierarchy, a different :class:`Module` can be
    specified, representing the root of the sub-hierarchy that is to be logged.
    """

    def __init__(self, module, *, name_module=False, draw_parent_interrupts=False, **kwargs):
        """Create a :class:`ModuleGraphLog`.

        If `draw_parent_interrupts` is `True`, red lines in the graph will indicate
        interrupts from parent modules.
        If it is `False`, only interrupts originating from timers of `module` will
        have red lines drawn.
        """
        self.graphlog = graphlog.GraphLog(name_module=name_module, **kwargs)
        self.module = module
        self.active = False
        self.draw_parent_interrupts = draw_parent_interrupts

    def write(self, stream):
        """See :meth:`GraphLog.write`."""
        self.graphlog.write(stream)

    def _forward(self, function, cpu, *args):
        """Call `function` if :attr:`active`.

        Takes care of changing the context chain to hide other :class:`<Modules> Module`.
        """
        if self.active:
            chain = cpu.status.chain
            real = chain.contexts
            real_kernel = real[0].thread.module

            chain.contexts = [real[0]] + [ctx for ctx in real if ctx.thread.module is self.module]
            # fake kernel module
            chain.contexts[0].thread.module = self.module

            function(cpu, *args)

            # restore
            chain.contexts = real
            real[0].thread.module = real_kernel

    def init_core(self, cpu):
        """Register a :class:`Core`."""
        if any(ctx.thread.module is self.module for ctx in cpu.status.chain.contexts):
            self.active = True
            self._forward(self.graphlog.init_core, cpu)
            return

    def context_switch(self, cpu, split_index, appendix, time):
        """Log an context switch event."""
        real_contexts = None
        if appendix:
            real_contexts = appendix.contexts
            module_contexts = [ctx for ctx in appendix.contexts
                               if ctx.thread.module is self.module]
            if module_contexts:
                self.active = True
                appendix.contexts = module_contexts
        else:
            contexts = cpu.status.chain.contexts
            if any(ctx.thread.module is self.module for ctx in contexts[split_index + 1:]):
                assert self.active
                if contexts[split_index].thread.module is not self.module:
                    self.active = False
                    return

        self._forward(self.graphlog.context_switch, cpu, split_index, appendix, time)
        if real_contexts is not None:
            appendix.contexts = real_contexts

    def thread_execute(self, cpu, runtime):
        """Log an thread execution event."""
        self._forward(self.graphlog.thread_execute, cpu, runtime)

    def thread_yield(self, cpu):
        """Log an thread yielded event."""
        self._forward(self.graphlog.thread_yield, cpu)

    def cpu_idle(self, _cpu, _idle_time):
        """Log an CPU idle event."""
        # FIXME?
        pass

    def timer_interrupt(self, cpu, idx, delay):
        """Log an timer interrupt event."""
        if self.draw_parent_interrupts:
            if self.module not in (ctx.thread.module for ctx in cpu.status.chain.contexts[idx:]):
                return
        elif cpu.status.chain.contexts[idx].thread.module is not self.module:
            return
        self._forward(self.graphlog.timer_interrupt, cpu, idx, delay)

    def thread_statistics(self, stats):
        """Log thread statistics.

        A no-op for this logger.
        """
        pass

    def cpu_statistics(self, stats):
        """Log CPU statistics.

        A no-op for this logger.
        """
        pass
