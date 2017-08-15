#!/usr/bin/env python3
"""Defines the :class:`GraphLog`."""

import pyx
import typing


pyx_color = pyx.color


def outlined_fill(color, amount):
    """Create an outlined, filled pyx attribute.

    Outline is full color (1.0), fill is graded.
    """
    return [pyx.style.linewidth.Thick,
            pyx.deco.stroked([color.getcolor(1.0)]), pyx.deco.filled([color.getcolor(amount)])]


CTXSW_COLORS = outlined_fill(pyx.color.gradient.WhiteRed, 0.5) + [pyx.style.linejoin.bevel]
CTXSW_ZERO_COLOR = [pyx.style.linewidth.THICk, pyx.deco.stroked([pyx.color.rgb.red])]
EXEC_COLORS = outlined_fill(pyx.color.gradient.WhiteBlue, 0.5)
IDLE_COLOR = [pyx.deco.stroked([pyx.color.gray(0.5)])]
INACTIVE_COLOR = outlined_fill(pyx.color.gradient.WhiteBlue, 0.3)
TIMER_COLOR = [pyx.style.linewidth.THICk, pyx.deco.stroked([pyx.color.rgb(1.0, 0.1, 0.1)])]
TEXT_ATTR = [pyx.text.mathmode, pyx.text.halign.boxcenter, pyx.color.rgb.black]

# height in graph for context switch
LEVEL = 3


class _Background:  # pylint: disable=too-few-public-methods
    """An active background task.

    Simply accumulates the time spent waiting while children are executing.
    """

    def __init__(self, thread, time):
        """Create a :class:`_Background`."""
        self.thread = thread
        self.time = time


