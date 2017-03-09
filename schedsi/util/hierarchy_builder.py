#!/usr/bin/env python3
"""Functionality to create a :class:`Module`-hierarchy."""

import collections
from schedsi.cpu import request as cpurequest
from schedsi import module, threads


class ModuleBuilder:
    """Build static hierarchies."""

    def __init__(self, name='0', parent=None, *, scheduler):
        """Create a :class:`ModuleBuilder`."""
        self.module = module.Module(name, parent, scheduler)
        self.vcpus = []

    def add_module(self, name=None, vcpu_add_args=None, *, scheduler, vcpus=1):
        """Attach a child :class:`Module`.

        The `name` is auto-generated, if it is `None`,
        as `self.spawn_name + "." + len(self.children)`.

        `vcpu_add_args` may be a single `dict`, in which
        case it is used for all vcpus, or it can be a list
        thereof, in which case it must have a length equal
        to `vcpus`.

        Returns the child-:class:`Module`.
        """
        if name is None:
            name = self.module.name + '.' + str(self.module.num_children())
        madder = ModuleBuilder(name, self.module, scheduler=scheduler)
        if not isinstance(vcpu_add_args, collections.abc.Sequence):
            vcpu_add_args = [vcpu_add_args] * vcpus
        assert len(vcpu_add_args) == vcpus
        self.vcpus.append((madder.module, vcpu_add_args))
        return madder

    def add_thread(self, thread, add_args=None, **kwargs):
        """Add a :class:`Thread`.

        `thread` is the class.
        All parameters are forwarded to the init-function.

        Returns `self`.
        """
        if add_args is None:
            add_args = {}
        self.module.add_thread(thread(self.module, **kwargs), **add_args)
        return self

    def add_vcpus(self):
        """Create all VCPUs for the attached children.

        VCPUs can be added incrementally while attaching modules.

        Returns `self`.
        """
        for child, vcpu_add_args in self.vcpus:
            for add_args in vcpu_add_args:
                self.add_thread(threads.VCPUThread, add_args, child=child)
        self.vcpus.clear()
        return self


