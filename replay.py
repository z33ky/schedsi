#!/usr/bin/env python3
"""Converter for binary log files."""

import datetime
import sys
from schedsi import binarylog, graphlog, textlog

NOW = datetime.datetime.now().isoformat()


def _extract_param(arg, name):
    """Extract a parameter in the style of "key=value".

    Return `''` if the `arg == name`,
           :obj:`None` if the key does not match name,
           value otherwise (might be `''`).
    """
    if arg.startswith(name):
        param = arg[len(name):]
        if param == '':
            return ''
        if param[0] != '=':
            return None
        return param[1:]
    return None


def _usage():
    """Print usage and exit with error."""
    print('Usage:', sys.argv[0], 'IN_FILENAME [(--text[=FILENAME[TEXT_ALIGN]]|--graph[=FILENAME])]')
    print('if IN_FILENAME is -, read from stdin.')
    print('If FILENAME is not set, create use using the current system time.')
    print('If FILENAME is -, write to stdout.')
    print('TEXT_ALIGN is in the format :cpu:time:module:thread:, '
          'where each element between to colons is a number '
          'specifying the padding of the fields in the text log.')
    print('If neither --text nor --graph are specified, --text=- is assumed.')
    sys.exit(1)


def main():
    """Convert a schedsi binary log file."""
    if not 2 <= len(sys.argv) <= 3:
        _usage()

    param = sys.argv[2] if len(sys.argv) > 2 else '--text=-'

    input_file_name = sys.argv[1]
    log_from_file = input_file_name != '-'
    with open(input_file_name, 'rb') if log_from_file else sys.stdin.buffer as input_log:
        value = _extract_param(param, '--text')
        if value is not None:
            fileparam = value.split(':')
            filename = fileparam[0]
            align = None
            if len(fileparam) > 1:
                alignparam = fileparam[1:]
                print(*alignparam)
                if len(alignparam) != 5:
                    print('Invalid TEXT_ALIGN', alignparam)
                else:
                    align = textlog.TextLogAlign(*(int(x) for x in alignparam[:-1]))

            if align is None:
                align = textlog.TextLogAlign(cpu=1, time=3, module=7, thread=1)

            if not filename:
                filename = NOW + '.log'
            log_to_file = filename != '-'
            with open(filename, 'x') if log_to_file else sys.stdout as log_file:
                binarylog.replay(input_log, textlog.TextLog(log_file, align))
                if log_to_file:
                    print('Wrote to', filename)
            return

        value = _extract_param(param, '--graph')
        if value is not None:
            filename = value
            if not filename:
                filename = NOW + '.svg'

            log_to_file = filename != '-'
            with open(filename, 'xb') if log_to_file else sys.stdout.buffer as log_file:
                log = graphlog.GraphLog()
                binarylog.replay(input_log, log)
                log.write(log_file)
                if log_to_file:
                    print('Wrote to', filename)
            return

        _usage()


if __name__ == '__main__':
    main()
