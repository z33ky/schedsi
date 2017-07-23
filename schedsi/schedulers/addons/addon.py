"""Defines :class:`Addon` and :class:`AddonScheduler`."""

import inspect
import sys
from schedsi.cpu.request import Request as CPURequest, Type as CPURequestType
from ..scheduler import Scheduler


_PENALTY_SCHEDULER_CLASS_TEMPLATE = """\
from schedsi.schedulers.addons import addon
import {addon_cls_module}
import {scheduler_cls_module}

class {typename}Meta(type):
    '''Metaclass of :class:`{typename}`.

    Provides a custom method resolution order.
    '''
    def mro(cls):
        'Return the mro of :class:`{typename}`.'
        order = super().mro()
        # put AddonSchedulerBase just before Scheduler
        base = order.index(addon.AddonSchedulerBase)
        superbaseidx = order.index(addon.AddonSchedulerBase.__base__)
        order = order[:base] + order[base + 1:superbaseidx] \\
              + [addon.AddonSchedulerBase] + order[superbaseidx:]
        return order


class {typename}(addon.AddonScheduler, {scheduler_cls_module}.{scheduler_cls},
                 metaclass={typename}Meta):
    ':class:`{scheduler_cls}` with :class:`~{addon_cls}` attached.'

    def __init__({init_args}):
        'Create a :class:`{typename}`.'
        super().__init__({scheduler_forward}, {addon_cls_module}.{addon_cls}(self, {addon_forward}),
                         {scheduler_kwforward})
"""


class AddonSchedulerBase(Scheduler):
    """Scheduler Base-class for :class:`AddonScheduler`.

    See :class:`AddonScheduler`.
    """

    def __init__(self, module, *args, **kwargs):
        """Create a :class:`AddonSchedulerBase`."""
        super().__init__(module, *args, **kwargs)
        # set this to skip Scheduler._start_schedule
        self._start_schedule_rcu_copy = None

    def _start_schedule(self, prev_run_time):
        """See :meth:`Scheduler._start_schedule`.

        This skips :meth:`Scheduler._start_schedule`
        if :attr:`_start_schedule_rcu_copy` is set.

        Resets :attr:`_start_schedule_rcu_copy` to `None`.
        """
        if self._start_schedule_rcu_copy is None:
            return (yield from super()._start_schedule(prev_run_time))

        rcu_copy = self._start_schedule_rcu_copy
        self._start_schedule_rcu_copy = None
        idx = rcu_copy.data.last_idx

        self._update_ready_chains((yield CPURequest.current_time()), rcu_copy.data)
        rcu_copy.data.last_idx = -1
        return rcu_copy, rcu_copy.data.ready_chains, idx


