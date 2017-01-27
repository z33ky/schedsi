#!/usr/bin/env python3
"""Defines the base class for schedulers."""

import inspect
import itertools
import sys
from schedsi import context, cpurequest, rcu


class SchedulerData:  # pylint: disable=too-few-public-methods
    """Mutable data for the :class:`Scheduler`.

    Mutable data for the scheduler needs to be updated atomically.
    To enable RCU this is kept in one class.
    """

    def __init__(self):
        """Create a :class:`SchedulerRCU`."""
        self.ready_chains = []
        self.waiting_chains = []
        self.finished_chains = []
        self.last_idx = -1


class Scheduler:
    """Scheduler base-class.

    Can schedule a single thread,
    raises an exception if more are in the queue.

    Has a :obj:`list` of :class:`context.Chains <schedsi.context.Chain>`.
    """

    def __init__(self, module, rcu_storage=None, *, time_slice=None):
        """Create a :class:`Scheduler`.

        Optionally takes a `rcu_storage` for which to create the :attr:`_rcu` for.
        It should be a subclass of :class:`SchedulerData`.

        The `time_slice` is for the kernel scheduler to set.
        """
        if rcu_storage is None:
            rcu_storage = SchedulerData()
        self._rcu = rcu.RCU(rcu_storage)
        self.module = module
        self.time_slice = time_slice

    @classmethod
    def builder(cls, *args, **kwargs):
        """Make a creator of :class:`Scheduler`.

        Returns a function taking a single argument:
        the :class:`Module` of the scheduler to create.
        `args` and `kwargs` are then also forwarded to :meth:`__init__`.
        """
        def make(module):
            """The creator function to be returned."""
            return cls(module, *args, **kwargs)
        return make

    def num_threads(self):
        """Return total number of threads.

        Includes both running and finished threads.
        """
        return self._rcu.look(lambda d:
                              sum(len(x) for x in
                                  [d.ready_chains, d.waiting_chains, d.finished_chains]))

    def add_thread(self, thread, rcu_data=None):
        """Add threads to schedule."""
        def appliance(data):
            """Append new threads to the waiting and finished queue."""
            chain = context.Chain.from_thread(thread)
            if thread.is_finished():
                data.finished_chains.append(chain)
            else:
                data.waiting_chains.append(chain)
        if rcu_data is None:
            self._rcu.apply(appliance)
        else:
            appliance(rcu_data)

    @classmethod
    def _update_ready_chains(cls, time, rcu_data):
        """Move threads becoming ready to the ready chains list."""
        cls._update_ready_chain_queues(time, rcu_data.ready_chains, rcu_data.waiting_chains)

        # do a sanity check while we're here
        assert not (0, -1) in ((c.bottom.remaining, c.bottom.ready_time)
                               for c in rcu_data.ready_chains)
        assert all(ctx.bottom.is_finished() for ctx in rcu_data.finished_chains)

    @staticmethod
    def _update_ready_chain_queues(time, ready_queue, waiting_queue):
        """Move threads becoming ready to the respective queues.

        See :meth:`Scheduler._update_ready_chains`.
        """
        for i in range(-len(waiting_queue), 0):
            if waiting_queue[i].bottom.ready_time <= time:
                ready_queue.append(waiting_queue.pop(i))

    def get_thread_statistics(self, current_time):
        """Obtain statistics of all threads."""
        rcu_data = self._rcu.read()
        all_threads = (ctx.bottom for ctx in
                       itertools.chain(rcu_data.finished_chains, rcu_data.waiting_chains,
                                       rcu_data.ready_chains))
        return {tid: stats for tid, stats in
                (((t.module.name, t.tid), t.get_statistics(current_time)) for t in all_threads)}

    def _start_schedule(self, _prev_run_time):
        """Prepare making a scheduling decision.

        Moves ready threads to the ready queue
        and finished ones to the finished queue.

        Returns a tuple (

            * RCUCopy of :attr:`_rcu`
            * list where previously scheduled chain ended up
                * (`rcu_copy_{ready,waiting,finished}_chains`)
            * index of previously scheduled chain
                * as passed to :meth:`_schedule`
                * *not* necessarily the index into the list where the chain ended up

        ).

        Yields an idle or execute :class:`~schedsi.cpurequest.Request`.
        Consumes the current time.
        """
        current_time = yield cpurequest.Request.current_time()
        while True:
            rcu_copy = self._rcu.copy()
            rcu_data = rcu_copy.data

            # check if the last scheduled thread is done now
            # move to a different queue is necessary
            dest = None
            last_idx = None
            if rcu_data.last_idx != -1:
                last_idx = rcu_data.last_idx
                # FIXME: last thread shouldn't be in ready_chains for multi-vcpu
                #        see _schedule() FIXME
                last_context = rcu_data.ready_chains[last_idx]

                if last_context.bottom.is_finished():
                    dest = rcu_data.finished_chains
                elif last_context.bottom.ready_time > current_time:
                    dest = rcu_data.waiting_chains
                else:
                    assert last_context.bottom.ready_time != -1

                if dest is None:
                    dest = rcu_data.ready_chains
                else:
                    dest.append(rcu_data.ready_chains.pop(last_idx))
                    # if not self._rcu.update(rcu_copy):
                    #     # current_time = yield cpurequest.Request.execute(1)
                    #     continue

            self._update_ready_chains(current_time, rcu_data)

            rcu_data.last_idx = -1

            return rcu_copy, dest, last_idx

    def _get_last_chain(self, rcu_data, last_chain_queue, last_chain_idx):  # pylint: disable=no-self-use
        """Return the last scheduled chain."""
        if last_chain_queue is rcu_data.ready_chains:
            return rcu_data.ready_chains[last_chain_idx]
        elif last_chain_queue is not None:
            return last_chain_queue[-1]
        return None

    def _schedule(self, idx, time_slice, rcu_copy):
        """Update :attr:`_rcu` and schedule the chain at `idx`.

        If `idx` is -1, yield an idle request.

        Yields a :class:`~schedsi.cpurequest.Request`.
        """
        rcu_copy.data.last_idx = idx
        # FIXME: we need to take it out of the ready_chains for multi-vcpu
        #        else we might try to run the same chain in parallel
        if not self._rcu.update(rcu_copy):
            return

        if idx == -1:
            yield cpurequest.Request.idle()
            return

        yield cpurequest.Request.timer(time_slice)

        rcu_copy.data.ready_chains[idx] = \
            yield cpurequest.Request.resume_chain(rcu_copy.data.ready_chains[idx])
        # FIXME: this can fail on multi-vcpu
        if not self._rcu.update(rcu_copy):
            assert False, 'Multi-vcpu synchronization not yet supported'

    def schedule(self, prev_run_time):
        """Schedule the next :class:`context.Chain <schedsi.context.Chain>`.

        This simply calls :meth:`_start_schedule`, :meth:`_sched_loop` and
        :meth:`_schedule` in a loop, passing appropriate arguments.

        Yields a :class:`~schedsi.cpurequest.Request`.
        Consumes the current time.
        """
        while True:
            rcu_copy, *rest = yield from self._start_schedule(*prev_run_time)
            idx, time_slice = yield from self._sched_loop(rcu_copy, *rest)

            yield from self._schedule(idx, time_slice, rcu_copy)

    def _sched_loop(self, rcu_copy, _last_chain_queue, _last_chain_idx):  # pylint: disable=no-self-use
        """Schedule the next :class:`context.Chain <schedsi.context.Chain>`.

        This :class:`Scheduler` is a base class.
        This function will only deal with a single :class:`context.Chain <schedsi.context.Chain>`.
        If more are present, a :exc:`RuntimeError` is raised.

        Returns the selected chain index, or -1 if none.
        Yields a :class:`~schedsi.cpurequest.Request`.
        Consumes the current time.
        """
        num_chains = len(rcu_copy.data.ready_chains)
        idx = 0
        if num_chains == 0:
            idx = -1
        if num_chains != 1:
            raise RuntimeError('Scheduler cannot make scheduling decision.')
        return idx, self.time_slice
        # needs to be a coroutine
        yield  # pylint: disable=unreachable


