#!/usr/bin/env python3
"""Run a simulation loaded from a schedsim-file.

The schedsim file format is documented in `schedsim`.
"""

import sys
from schedsi import world
from schedsi.util import hierarchy_builder
from parser import (Cursor, MalformedString, MalformedSymbol, Parser, ParserError, Symbol,
                    SymbolKind, UntermiatedString)
from interpreter import InterpreterError, load_log, load_simulation

def append_modules(children, parent):
    """Generate :class:`Module`s from `children` attached to `parent`.

    `parent` may be `None` for the kernel.

    Return the list of generated modules.
    """
    modules = []
    for name, sched, workload, mods in children:
        if parent is not None:
            module = parent.add_module(name, scheduler=sched[0].builder(**sched[1]))
        else:
            module = hierarchy_builder.ModuleBuilder(name, scheduler=sched[0].builder(**sched[1]))

        append_modules(mods, module)

        for thread, tid, kwargs in workload:
            module.add_thread(thread, tid=tid, **kwargs)
        module.add_vcpus()

        modules.append(module)
    return modules

def main():
    """Load and run a simulation."""
    if len(sys.argv) != 2:
        print(f'Usage: {sys.argv[0]} simulation.schedsim', file=sys.stderr)
        sys.exit(1)

    filename = sys.argv[1]
    sfile = open(filename, 'r')
    try:
        parser = Parser(sfile)
        nodes = (*parser,)
    except ParserError as error:
        begin, end = error.get_range()

        print(f'Encountered an error while parsing {filename}:\n'
              f'{error.msg} in line {begin.line}.', file=sys.stderr)

        # some common stuff used for specific error handling
        linebegin = begin.get_line_begin().byte
        # assert end == parser.cursor
        sfile.seek(linebegin)
        line_to_token = sfile.read(begin.byte - linebegin)
        tokenstr = sfile.read(end.byte - begin.byte + 1)
        if tokenstr[-1:] == '\n':
            tokenstr = tokenstr[:-1]
            line_rest = '\n'
        else:
            line_rest = sfile.readline()
            if line_rest[-1:] != '\n':
                line_rest = line_rest + '\n'
        token_spacing = ''.join(c if c.isspace() else ' ' for c in line_to_token)
        # sfile.seek(end.byte)

        if isinstance(error, UntermiatedString):
            assert tokenstr == '"' + error.node.string
            print(f'\t{line_to_token}{tokenstr}{line_rest}\t{token_spacing}^-- beginning here',
                  file=sys.stderr)
        elif isinstance(error, MalformedString):
            string = error.node
            assert tokenstr == '"' + string.string + '"'

            # we remove the quotes from the string
            tokenstr = tokenstr[1:-1]
            # and also the quotes from the repr
            stringrepr = repr(tokenstr)[1:-1]
            # we include an additional space to token_spacing for the quote character
            sys.stderr.write(f'\t{line_to_token}"{stringrepr}"{line_rest}\t{token_spacing} ')

            prev_idx = 0
            for idx in string.invalid_indices():
                # two are subtracted to disregard the quotes from the repr
                sys.stderr.write(' ' * (len(repr(tokenstr[prev_idx:idx])) - 2) +
                                 '-' * (len(repr(tokenstr[idx])) - 2))
                prev_idx = idx + 1

            print(file=sys.stderr)
        elif isinstance(error, MalformedSymbol):
            symbol = error.node
            assert tokenstr == symbol.symbol

            line = f'\t{line_to_token}{tokenstr}{line_rest}\t{token_spacing}'
            print(f'{line}{"-" * len(tokenstr)}', file=sys.stderr)

            for kind in SymbolKind:
                errors = ''
                for idx in symbol.invalid_indices(kind):
                    if idx is None:
                        assert errors == ''
                        break
                    errors += ' ' * idx + '-'
                else:
                    print(f'Invalid characters as {kind.name}:\n{line}{errors}', file=sys.stderr)

        sys.exit(1)
    # print(repr(nodes))

    try:
        sim = load_simulation(nodes)
    except InterpreterError as err:
        sys.stderr.write(f'Encountered an error while interpreting {filename}:\n{err.msg}')
        node = err.node
        if node is None:
            print(file=sys.stderr)
        else:
            # print the line as well
            begin, end = node.cursor
            print(f' on line {begin.line}:', file=sys.stderr)
            # note that we indent every line printed now

            linebegin = begin.get_line_begin().byte
            sfile.seek(linebegin)
            lines = sfile.read(end.byte - linebegin)

            token_spacing = '\t' + ''.join(c if c.isspace() else ' '
                                           for c in lines[:begin.col - 1])

            last_line_begin = lines.rfind('\n') + 1

            # complete the line
            lines = '\t' + lines + sfile.readline()
            if lines[-1:] != '\n':
                lines += '\n'

            if last_line_begin == 0:
                # single line, just underline the node
                sys.stderr.write(lines)
                # we add one to include the last column
                tokenlen = len(repr(lines[begin.col:end.col + 1])) - 2
                print(token_spacing, '-' * tokenlen, sep='', file=sys.stderr)
            else:
                # multiple lines, point to beginning and end of node
                print(token_spacing, 'v-- from here', sep='', file=sys.stderr)
                sys.stderr.write(lines.replace('\n', '\n\t'))

                last_line = lines[last_line_begin + 1:]
                last_spaces = last_line[:-len(last_line.lstrip())]
                print(last_spaces, ' ' * (end.col - len(last_spaces) - 1), '^-- to here', sep='',
                      file=sys.stderr)

        sys.exit(1)

    if 'log' not in sim:
        sim['log'] = load_log([Symbol(Cursor(None), 'BinaryLog')])

    if 'kernel' not in sim:
        print('Simulation must define a kernel module.', file=sys.stderr)
        sys.exit(1)
    kernel = append_modules((sim['kernel'],), None)[0]

    logger, logger_finish = sim['log']

    if 'local_timer' not in sim:
        print('Simulation must set the local_timer parameter.', file=sys.stderr)
        sys.exit(1)
    the_world = world.World(1, kernel.module, logger, local_timer_scheduling=sim['local_timer'])
    limit = sim.get('time_limit', float('inf'))
    try:
        while the_world.step() <= limit:
            pass
    except RuntimeError:
        if not all(thread.is_finished() for thread in kernel.module.all_threads()):
            raise
    logger_finish(the_world)

if __name__ == '__main__':
    main()
