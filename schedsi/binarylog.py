#!/usr/bin/env python3
"""Defines the :class:`BinaryLog` and the :func:`replay` function."""

from schedsi import types
import collections
import enum
import msgpack
import typing

if typing.TYPE_CHECKING:
    from schedsi import context, cpu, module, threads

# https://github.com/python/mypy/issues/2306
#_EntryType = enum.Enum('_EntryType', ['event', 'thread_statistics', 'cpu_statistics'])
#_Event = enum.Enum('_Event', [
#    'init_core',
#    'context_switch',
#    'thread_execute',
#    'thread_yield',
#    'cpu_idle',
#    'timer_interrupt'
#])
class _EntryType(enum.Enum):
    event = 1
    thread_statistics = 2
    cpu_statistics = 3

class _Event(enum.Enum):
    init_core = 1
    context_switch = 2
    thread_execute = 3
    thread_yield = 4
    cpu_idle = 5
    timer_interrupt = 6

_GenericEvent = collections.namedtuple('_GenericEvent', 'cpu event')


# _LogValues = typing.Union[float, str, '_LogDict', typing.List[_LogValues]]
# https://github.com/python/mypy/issues/1561
# instead manually unroll '_LogValues' two levels
_LogValues2 = typing.Union[float, str, typing.Dict[str, typing.Any],
                           typing.List[typing.Union[float, str, typing.Dict[str, typing.Any]]]]
_LogValues1 = typing.Union[_LogValues2, typing.Dict[str, _LogValues2], typing.List[_LogValues2]]
_LogValues0 = typing.Union[_LogValues1, typing.Dict[str, _LogValues1], typing.List[_LogValues1]]
_LogDict = typing.Dict[str, _LogValues0]


def _encode_cpu(cpu: 'cpu.Core') -> _LogDict:
    """Encode a :class:`~schedsi.cpu.Core` to a :obj:`dict`."""
    assert cpu.uid == int(cpu.uid)
    return {
        'uid': int(cpu.uid),
        'status': {'current_time': cpu.status.current_time}
    }


def _encode_contexts(contexts: typing.List['context.Context'],
                     current_context: typing.Optional['context.Context']) -> typing.List[_LogDict]:
    """Encode a :class:`~schedsi.context.Context` to a :obj:`dict`.

    `current_context` is the top context of the current
    :class:`context.chain <schedsi.context.Chain>.
    """
    def stringify_relationship(top: 'threads.Thread', bottom: 'threads.Thread') -> str:
        """Stringify the relationship between the :class:`Modules <schedsi.module.Module>` \
        `top` and `bottom`.

        `top` and `bottom` should refer to :class:`Modules <schedsi.module.Module>`
        following each other in the :class:`context.Chain <schedsi.context.Chain>`.
        """
        is_child = top.module.parent == bottom.module
        if not is_child:
            assert top.module == bottom.module
        return 'child' if is_child else 'sibling'

    first = contexts[0].thread
    chain = [_LogDict({'thread': _encode_thread(first)})]
    if current_context is not None:
        chain[0].update({'relationship': stringify_relationship(first, current_context.thread)})

    for cur, prev in zip(contexts[1:], contexts):
        chain.append({
            'thread': _encode_thread(cur.thread),
            'relationship': stringify_relationship(cur.thread, prev.thread)
        })

    return chain


def _encode_module(module: 'module.Module') -> _LogDict:
    """Encode a :class:`~schedsi.module.Module` to a :obj:`dict`."""
    return {'name': module.name}


def _encode_thread(thread: 'threads.Thread') -> _LogDict:
    """Encode a :class:`~schedsi.threads.Thread` to a :obj:`dict`."""
    assert thread.tid == int(thread.tid)
    return {'module': _encode_module(thread.module), 'tid': int(thread.tid)}


def _encode_event(cpu: 'cpu.Core', event: str, args: _LogDict = None) -> _LogDict:
    """Create a :class:`_GenericEvent`.

    `args` can contain additional parameters to put in the :obj:`dict`.
    """
    encoded = _LogDict({'cpu': _encode_cpu(cpu), 'event': event, 'type': _EntryType.event.name})
    if args is not None:
        encoded.update(args)
    return encoded


def _encode_ctxsw(cpu: 'cpu.Core', split_index: typing.Optional[int],
        appendix: typing.Optional['context.Chain'], time: types.Time) -> _LogDict:
    """Encode a context switching event to a :obj:`dict`."""
    if appendix is None:
        assert split_index is not None
        param = _LogDict({'split_index': split_index})
    else:
        assert split_index is None
        param = _LogDict({'appendix': _encode_contexts(appendix.contexts,
                                                       cpu.status.chain.current_context)})

    param['time'] = time

    return _encode_event(cpu, _Event.context_switch.name, param)