_PENALTY_SCHEDULER_CLASS_TEMPLATE = """\
from schedsi import scheduler
import {addon_cls_module}
import {scheduler_cls_module}

class {typename}(scheduler.SchedulerAddon, {scheduler_cls_module}.{scheduler_cls}):
    ':class:`{scheduler_cls}` with :class:`~{addon_cls}` attached.'

    def __init__({init_args}):
        'Create a :class:`{typename}`.'
        super().__init__({scheduler_forward}, {addon_cls_module}.{addon_cls}(self, {addon_forward}),
                         {scheduler_kwforward})
"""


class SchedulerAddonBase():
    """Scheduler addon base-class.

    Scheduler addons should use this as their baseclass.
    The :class:`SchedulerAddon` will call these functions
    like hooks.
    """

    def __init__(self, scheduler):
        """Create a :class:`SchedulerAddonBase`."""
        self.scheduler = scheduler

    @classmethod
    def attach(cls, typename, scheduler_cls):
        """Create a scheduler-class with an addon attached.

        A new class named `typename` is returned, which represents the `scheduler_cls`
        with the addon attached.
        """
        signature = inspect.signature(cls.__init__)
        init_args = ', '.join(str(v) for v in signature.parameters.values()) + ', **kwargs'

        parameters = signature.parameters.copy()
        # pop self-parameter
        parameters.popitem(0)
        # pop *args
        _, args = parameters.popitem(0)
        if args.kind is not inspect.Parameter.VAR_POSITIONAL:
            raise NotImplementedError('Positional addon parameters not implemented.')
        if any(arg.kind is inspect.Parameter.VAR_KEYWORD for arg in parameters.values()):
            raise NotImplementedError('**kwargs for addon parameters not implemented.')

        addon_forward = ', '.join(param.name + '=' + param.name for param in parameters.values())

        # this mirrors how the pure-python stdlib does dynamic class creation
        class_definition = _PENALTY_SCHEDULER_CLASS_TEMPLATE.format(
            typename=typename,
            addon_cls_module=cls.__module__,
            addon_cls=cls.__name__,
            scheduler_cls_module=scheduler_cls.__module__,
            scheduler_cls=scheduler_cls.__name__,
            init_args=init_args,
            scheduler_forward='*args',
            scheduler_kwforward='**kwargs',
            addon_forward=addon_forward,
        )
        namespace = {'__name__': 'schedaddon_' + typename}
        exec(class_definition, namespace)  # pylint: disable=exec-used
        result = namespace[typename]
        result._source = class_definition
        try:
            result.__module__ = sys._getframe(1).f_globals.get('__name__', '__main__')  # pylint: disable=protected-access
        except (AttributeError, ValueError):
            pass

        return result

    def transmute_rcu_data(self, original, *addon_data):  # pylint: disable=no-self-use
        """Transmute a :class:`SchedulerData`.

        This should be called like `super().transmute_rcu_data(original, MyAddonData, *addon_data)`.
        `MyAddonData` should not inherit from :class:`SchedulerData`.

        The result is that the scheduler's rcu_data will be merged with `MyAddonData`.
        """
        if len(addon_data) == 0:
            return

        class AddonData(*addon_data):  # pylint: disable=too-few-public-methods
            """Joins all `addon_data` into one class."""

            pass
        original.__class__ = AddonData
        for data in addon_data:
            data.__init__(original)

    def _get_last_chain(self, rcu_data, last_chain_queue, last_chain_idx):
        """Return the last scheduled thread of :attr:`scheduler`.

        See :meth:`Scheduler._get_last_chain`.
        """
        return self.scheduler._get_last_chain(rcu_data, last_chain_queue, last_chain_idx)  # pylint: disable=protected-access

    def start_schedule(self, _prev_run_time, _rcu_data, _last_chain_queue, _last_chain_idx):  # pylint: disable=no-self-use
        """Hook for :meth:`_start_schedule`."""
        pass

    def schedule(self, _idx, time_slice, _rcu_data):  # pylint: disable=no-self-use
        """Hook for :meth:`_schedule`.

        Return a tuple (

            * True to proceed, False to schedule another chain
            * time slice

        )
        The :class:`SchedulerAddon` captures the :class:`requests <schedsi.cpurequest.Request>`
        yielded from :meth:`Scheduler._schedule` to filter the resume-chain request and override
        the timer request.
        Care should be taken for the case the same chain is selected again.
        """
        return True, time_slice