class GraphLog:
    """Graphical logger.

    Records events on a canvas, which can be converted to SVG.

    The logger has two canvases,
    representing a background (self.canvas) and foreground (self.top) layer.
    Since we draw event-based, sometimes something might be overwritten by a later event.
    To prevent this, a few things are drawn on the top layer.

    Drawing is stateful, so we keep the current drawing position in self.cursor.

    Finally we have a list of active background tasks,
    so that we can draw a single contiguous block when the children finish.
    """

    def __init__(self, *, draw_scale: float = 1, text_scale: float = 1, time_scale: float = 1,
                 exec_colors=None, bg_colors=None, name_module: bool = True):
        """Create a :class:`GraphLog`."""
        pyx.text.set(cls=pyx.text.LatexRunner)
        pyx.text.preamble(r"\usepackage[helvet]{sfmath}")
        self.canvas = pyx.canvas.canvas()
        self.top = pyx.canvas.canvas()
        self.cursor = [0, 0]
        self.level = 0
        self.background_tasks = []
        self.task_executed = False

        text_scale /= draw_scale
        # TODO: the translation is not brilliant
        self.text_attr = TEXT_ATTR + [pyx.trafo.scale(text_scale),
                                      pyx.trafo.translate(0, -text_scale / 10)]
        self.scaled = [pyx.trafo.scale(draw_scale)]
        self.time_scale = time_scale
        if name_module:
            self._name_thread = self._name_thread_module
        else:
            self._name_thread = self._name_thread_only
        self.exec_colors = exec_colors or {}
        self.bg_colors = bg_colors or {}

    @staticmethod
    def _name_thread_only(thread):
        """Return a string identifying the thread."""
        return thread.tid

    @classmethod
    def _name_thread_module(cls, thread):
        """Return a string identifying the thread with module."""
        return thread.module.name + '|' + cls._name_thread_only(thread)

    def write(self, stream: typing.BinaryIO):
        """Generate SVG output of the current graph."""
        # since we draw additional things (like axes), let's do this on a temporary canvas
        temp = pyx.canvas.canvas()

        # draw the yet undrawn background tasks
        # TODO: we should leverage _draw_background_tasks
        for idx in reversed(range(0, len(self.background_tasks))):
            self._move(0, -LEVEL)
            self._draw_recent(idx, temp)
        self._move(0, LEVEL * len(self.background_tasks))

        # draw axes
        path = pyx.path.path(pyx.path.moveto(0, 0), pyx.path.rlineto(self.cursor[0], 0))
        temp.stroke(path, [pyx.style.linecap.square, pyx.style.linewidth.THICk,
                             pyx.color.rgb.black])
        for point in range(0, int(self.cursor[0] / self.time_scale + 1), 5):
            tick = point
            point *= self.time_scale
            line = pyx.path.line(point, 0, point, -0.5)
            temp.stroke(line, [pyx.style.linewidth.THICk, pyx.color.rgb.black])
            temp.text(point, -1.1, tick, self.text_attr)

        # add everything together
        canvas = pyx.canvas.canvas()
        canvas.insert(self.canvas, self.scaled)
        canvas.insert(temp, self.scaled)
        canvas.insert(self.top, self.scaled)

        # and done
        canvas.writeSVGfile(stream)

    def _move(self, dx, dy):
        """Move the cursor."""
        self.cursor[0] += dx
        self.cursor[1] += dy

    def _draw_line(self, color, dx, dy, canvas=None):
        """Draw a line.

        If `canvas` is :obj:`None`, :attr:`self.canvas` is used.
        """
        if canvas is None:
            canvas = self.canvas

        begin = self.cursor.copy()
        self._move(dx, dy)
        path = pyx.path.line(*begin, *self.cursor)
        canvas.stroke(path, color)

    def _draw_block(self, color, thread, length, height=LEVEL, canvas=None):
        """Draw a solid block.

        Usually we want to draw a process, so `height` defaults to :const:`LEVEL`.
        If `canvas` is :obj:`None`, :attr:`self.canvas` is used.
        `text` is always drawn on the top layer.
        """
        if canvas is None:
            canvas = self.canvas
        if color is EXEC_COLORS:
            color = self.exec_colors.get(thread, color)
        if color is INACTIVE_COLOR:
            color = self.bg_colors.get(thread, color)

        path = pyx.path.rect(*self.cursor, length, height)
        canvas.draw(path, color)

        # center the text
        textpos = self.cursor.copy()
        textpos[0] += length / 2
        if length >= 1:
            textpos[1] += height / 2
        else:
            # if the block is really small, put the text above and draw a line to it
            linepos = textpos.copy()
            linepos[1] += height
            textpos[1] = linepos[1] + 0.5
            self.top.stroke(pyx.path.line(*linepos, *textpos), color)
        self.top.text(*textpos, self._name_thread(thread), self.text_attr)

        self._move(length, 0)

    def _draw_slope(self, color, dx, dy, canvas=None):
        """Draw a trinangle.

        This represents a context switch.

        If `canvas` is :obj:`None`, :attr:`self.canvas` is used.
        """
        if dx == 0:
            #assert dy == 0
            self._draw_line(color, 0, dy, canvas)
            return

        if canvas is None:
            canvas = self.canvas

        cursor = self.cursor.copy()
        # the context switch is drawn on top of the current block
        cursor[1] += LEVEL
        lineright = pyx.path.rlineto(dx, 0)
        lineup = pyx.path.rlineto(0, dy)
        if dy < 0:
            # create a downwards slope
            lineup, lineright = lineright, lineup

        path = pyx.path.path(pyx.path.moveto(*cursor), lineright, lineup, pyx.path.closepath())
        canvas.draw(path, color)
        self._move(dx, dy)

    def _update_background_tasks(self, time):
        """Update the time of active background tasks."""
        for task in self.background_tasks:
            task.time += time

    def _draw_recent(self, idx=None, canvas=None):
        """Draw the most recent background task.

        If `idx` is :obj:`None`, the background task is popped from the stack.
        Otherwise `idx` is used for indexing and the stack is not modified.
        `canvas` is passed along to the drawing functions.
        """
        if idx is not None:
            task = self.background_tasks[idx]
        else:
            task = self.background_tasks.pop()
        self._move(-task.time, 0)
        self._draw_block(INACTIVE_COLOR, task.thread, task.time, canvas=canvas)

    def _draw_background_tasks(self, time, amount=None):
        """Draw all active background tasks."""
        if not self.background_tasks:
            return

        if amount is None:
            amount = len(self.background_tasks)

        # background tasks are not active during the switch,
        # so we move back for that amount of time
        self._move(-time, 0)
        for _ in range(0, amount):
            self._move(0, -LEVEL)
            self._draw_recent()
        # kernel was active during the switch, so it has the switch time added
        self._move(time, -LEVEL)
        self._draw_recent()

    def _ctx_down(self, threads, time, level_step):
        """Step down a level."""
        assert self.level % LEVEL == 0
        # we can't be at the bottom and step down
        assert self.level > 0 or level_step == 0

        if not self.task_executed and time != 0:
            self._draw_block(EXEC_COLORS, threads[0], 0)
            self.task_executed = True

        self._draw_slope(CTXSW_COLORS, time, -level_step)

        if level_step > LEVEL:
            # kernel is active during the switch
            self.background_tasks[0].time += time
            # move back up to the level we just were to draw the tasks processes
            self._move(0, level_step)
            self._draw_background_tasks(time, int(level_step / LEVEL) - 1)
        else:
            self._update_background_tasks(time)
            if level_step > 0:
                self._draw_recent()
        return -level_step

    def _ctx_up(self, threads, time, level_step):
        """Step up a level."""
        assert self.level % LEVEL == 0

        self.task_executed = False

        self._draw_slope(CTXSW_COLORS, time, level_step)

        self._update_background_tasks(time)
        if level_step > 0:
            assert len(threads) > 0
            self.background_tasks.extend(_Background(thread, 0) for thread in threads)
            # the thread on the bottom records context switching as background execution
            self.background_tasks[-len(threads)].time = time

        return level_step

    def _ctx_zero(self, thread):
        """Context switch with zero time."""
        self._move(0, LEVEL - 0.5)
        self._draw_line(CTXSW_ZERO_COLOR, 0, 1, self.top)
        self.top.text(*self.cursor, self._name_thread(thread), self.text_attr)
        self._move(0, -LEVEL - 0.5)

    def init_core(self, _cpu):
        """Register a :class:`Core`."""
        pass

    def context_switch(self, cpu, split_index, appendix, time):
        """Log an context switch event."""
        thread_diff = None
        time *= self.time_scale

        if appendix:
            ctx_func = self._ctx_up
            thread_diff = (ctx.thread for ctx in appendix.contexts)
        else:
            ctx_func = self._ctx_down
            # reversed because we go from the top to the bottom
            thread_diff = (ctx.thread for ctx in reversed(cpu.status.chain.contexts[split_index:]))

        # calculate depth of the hierarchy that is appended/removed
        current = cpu.status.chain.top
        levels = 0
        # threads at module-border
        border_threads = []
        for thread in thread_diff:
            if thread.module is not current.module:
                levels += LEVEL
                border_threads.append(current)
            current = thread

        if time == 0 and levels > 0:
            self._ctx_zero(border_threads[0])

        self.level += ctx_func(border_threads, time, levels)

    def thread_execute(self, cpu, runtime):
        """Log an thread execution event."""
        runtime *= self.time_scale
        self._update_background_tasks(runtime)
        self._draw_block(EXEC_COLORS, cpu.status.chain.top, runtime)
        self.task_executed = True

    def thread_yield(self, _cpu):
        """Log an thread yielded event."""
        pass

    def cpu_idle(self, _cpu, idle_time):
        """Log an CPU idle event."""
        self._draw_line(IDLE_COLOR, idle_time * self.time_scale, 0)

    def timer_interrupt(self, cpu, idx, delay):
        """Log an timer interrupt event."""
        delay *= self.time_scale
        # calculate depth of the module at idx from the top
        current = cpu.status.chain.top
        thread_diff = (ctx.thread for ctx in reversed(cpu.status.chain.contexts[idx:]))
        idx = 0
        for thread in thread_diff:
            if thread.module is not current.module:
                idx += 1
                current = thread
        timer_level_offset = idx * LEVEL

        self._move(-delay, -timer_level_offset - 0.5)
        self._draw_line(TIMER_COLOR, 0, 1.5, self.top)
        self._move(delay, timer_level_offset - 1)

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