def _encode_coreinit(cpu: 'cpu.Core') -> _LogDict:
    """Encode a init_core event to a :obj:`dict`."""
    return _encode_event(cpu, _Event.init_core.name,
                         {'context': _encode_contexts(cpu.status.chain.contexts, None)})


class BinaryLog:
    """Binary logger using MessagePack."""

    stream: typing.BinaryIO
    packer: msgpack.Packer

    def __init__(self, stream: typing.BinaryIO) -> None:
        """Create a :class:`BinaryLog`."""
        self.stream = stream
        self.packer = msgpack.Packer()

    def _write(self, data: _LogDict) -> None:
        """Write data to the MessagePack file."""
        self.stream.write(self.packer.pack(data))

    def _encode(self, cpu: 'cpu.Core', event: _Event, args: _LogDict = None) -> None:
        """Encode an event and write data to the MessagePack file.

        See :func:`_encode_event`.
        """
        self._write(_encode_event(cpu, event.name, args))

    def init_core(self, cpu: 'cpu.Core') -> None:
        """Register a :class:`Core`."""
        self._write(_encode_coreinit(cpu))

    def context_switch(self, cpu: 'cpu.Core', split_index: typing.Optional[int],
                       appendix: typing.Optional['context.Chain'], time: types.Time) -> None:
        """Log an context switch event."""
        self._write(_encode_ctxsw(cpu, split_index, appendix, time))

    def thread_execute(self, cpu: 'cpu.Core', runtime: types.Time) -> None:
        """Log an thread execution event."""
        self._encode(cpu, _Event.thread_execute, {'runtime': runtime})

    def thread_yield(self, cpu: 'cpu.Core') -> None:
        """Log an thread yielded event."""
        self._encode(cpu, _Event.thread_yield)

    def cpu_idle(self, cpu: 'cpu.Core', idle_time: types.Time) -> None:
        """Log an CPU idle event."""
        self._encode(cpu, _Event.cpu_idle, {'idle_time': idle_time})

    def timer_interrupt(self, cpu: 'cpu.Core', idx: int, delay: types.Time) -> None:
        """Log an timer interrupt event."""
        self._encode(cpu, _Event.timer_interrupt, {'idx': idx, 'delay': delay})

    def thread_statistics(self, stats: 'threads.ThreadStatsDict') -> None:
        """Log thread statistics."""
        self._write({'type': _EntryType.thread_statistics.name, 'stats': stats})

    def cpu_statistics(self, stats: typing.Iterable['cpu.CoreStatsDict']) -> None:
        """Log CPU statistics."""
        self._write({'type': _EntryType.cpu_statistics.name, 'stats': list(stats)})


# types emulating schedsi classes for other logs
_CPUContext = collections.namedtuple('_CPUContext', 'thread')
_Core = collections.namedtuple('_Core', 'uid status')

# namedtuples are immutable, but the following classes require mutable fields


class _Module:  # pylint: disable=too-few-public-methods
    """A :class:`~schedsi.module.Module` emulation class."""

    name: str
    parent: typing.Optional[_Module] = None

    def __init__(self, name: str) -> None:
        """Create a :class:`_Module`."""
        self.name = name


class _ContextChain(typing.Sized):
    """A :class:`context.Chain <schedsi.context.Chain>` emulation class."""

    contexts: typing.List[_CPUContext]

    def __init__(self, contexts: typing.List[_CPUContext] = None) -> None:
        """Create a :class:`_ContextChain`."""
        self.contexts = contexts or []

    def __len__(self) -> int:
        """Return the length of the :class:`_ContextChain`.

        See :meth:`context.Chain.__len__ <schedsi.context.Chain.__len__>`.
        """
        return len(self.contexts)

    @property
    def bottom(self) -> '_Thread':
        """The bottom thread.

        See :py:attr:`context.Chain.thread_at <schedsi.context.Chain.bottom>`.
        """
        return self.contexts[0].thread

    @property
    def top(self) -> '_Thread':
        """The top thread.

        See :py:attr:`context.Chain.top <schedsi.context.Chain.top>`.
        """
        return self.contexts[-1].thread

    @property
    def current_context(self) -> _CPUContext:
        """The current (top) context.

        See :py:attr:`context.Chain.current_context <schedsi.context.Chain.current_context>`.
        """
        return self.contexts[-1]

    def thread_at(self, idx: int) -> '_Thread':
        """Return the thread at index `idx` in the chain.

        Negative values are treated as an offset from the back.

        See :meth:`context.Chain.thread_at <schedsi.context.Chain.thread_at>`.
        """
        return self.contexts[idx].thread


class _CPUStatus:  # pylint: disable=too-few-public-methods
    """A :class:`~schedsi.cpu._Status` emulation class."""

    current_time: types.Time
    chain: _ContextChain

    def __init__(self, current_time: types.Time) -> None:
        """Create a :class:`_CPUStatus`."""
        self.current_time = current_time
        self.chain = _ContextChain()


