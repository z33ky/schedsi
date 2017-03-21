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
TIME_RANGE_CLAMPING = 10
COUNT_RANGE_CLAMPING = 10

DO_PLOT = True


class ThreadFigures:
    """Management of pyplot figures for thread-timing statistics."""

    def __init__(self, num_plots):
        """Create a :class:`ThreadFigures`."""
        if DO_PLOT:
            wait_figs = self._make_figure(num_plots)
            run_figs = self._make_figure(num_plots)
        else:
            wait_figs = run_figs = self._make_figure(1)
        self.figures = {
            'wait': wait_figs,
            'run': run_figs,
        }
        self.num_plots = num_plots if DO_PLOT else 1
        self.plot_count = 0

    @staticmethod
    def _make_figure(num_plots):
        """Create a blank pyplot figure."""
        figure, *rest = matplotlib.pyplot.subplots(num_plots, figsize=(15, 20))
        figure.subplots_adjust(wspace=0, hspace=0.5)
        return (figure, *rest)

    def plot_thread(self, title, stats, conf):
        """Add subplots for the thread's timings."""
        for key, fig in self.figures.items():
            subplot = fig[1]
            if self.num_plots > 1:
                subplot = subplot[self.plot_count]
            times = stats[key]

            if not times:
                max_time = 0
                max_range = 0
            else:
                if isinstance(times[0], collections.abc.Sequence):
                    times = [sum(elem) for elem in times]
                max_time = max(times)
                max_range = max_time
                if max_range != 0:
                    clamp_range = max_range + (max_range / TIME_RANGE_CLAMPING)
                    max_range = round(max_range,
                                      -math.floor(math.log(clamp_range, TIME_RANGE_CLAMPING)))
            bins = max(1, math.ceil(max_time / BINS_CLUSTER))
            plot_range = (0, max_range)
            conf_params = conf.get(key, None)
            if conf_params is not None:
                bins = conf_params['bins'] or bins
                plot_range = conf_params['range'] or (0, max_range)
            # we need to plot irregardless of DO_PLOT to get ylim
            subplot.hist(times, bins, range=plot_range)
            subplot.set_title(title)
            subplot.set_xlabel('time')
            subplot.set_ylabel('count')
            # add some spacing to the top
            if conf_params is not None and conf_params['ylim'] is not None:
                ylim = conf_params['ylim']
            else:
                ylim = list(subplot.axes.get_ylim())
                if ylim[1] == 1:
                    ylim[1] += 0.1
                elif ylim[1] > 1:
                    ylim[1] += math.log10(ylim[1])
                if ylim[1] != 0:
                    clamp_ylim = ylim[1] + (ylim[1] / COUNT_RANGE_CLAMPING)
                    ylim[1] = round(ylim[1], -math.floor(math.log(clamp_ylim, COUNT_RANGE_CLAMPING)))
            if DO_PLOT:
                subplot.axes.set_ylim(ylim)
            else:
                subplot.clear()

            if conf_params is None:
                conf[key] = {
                    'bins': bins,
                    'range': plot_range,
                    'ylim': tuple(ylim),
                }
        self.plot_count += 1

    def save(self, prefix):
        """Save the figures to SVG files.

        The files created are named `prefix + figure_name + ".svg"`.
        """
        if not DO_PLOT:
            return
        for (name, fig) in self.figures.items():
            fig = fig[0]
            fig.savefig(prefix + name + '.svg')
            fig.clf()


def plot_scheduler(name, stats, conf):
    """Process scheduler stats."""
    figures = ThreadFigures(len(stats['children']) + 1)

    print('Plotting thread {}...'.format(name))
    conf_params = conf.setdefault(name, {})
    figures.plot_thread(name, stats, conf_params)

    for (key, values) in sorted(stats['children'].items()):
        print('Plotting thread {}...'.format(key))
        conf_params = conf.setdefault(key, {})
        scheduler = values.get('scheduler', None)
        if scheduler is not None:
            key += ' (' + ', '.join(scheduler.keys()) + ')'
        figures.plot_thread(key, values, conf_params)

    # strip the thread-id from the name
    figures.save(name[:name.rindex('-') + 1])

    print('Scheduler {} plotted.'.format(name))

    return conf


