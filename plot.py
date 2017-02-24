#!/usr/bin/env python3
"""A tool to plot schedsi simulation statistics."""

import collections
import functools
import json
import math
import multiprocessing
import operator
import string
import sys
import tempfile

import matplotlib
import matplotlib.pyplot

from schedsi.log import binarylog

# TODO: parameterize
BINS_CLUSTER = 10


class ThreadFigures:
    """Management of pyplot figures for thread-timing statistics."""

    def __init__(self, num_plots):
        """Create a :class:`ThreadFigures`."""
        self.figures = {
            'wait': self._make_figure(num_plots),
            'run': self._make_figure(num_plots)
        }
        self.num_plots = num_plots
        self.plot_count = 0

    @staticmethod
    def _make_figure(num_plots):
        """Create a blank pyplot figure."""
        figure, *rest = matplotlib.pyplot.subplots(num_plots, figsize=(15, 20))
        figure.subplots_adjust(wspace=0, hspace=0.5)
        return (figure, *rest)

    def plot_thread(self, title, stats):
        """Add subplots for the thread's timings."""
        for key, fig in self.figures.items():
            times = stats[key]
            subplot = fig[1][self.plot_count]

            if not times:
                max_time = 0
            else:
                if isinstance(times[0], collections.abc.Sequence):
                    times = [sum(elem) for elem in times]
                max_time = max(times)
            bins = max(1, math.ceil(max_time / BINS_CLUSTER))
            subplot.hist(times, bins, range=(0, max_time))
            subplot.set_title(title)
            subplot.set_xlabel('time')
            subplot.set_ylabel('count')
            # add some spacing to the top
            ylim = list(subplot.axes.get_ylim())
            if ylim[1] == 1:
                ylim[1] += 0.1
            elif ylim[1] > 1:
                ylim[1] += math.log10(ylim[1])
            subplot.axes.set_ylim(ylim)
        self.plot_count += 1

    def save(self, prefix):
        """Save the figures to SVG files.

        The files created are named `prefix + figure_name + ".svg"`.
        """
        for (name, fig) in self.figures.items():
            fig = fig[0]
            fig.savefig(prefix + name + '.svg')
            fig.clf()


def plot_scheduler(name, stats):
    """Process scheduler stats."""
    figures = ThreadFigures(len(stats['children']) + 1)

    print('Plotting thread {}...'.format(name))
    figures.plot_thread(name, stats)

    for (key, values) in sorted(stats['children'].items()):
        print('Plotting thread {}...'.format(key))
        scheduler = values.get('scheduler', None)
        if scheduler is not None:
            key += ' (' + ', '.join(scheduler.keys()) + ')'
        figures.plot_thread(key, values)

    # strip the thread-id from the name
    figures.save(name[:name.rindex('-') + 1])

    print('Scheduler {} plotted.'.format(name))


def get_scheduler_keyslist(scheduler_threads):
    """Get a list of keys to all scheduler threads contained in `scheduler_threads`.

    The returned list can be iterated over like so::

        for keys in get_scheduler_keyslist(stats):
            scheduler_stats = reduce(getitem, keys, stats)
            #scheduler_stats now points to statistics of a scheduler
    """
    keyslist = []
    for (name, scheduler) in scheduler_threads.items():
        keyslist.append([name])
        for (child, child_thread) in scheduler['children'].items():
            scheduler = child_thread.get('scheduler', {})
            prefix = [name, 'children', child, 'scheduler']
            keyslist += (prefix + keys for keys in get_scheduler_keyslist(scheduler))
    return keyslist


def do_scheduler(stats, keys):
    """Call :func:`plot_scheduler` on the stats available through `keys`.

    :func:`get_scheduler_keyslist` can be used to obtain a list of valid `keys`.
    """
    plot_scheduler(keys[-1], functools.reduce(operator.getitem, keys, stats))


def get_text_stats(log):
    """Return thread stats from a text file."""
    thread_stats = log
    if log.readline() != '{\n':
        # not just plain JSON
        # hopefully a schedsi log
        thread_stats = tempfile.TemporaryFile('w+')

        for line in log:
            if line == 'Thread stats:\n':
                break
        for line in log:
            thread_stats.write(line)
            if line == '}\n':
                break

    thread_stats.seek(0)

    return json.load(thread_stats)


def get_binary_stats(log):
    """Return thread stats from a binary log."""
    return fix_keys(binarylog.get_thread_statistics(log))


def fix_keys(stats):
    """Fix tuple-keys from thread stats.

    Needed by :func:`get_binary_stats`.
    """
    if not isinstance(stats, dict):
        return stats

    new = {}
    for key, value in stats.items():
        # thread keys are (module-name, thread-id) tuples
        # convert to string
        if isinstance(key, tuple):
            key = '{}-{}'.format(key[0], key[1])
        new[key] = fix_keys(value)

    return new


def get_stats(filename):
    """Read thread stats from the file specified by `filename`."""
    with open(filename, 'rb') as log:
        # check if were dealing with a text log or a binary log
        testbuf = log.read(64)
        if not all((c in string.printable.encode('utf-8')) for c in testbuf):
            log.seek(0)
            return get_binary_stats(log)

    with open(filename) as log:
        return get_text_stats(log)


def main():
    """Plot the statistics in `sys.argv[1]`."""
    matplotlib.rcParams.update({'figure.max_open_warning': 0})

    if len(sys.argv) != 2:
        print('Usage: {0} stats.json or {0} schedsi.log'.format(sys.argv[0]), file=sys.stderr)
        sys.exit(1)

    stats = get_stats(sys.argv[1])

    keyslist = get_scheduler_keyslist(stats)
    with multiprocessing.Pool() as pool:
        pool.map(functools.partial(do_scheduler, stats), keyslist)


if __name__ == '__main__':
    main()
