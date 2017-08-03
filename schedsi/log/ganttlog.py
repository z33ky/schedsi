#!/usr/bin/env python3
"""Defines the :class:`GanttLog`.

There's some code duplication with :class:`GraphLog`.
"""

from schedsi import threads
import collections
import pyx


pyx_color = pyx.color


def outlined_fill(color, amount):
    """Create an outlined, filled pyx attribute.

    Outline is full color (1.0), fill is graded.
    """
    return [pyx.style.linewidth.Thick,
            pyx.deco.stroked([color.getcolor(1.0)]), pyx.deco.filled([color.getcolor(amount)])]


EXEC_COLORS = outlined_fill(pyx.color.gradient.WhiteBlue, 0.5)
TIMER_COLOR = [pyx.style.linewidth(0.1), pyx.deco.stroked([pyx.color.rgb(1.0, 0.1, 0.1)])]
YIELD_COLOR = [pyx.style.linewidth(0.3), pyx.deco.stroked([pyx.color.rgb(0.2, 0.7, 1.0)])]
FINISH_COLOR = [pyx.style.linewidth(0.3), pyx.deco.stroked([pyx.color.rgb(0.2, 1.0, 0.2)])]
TEXT_ATTR = [pyx.text.mathmode, pyx.text.halign.boxcenter, pyx.color.rgb.black]

# height of boxes in graph
BOX_HEIGHT = 2
# distance between boxes in graph
BOX_DISTANCE = BOX_HEIGHT / 5
# height lines on boxes (finish, yield)
BOX_LINE_SIZE = 1.5


class Indexer:
    """Assign consecutive numbers to things."""

    _list = []

    def __len__(self):
        """Return the number of things encountered."""
        return len(self._list)

    def index(self, thing):
        """Return index of a thing, adding it if it wasn't indexed."""
        try:
            return self._list.index(thing)
        except ValueError:
            self._list.append(thing)
            return len(self) - 1


class GanttLog:
    """Graphical logger, Gantt-style.

    Records events on a canvas, which can be converted to SVG.

    The logger has two canvases,
    representing a background (self.canvas) and foreground (self.top) layer.
    Since we draw event-based, sometimes something might be overwritten by a later event.
    To prevent this, a few things are drawn on the top layer.

    Drawing is stateful, so we keep the current drawing position in self.cursor.
    """

    def __init__(self, *, text_scale=1, exec_colors=None, name_module=True):
        """Create a :class:`GraphLog`."""
        pyx.text.set(cls=pyx.text.LatexRunner)
        pyx.text.preamble(r"\usepackage[helvet]{sfmath}")
        self.canvas = pyx.canvas.canvas()
        self.top = pyx.canvas.canvas()
        self.cursor = [0, 0]
        self.threads = Indexer()
        self.interrupts = []
        # TODO: the translation is not brilliant
        self.text_attr = TEXT_ATTR + [pyx.trafo.scale(text_scale),
                                      pyx.trafo.translate(0, -text_scale / 10)]
        if name_module:
            self._name_thread = self._name_thread_module
        else:
            self._name_thread = self._name_thread_only
        self.exec_colors = exec_colors or {}

    @staticmethod
    def _name_thread_only(thread):
        """Return a string identifying the thread."""
        return thread.tid

    @classmethod
    def _name_thread_module(cls, thread):
        """Return a string identifying the thread with module."""
        return thread.module.name + '|' + cls._name_thread_only(thread)

    def write(self, stream):
        """Generate SVG output of the current graph."""
        # since we draw additional things (like axes), let's do this on a temporary canvas
        canvas = pyx.canvas.canvas()
        canvas.insert(self.canvas)

        # insert the top layer
        canvas.insert(self.top)

        # draw interrupts
        total_height = len(self.threads) * (BOX_HEIGHT + BOX_DISTANCE) - BOX_DISTANCE
        for y in self.interrupts:
            line = pyx.path.line(y, 0, y, total_height)
            canvas.stroke(line, TIMER_COLOR)

        # draw axes
        path = pyx.path.path(pyx.path.moveto(0, 0), pyx.path.rlineto(self.cursor[0], 0))
        canvas.stroke(path, [pyx.style.linecap.square, pyx.style.linewidth.THICk,
                             pyx.color.rgb.black])
        for point in range(0, int(self.cursor[0] + 1), 5):
            line = pyx.path.line(point, 0, point, -0.5)
            canvas.stroke(line, [pyx.style.linewidth.THICk, pyx.color.rgb.black])
            canvas.text(point, -1.1, point, self.text_attr)

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

    def _draw_block(self, color, thread, length, height=BOX_HEIGHT, canvas=None):
        """Draw a solid block.

        Usually we want to draw a process, so `height` defaults to :const:`LEVEL`.
        If `canvas` is :obj:`None`, :attr:`self.canvas` is used.
        `text` is always drawn on the top layer.
        """
        if canvas is None:
            canvas = self.canvas
        if color is EXEC_COLORS:
            color = self.exec_colors.get(thread, color)

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
        cursor[1] += BOX_HEIGHT
        lineright = pyx.path.rlineto(dx, 0)
        lineup = pyx.path.rlineto(0, dy)
        if dy < 0:
            # create a downwards slope
            lineup, lineright = lineright, lineup

        path = pyx.path.path(pyx.path.moveto(*cursor), lineright, lineup, pyx.path.closepath())
        canvas.draw(path, color)
        self._move(dx, dy)

    def init_core(self, _cpu):
        """Register a :class:`Core`."""
        pass

    def context_switch(self, cpu, split_index, appendix, time):
        """Log an context switch event."""
        if appendix:
            new_thread = appendix.thread_at(-1)
        else:
            new_thread = cpu.status.chain.thread_at(split_index)

        if isinstance(new_thread, (threads.SchedulerThread, threads.VCPUThread)):
            return

        self.cursor[1] = self.threads.index(new_thread) * (BOX_HEIGHT + BOX_DISTANCE)

    def thread_execute(self, cpu, runtime):
        """Log an thread execution event."""
        self._draw_block(EXEC_COLORS, cpu.status.chain.top, runtime)
        self.task_executed = True

    def thread_yield(self, cpu):
        """Log an thread yielded event."""
        thread = cpu.status.chain.top
        if isinstance(thread, (threads.SchedulerThread, threads.VCPUThread)):
            return

        color = FINISH_COLOR if thread.is_finished() else YIELD_COLOR
        offset = (BOX_HEIGHT - BOX_LINE_SIZE) / 2
        self._move(0, offset)
        self._draw_line(color, 0, BOX_LINE_SIZE, self.top)
        self._move(0, -offset - BOX_LINE_SIZE)

    def cpu_idle(self, _cpu, idle_time):
        """Log an CPU idle event."""
        self._move(idle_time, 0)

    def timer_interrupt(self, cpu, idx, delay):
        """Log an timer interrupt event."""
        if cpu.status.chain.top.is_finished():
            self.thread_yield(cpu)
        self.interrupts.append(cpu.status.current_time - delay)

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