class _Thread:  # pylint: disable=too-few-public-methods
    """A :class:`~schedsi.threads.Thread` emulation class."""

    tid: int
    module: '_Module'

    def __init__(self, tid: int, module: '_Module') -> None:
        """Create a :class:`_Thread`."""
        self.tid = tid
        self.module = module


def _decode_contexts(entries, current_context):
    """Extract :class:`_CPUContexts <_CPUContext>` from a :obj:`dict`-entry.

    `current_context` is the top context of the current
    :class:`context.chain <schedsi.context.Chain>.
    """
    contexts = [_CPUContext(_decode_thread(entry['thread'])) for entry in entries]
    if current_context is None:
        assert 'relationship' not in entries[0]
        return contexts
    for prev, cur, ent in zip([current_context] + contexts, contexts, entries):
        rel = ent.get('relationship', None)
        if rel == 'child':
            cur.thread.module.parent = prev.thread.module
        elif rel == 'sibling':
            cur.thread.module = prev.thread.module
        else:
            assert False
    return contexts


def _decode_generic_event(entry):
    """Convert a :obj:`dict-entry` to a :class:`_GenericEvent`.

    Returns :obj:`None` on failure.
    """
    if entry['type'] == _EntryType.event.name:
        return _GenericEvent(_decode_core(entry), entry['event'])
    return None


def _decode_core(entry):
    """Extract a :class:`_Core` from a :obj:`dict`-entry."""
    core = entry['cpu']
    return _Core(core['uid'], _decode_status(core['status']))


def _decode_status(entry):
    """Extract :class:`_CPUStatus` from a :obj:`dict`-entry."""
    return _CPUStatus(entry['current_time'])


def _decode_thread(entry):
    """Extract a :class:`_Thread` from a :obj:`dict`-entry.

    Returns :obj:`None` if `entry` is :obj:`None`.
    """
    if not entry:
        return None
    return _Thread(entry['tid'], _decode_module(entry['module']))


def _decode_module(entry):
    """Extract a :class:`_Module` from a :obj:`dict`-entry.

    Returns :obj:`None` if `entry` is :obj:`None`.
    """
    if not entry:
        return None
    return _Module(entry['name'])


def _decode_ctxsw(cpu, entry):
    """Extract context switch arguments from a :obj:`dict`-entry.

    Returns a tuple (split_index, appendix) corresponding to the
    `split_index` and `appendix` parameters to :meth:`BinaryLog.context_switch`.
    """
    split_index = entry.get('split_index', None)
    appendix = entry.get('appendix', None)

    if split_index is not None:
        assert appendix is None
    else:
        assert appendix is not None
        appendix = _ContextChain(_decode_contexts(appendix, cpu.status.chain.current_context))

    return (split_index, appendix)


def replay(binary: typing.BinaryIO, log: types.Log) -> None:
    """Play a MessagePack file to another log."""
    contexts: typing.Dict[int, _CPUContext] = {}
    for entry in msgpack.Unpacker(binary, read_size=16 * 1024, encoding='utf-8', use_list=False):
        event = _decode_generic_event(entry)
        if event is not None:
            if event.event == _Event.init_core.name:
                if event.cpu.uid in contexts:
                    raise RuntimeError('init_core found twice for same core')
                contexts[event.cpu.uid] = _decode_contexts(entry['context'], None)

            event.cpu.status.chain.contexts = contexts[event.cpu.uid]

            if event.event == _Event.init_core.name:
                log.init_core(event.cpu)
            elif event.event == _Event.context_switch.name:
                split_index, appendix = _decode_ctxsw(event.cpu, entry)
                log.context_switch(event.cpu, split_index, appendix, entry['time'])
                chain = event.cpu.status.chain
                if split_index is not None:
                    del chain.contexts[split_index + 1:]
                else:
                    chain.contexts += appendix.contexts
            elif event.event == _Event.thread_execute.name:
                log.thread_execute(event.cpu, entry['runtime'])
            elif event.event == _Event.thread_yield.name:
                log.thread_yield(event.cpu)
            elif event.event == _Event.cpu_idle.name:
                log.cpu_idle(event.cpu, entry['idle_time'])
            elif event.event == _Event.timer_interrupt.name:
                log.timer_interrupt(event.cpu, entry['idx'], entry['delay'])
            else:
                print('Unknown event:', event)
        elif entry['type'] == _EntryType.thread_statistics.name:
            log.thread_statistics(entry['stats'])
        elif entry['type'] == _EntryType.cpu_statistics.name:
            log.cpu_statistics(entry['stats'])
        else:
            print('Unknown entry:', entry)


def get_thread_statistics(binary: typing.BinaryIO) -> str:
    """Read thread statistics from a MessagePack file."""
    for entry in msgpack.Unpacker(binary, read_size=16 * 1024, encoding='utf-8', use_list=False):
        if entry['type'] == _EntryType.thread_statistics.name:
            return entry['stats']
    raise RuntimeError('Thread statistics not found.')
