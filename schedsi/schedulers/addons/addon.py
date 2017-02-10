"""Defines :class:`Addon` and :class:`AddonScheduler`."""

import inspect
import sys
from schedsi.cpu.request import Request as CPURequest, Type as CPURequestType
from ..scheduler import Scheduler


_PENALTY_SCHEDULER_CLASS_TEMPLATE = """\
from schedsi.schedulers.addons import addon
import {addon_cls_module}
import {scheduler_cls_module}

class {typename}(addon.AddonScheduler, {scheduler_cls_module}.{scheduler_cls}):
    ':class:`{scheduler_cls}` with :class:`~{addon_cls}` attached.'

    def __init__({init_args}):
        'Create a :class:`{typename}`.'
        super().__init__({scheduler_forward}, {addon_cls_module}.{addon_cls}(self, {addon_forward}),
                         {scheduler_kwforward})
"""


class AddonScheduler(Scheduler):
    """Scheduler with addon.

    This can be used to add scheduler addons via
    multiple inheritance.
    For instance, if we wanted the Addon `MyAddon`
    with the `BaseScheduler` scheduler, you can do this::

        class MyScheduler(AddonScheduler, BaseScheduler):
            def __init__(self, module):
                super().__init__(module, MyAddon("addon-param"), "sched-param")

    It may be convenient to use :meth:`Addon.attach` instead.
    """

    def __init__(self, module, addon, *args, **kwargs):
        """Create a :class:``."""
        super().__init__(module, *args, **kwargs)
        self.addon = addon
        addon.transmute_rcu_data(self._rcu._data)

    def _start_schedule(self, prev_run_time):
        """See :meth:`Scheduler._start_schedule`.

        This will also call the
        :attr:`addon`'s :meth:`~Addon.start_schedule` hook.
        """
        rcu_copy, *rest = yield from super()._start_schedule(prev_run_time)

        self.addon.start_schedule(prev_run_time, rcu_copy.data, *rest)

        return (rcu_copy, *rest)

    def _schedule(self, idx, time_slice, next_ready_time, rcu_copy):
        """See :meth:`Scheduler._schedule`.

        This will also call the :attr:`addon`'s :meth:`~Addon.schedule`.
        """
        schedule = super()._schedule(idx, time_slice, next_ready_time, rcu_copy)
        proceed, time_slice = self.addon.schedule(idx, time_slice, rcu_copy.data)

        answer = None
        can_idle = True
        # TODO: ideally we would avoid creating a new rcu_copy for the next schedule() call
        while True:
            try:
                request = schedule.send(answer)
            except StopIteration:
                return

            if request.rtype == CPURequestType.timer:
                if not proceed:
                    request = CPURequest.current_time()
                else:
                    delta = None
                    if next_ready_time[0] != 0:
                        if next_ready_time[0] is not None:
                            current_time = yield CPURequest.current_time()
                            delta = next_ready_time[0] - current_time
                        # if this assumption does not hold we need to decide
                        # whether we really want to override this
                        assert delta == request.thing
                    if time_slice is None or delta is None:
                        request.thing = time_slice
            elif request.rtype == CPURequestType.resume_chain:
                assert can_idle
                if not proceed:
                    answer = request.thing
                    can_idle = False
                    continue
            else:
                assert can_idle or request.rtype != CPURequestType.idle

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
        The :class:`AddonScheduler` captures the :class:`requests <schedsi.cpu.request.Request>`
        yielded from :meth:`Scheduler._schedule` to filter the resume-chain request and override
        the timer request.
        Care should be taken for the case the same chain is selected again.
        """
        return True, time_slice