class SchedulerAddon(Scheduler):
    """Scheduler with addon.

    This can be used to add scheduler addons via
    multiple inheritance.
    For instance, if we wanted the Addon `MyAddon`
    with the `BaseScheduler` scheduler, you can do this::

        class MyScheduler(SchedulerAddon, BaseScheduler):
            def __init__(self, module):
                super().__init__(module, MyAddon("addon-param"), "sched-param")

    """

    def __init__(self, module, addon, *args, **kwargs):
        """Create a :class:`SchedulerAddon`."""
        super().__init__(module, *args, **kwargs)
        self.addon = addon
        addon.transmute_rcu_data(self._rcu._data)

    def _start_schedule(self, prev_run_time):
        """See :meth:`Scheduler._start_schedule`.

        This will also call the
        :attr:`addon`'s :meth:`~SchedulerAddonBase.start_schedule` hook.
        """
        rcu_copy, *rest = yield from super()._start_schedule(prev_run_time)

        self.addon.start_schedule(prev_run_time, rcu_copy.data, *rest)

        return (rcu_copy, *rest)

    def _schedule(self, idx, time_slice, rcu_copy):
        """See :meth:`Scheduler._schedule`.

        This will also call the :attr:`addon`'s :meth:`~SchedulerAddonBase.schedule`.
        """
        schedule = super()._schedule(idx, time_slice, rcu_copy)
        proceed, time_slice = self.addon.schedule(idx, time_slice, rcu_copy.data)
        # TODO: ideally we would avoid creating a new rcu_copy for the next schedule() call
        for request in schedule:
            if request.rtype == cpurequest.Type.timer:
                if not proceed:
                    continue
                request.thing = time_slice
            elif request.rtype == cpurequest.Type.resume_chain:
                try:
                    response = request.thing
                    if proceed:
                        response = (yield request)
                    request = schedule.send(response)
                except StopIteration:
                    return
                assert request.rtype not in (cpurequest.Type.idle, cpurequest.Type.resume_chain)
            yield request