class ModuleBuilderThread(threads.Thread):
    """A :class:`Thread` that creates (and attaches) a :class:`Module`.

    Can also do computation on the side.
    """

    def __init__(self, parent, name=None, *args, time, vcpus=1, scheduler,
                 units=-1, ready_time=None, **kwargs):
        """Create a :class:`ModuleBuilderThread`.

        `time` refers to the time the module should be spawned.
        `units` may be `-1` to indicate the thread should be finished when the thread spawns.
        `ready_time` may be `None` to indicate it coinciding with `time`.

        `time` must be >= `ready_time` and <= `ready_time` + `units` if `units` != `None`.
        """
        if units == -1:
            assert ready_time is None, 'If units is -1, ready_time must be None.'
            units = 0
            self.destroy_after_spawn = True
        else:
            assert ready_time is not None, 'If units is not None, ready_time must not be None.'
            self.destroy_after_spawn = False

        if ready_time is None:
            ready_time = time

        if not isinstance(parent, ModuleBuilderThread):
            self.init_args = None
            super().__init__(parent, *args, ready_time=ready_time, units=units, **kwargs)
            self.module.add_thread(self)
        else:
            # self._late_init() will be called by the parent
            # see documentation of _late_init()
            self.init_args = (args, kwargs)
            self.init_args[1].update({'ready_time': ready_time, 'units': units})

        assert time >= ready_time, 'Spawn time must not come before ready_time.'
        assert units is None or time <= ready_time + units, \
            'Spawn time must not exceed execution time.'

        self.spawn_time = time
        self.spawn_name = name
        self.scheduler = scheduler
        self.threads = []
        self.vcpus = vcpus

        self.spawn_skew = None

    def _late_init(self, parent):
        """Call `super().__init__`.

        We don't initialize `super()` if :attr:`parent` was a
        :class:`ModuleBuilderThread`, since :class:`Thread` expects
        a proper :class:`Module`.
        """
        assert self.init_args is not None, \
            '_late_init called after super() as already initialized.'
        super().__init__(parent, *self.init_args[0], **self.init_kwargs[1])
        self.init_args = None

    def disable_spawning(self):
        """Pass execution directly to `super()`.

        This can be called once all :class:`Modules` are spawned.
        """
        self._execute = super()._execute
        self.suspend = super().suspend
        self.end = super().end

    def is_spawning_disabled(self):
        """Returns True if :meth:`disable_spawning` was called, False otherwise."""
        return self._execute == super()._execute

    def is_finished(self):
        """Check if the :class:`Thread` is finished.

        See :class:`Thread.is_finished`.
        """
        return self.is_spawning_disabled() and super().is_finished()

    # this gets overwritten in disable_spawning()
    def _execute(self, current_time, run_time):  # pylint: disable=method-hidden
        """Simulate execution.

        See :meth:`Thread._execute`.

        Spawns thread when it's time.
        Reduces `run_time` if we would miss the spawn time.
        """
        if self.spawn_time <= current_time:
            self._spawn_module(current_time)
            self.disable_spawning()
            if super().is_finished():
                self._update_ready_time(current_time)
                yield cpurequest.Request.idle()
                return
        elif run_time is None or current_time + run_time > self.spawn_time:
            run_time = self.spawn_time - current_time
        return (yield from super()._execute(current_time, run_time))

    def suspend(self, current_time):  # pylint: disable=method-hidden
        """Become suspended.

        See :meth:`Thread.suspend`.

        Spawns a :class:`Thread` if it's time.
        """
        if self.spawn_time == current_time:
            self._spawn_module(current_time)
            self.disable_spawning()
        else:
            assert self.spawn_time > current_time, 'Ran over spawn time.'
        super().suspend(current_time)

    def end(self):  # pylint: disable=method-hidden
        """End execution.

        See :meth:`Thread.end`.

        This should not be called before disabling spawning.
        """
        assert self.is_spawning_disabled(), 'Execution ended before spawning was disabled.'
        assert False, 'This function should have been replaced in disable_spawning().'
        super().end()

    def _spawn_module(self, current_time):
        """Spawn the :class:`Module`."""
        assert not self.is_spawning_disabled(), 'Spawning is disabled.'
        assert self.spawn_time <= current_time

        name = self.spawn_name
        if name is None:
            name = self.module.name + '.' + str(self.module.num_children())

        child = module.Module(name, self.module, scheduler=self.scheduler)

        for (thread, args, kwargs) in self.threads:
            if isinstance(thread, ModuleBuilderThread):
                assert args is None, \
                    'A ModuleBuilderThread is already created and should not get any arguments.'
                assert kwargs is None
                thread._late_init(child)  # pylint: disable=protected-access
            else:
                if kwargs.get('ready_time', None) is None:
                    kwargs['ready_time'] = self.spawn_time
                elif kwargs['ready_time'] < 0:
                    kwargs['ready_time'] = current_time - kwargs['ready_time']
                thread = thread(child, *args, **kwargs)
            child.add_thread(thread)

        for _ in range(0, self.vcpus):
            self.module.add_thread(threads.VCPUThread(self.module, child=child))

        self.spawn_skew = current_time - self.spawn_time

    def get_statistics(self, current_time):
        """Obtain statistics.

        See :meth:`Thread.get_statistics`.
        """
        stats = super().get_statistics(current_time)
        stats.update({'spawn_skew': self.spawn_skew})

    def add_thread(self, thread, *args, **kwargs):
        """Add a :class:`Thread`.

        See :meth:`ModuleBuilder.add_thread`.

        Negative `ready_time`s will be replaced by `current_time - ready_time`
        at module spawn.
        If `ready_time` is not present, it will be replaced by `current_time`
        at module spawn.

        Returns `self`.
        """
        assert not self.is_spawning_disabled(), 'Spawning was disabled.'

        self.threads.append((thread, args, kwargs))

        return self

    def add_module(self, name=None, time=None, *args, scheduler, **kwargs):
        """Add a :class:`Module`.

        No static hierarchy can be built, so all building happens through
        a :class:`ModuleBuilderThread` that is returned.

        All parameters are forwarded to the :class:`ModuleBuilderThread` constructor.
        If `time` is `None`, `time` is set to :attr:`time`.

        Returns the :class:`ModuleBuilderThread` for the child-:class:`Module`.
        """
        assert not self.is_spawning_disabled(), 'Spawning was disabled.'

        if time is None:
            time = self.spawn_time

        thread = ModuleBuilderThread(time, self, name, *args, scheduler=scheduler, **kwargs)
        self.threads.append((thread, None, None))

        return thread