def get_scheduler_keyslist(scheduler_threads):
    """Get a list of keys to all scheduler threads contained in `scheduler_threads`.

    The returned list can be iterated over like so::

        for keys in get_scheduler_keyslist(stats):
            scheduler_stats = reduce(getitem, keys, stats)
            #scheduler_stats now points to statistics of a scheduler
    """
    keyslist = []
    for (name, scheduler) in scheduler_threads.items():
        keyslist.append((name,))
        for (child, child_thread) in scheduler['children'].items():
            scheduler = child_thread.get('scheduler', {})
            prefix = (name, 'children', child, 'scheduler')
            keyslist += (prefix + tuple(keys) for keys in get_scheduler_keyslist(scheduler))
    return keyslist


def do_scheduler(stats, keys, conf):
    """Call :func:`plot_scheduler` on the stats available through `keys`.

    :func:`get_scheduler_keyslist` can be used to obtain a list of valid `keys`.
    """
    return plot_scheduler(keys[-1], functools.reduce(operator.getitem, keys, stats), conf)


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


def flatten_conf(conf, prefix=()):
    """Flatten a hierarchical (wide) config `dict`.

    This is done by squashing keys into tuples, i.e.
    `{'a': {'a': 0, 'b': 1}, 'b': 2}` becomes
    `{('a', 'a'): 0, ('a', 'b'): 1, ('b',): 2}`.
    """
    flattened = {}
    for k, v in conf.items():
        if k in ('run', 'wait') and all(not isinstance(v, dict) for v in conf[k].values()):
            flattened.setdefault(prefix, {}).update({k: v})
            continue
        flattened.update(flatten_conf(v, prefix + (k,)))
    return flattened


def format_conf(conf, sep_indent='\n'):
    """Format the config `dict` nicely in a string."""
    # TODO: ideally we'd model the module hierarchy,
    #       not the scheduling chain, but this is way easier
    if isinstance(conf, dict):
        next_sep_indent = sep_indent + '    '
        values = []

        for key, value in conf.items():
            values.append('"' + str(key) + '": ' + format_conf(value, next_sep_indent))

        return '{' + next_sep_indent + (',' + next_sep_indent).join(values) + sep_indent + '}'

    return str(conf)


def widen_conf(conf, keyslist):
    """Convert the flattened config list back to a wide one.

    See :meth:`flatten_conf`.
    """
    wide = {}
    for keys in keyslist:
        # get rid of VCPUs in index
        entry = functools.reduce(operator.getitem, keys[1:-1:2], wide)
        found = False
        for subentry in conf:
            if keys[-1] in subentry:
                found = True
                entry.update(subentry)
        assert found
    return wide


def main():
    """Plot the statistics in `sys.argv[-1]`."""
    matplotlib.rcParams.update({'figure.max_open_warning': 0})

    if len(sys.argv) not in (2, 4) or sys.argv[1] in ('-h', '--help'):
        print('Usage: {0} [(--conf|--create-conf) conf.py] (stats.json|schedsi.log)\n'.format(sys.argv[0])
            + '	schedsi.log may be either a text log or a binary log.', file=sys.stderr)
        sys.exit(1)

    use_conf = len(sys.argv) == 4

    stats = get_stats(sys.argv[-1])

    keyslist = get_scheduler_keyslist(stats)

    conf = {}
    if use_conf and sys.argv[1] == '--conf':
        import importlib.util
        spec = importlib.util.spec_from_file_location('conf', sys.argv[2])
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        conf = flatten_conf(module.conf)

    conf_file = None
    if use_conf and sys.argv[1] == '--create-conf':
        conf_file = open(sys.argv[2], 'x')
        global DO_PLOT
        DO_PLOT = False

    # strip 'children' and 'scheduler' from keys
    confkeys = tuple(k[::2] for k in keyslist)
    keysconf = {k: conf.get(k, {}) for k in confkeys}
    if conf != keysconf:
        if sys.argv[1] == '--conf':
            print('Warning: config doesn\'t fit the stats.', file=sys.stderr)
        conf = keysconf

    # order for multiprocessing
    conf = collections.OrderedDict((k, conf[k]) for k in confkeys)
    with multiprocessing.Pool() as pool:
        conf = pool.starmap(functools.partial(do_scheduler, stats), zip(keyslist, conf.values()))
        assert len(conf) == len(keyslist)

    if conf_file is not None:
        conf = widen_conf(conf, confkeys)
        conf_file.write('conf = ' + format_conf(conf) + '\n')
        conf_file.close()


if __name__ == '__main__':
    main()