class AddonScheduler(AddonSchedulerBase):
    """Scheduler with addon.

    This can be used to add scheduler addons via multiple inheritance.
    A metaclass is required to implement the desired MRO. Use :meth:`Addon.attach`
    to generate a scheduler-class with an addon attached.
    """

    def __init__(self, module, addon, *args, **kwargs):
        """Create a :class:``."""
        super().__init__(module, *args, **kwargs)
        self.addon = addon
        addon.transmute_rcu_data(self._rcu._data)
        # this is a pair (rcu_copy, time_slice) for repeating scheduling decisions
        # we don't need this in rcu_copy because we only use this within a single schedule() call
        self._repeat = (None, None)
        # FIXME: this should probably be in a rcu_copy though
        self._prev_run_time = 0

    def add_thread(self, thread, rcu_data=None, **kwargs):
        """See :meth:`Scheduler.add_thread`."""
        super_add_thread = super().add_thread
        def appliance(data):
            self.addon.add_thread(thread, data)
            super_add_thread(thread, data, **kwargs)
        if rcu_data is None:
            self._rcu.apply(appliance)
        else:
            appliance(rcu_data)

    def _check_repeat(self, prev_run_time):
        """Check if the :attr:`addon` wants to repeat.

        And set it up if so.
        """
        self._repeat = (None, None)

        rcu_copy = self._start_schedule_rcu_copy
        if rcu_copy is None:
            rcu_copy = self._rcu.copy()

        rcu_data = rcu_copy.data
        if rcu_data.last_idx == -1:
            return

        chain = rcu_data.ready_chains[rcu_data.last_idx]
        current_time = yield CPURequest.current_time()
        done = chain.bottom.is_finished() or chain.bottom.ready_time > current_time

        repeat, time_slice = self.addon.repeat(rcu_data, prev_run_time, done)
        if not repeat:
            return
        assert not done
        assert time_slice is None or time_slice > 0

        self._repeat = (rcu_copy, time_slice)

    def _sched_loop(self, rcu_copy, last_chain_queue, last_chain_idx):
        """See :meth:`Scheduler._sched_loop`.

        Takes care of repeating the last decision, if desired.
        """
        if self._repeat[0] is not None:
            assert self._repeat[0] is rcu_copy
            assert rcu_copy.data.last_idx != -1
            return rcu_copy.data.last_idx, self._repeat[1]
        return (yield from super()._sched_loop(rcu_copy, last_chain_queue, last_chain_idx))

    def _start_schedule(self, prev_run_time):
        """See :meth:`AddonSchedulerBase._start_schedule`.

        This will also call the
        :attr:`addon`'s :meth:`~Addon.start_schedule` hook.
        """
        yield from self._check_repeat(prev_run_time)
        if self._repeat[0] is not None:
            self._prev_run_time += prev_run_time
            return (self._repeat[0], None, None)
        assert self._repeat[1] is None

        if prev_run_time is not None:
            prev_run_time += self._prev_run_time
            self._prev_run_time = 0
        else:
            assert self._prev_run_time == 0

        rcu_copy, *rest = yield from super()._start_schedule(prev_run_time)

        self.addon.start_schedule(prev_run_time, rcu_copy.data, *rest)

        return (rcu_copy, *rest)

    def _schedule(self, idx, time_slice, next_ready_time, rcu_copy):
        """See :meth:`Scheduler._schedule`.

        This will also call the :attr:`addon`'s :meth:`~Addon.schedule`.
        """
        proceed, time_slice = self.addon.schedule(idx, time_slice, rcu_copy.data)

        if not proceed:
            rcu_copy.data.last_idx = idx
            self._start_schedule_rcu_copy = rcu_copy
            if self._repeat[0] is not None:
                # block repeating
                self.addon.repeat(rcu_copy.data, 0, True)
            return

        schedule = super()._schedule(idx, time_slice, next_ready_time, rcu_copy)
        answer = None
        while True:
            try:
                request = schedule.send(answer)
            except StopIteration:
                break

            if request.rtype == CPURequestType.timer:
                delta = None
                if next_ready_time[0] != 0:
                    if next_ready_time[0] is not None:
                        current_time = yield CPURequest.current_time()
                        delta = next_ready_time[0] - current_time
                    # if this assumption does not hold we need to decide
                    # whether we really want to override this
                    assert delta == request.arg
                if time_slice is None or delta is None:
                    request.arg = time_slice

            answer = yield request


class Addon():
    """Scheduler addon base-class.

    Scheduler addons should use this as their baseclass.
    The :class:`AddonScheduler` will call these functions
    like hooks.
    """

    def __init__(self, scheduler):
        """Create a :class:`Addon`."""
        self.scheduler = scheduler

    @classmethod
    def attach(cls, typename, scheduler_cls):
        """Create a scheduler-class with an addon attached.

        A new class named `typename` is returned, which represents the `scheduler_cls`
        with the addon attached.
        """
        signature = inspect.signature(cls.__init__)
        init_args = ', '.join(map(str, signature.parameters.values())) + ', **kwargs'

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

    def add_thread(self, thread, rcu_data):
        """Called on :meth:`Scheduler.add_thread`."""
        return

    def _get_last_chain(self, rcu_data, last_chain_queue, last_chain_idx):
        """Return the last scheduled thread of :attr:`scheduler`.

        See :meth:`Scheduler._get_last_chain`.
        """
        return self.scheduler._get_last_chain(rcu_data, last_chain_queue, last_chain_idx)  # pylint: disable=protected-access

    def repeat(self, _rcu_data, _prev_run_time, _done):
        """Called before :meth:`Scheduler._start_schedule`, :meth:`Scheduler._schedule`.

        Returns a tuple (

            * True if last scheduling decision should be repeated, False if not
            * time-slice (if first element is True, None otherwise)

        ).

        If `done` is true, this function must return `(False, None)` as first element.
        """
        return False, None

    def start_schedule(self, _prev_run_time, _rcu_data, _last_chain_queue, _last_chain_idx):  # pylint: disable=no-self-use
        """Hook for :meth:`_start_schedule`."""
        pass

    def schedule(self, _idx, time_slice, _rcu_data):  # pylint: disable=no-self-use
        """Hook for :meth:`_schedule`.

        Return a tuple (

            * True to proceed, False to schedule another chain
            * time slice

        )
        The :class:`AddonScheduler` captures the :class:`requests <schedsi.cpu.request.Request>`
        yielded from :meth:`Scheduler._schedule` to filter the resume-chain request and override
        the timer request.
        Care should be taken for the case the same chain is selected again.
        """
        return True, time_slice
