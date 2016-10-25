#!/usr/bin/env python3
"""Defines the base class for schedulers."""

from schedsi import cpu, rcu

class SchedulerData: # pylint: disable=too-few-public-methods
    """Mutable data for the :class:`Scheduler`.

    Mutable data for the scheduler needs to be updated atomically.
    To enable RCU this is kept in one class.
    """
    def __init__(self):
        """Create a :class:`SchedulerRCU`."""
        self.ready_threads = []
        self.waiting_threads = []
        self.finished_threads = []
        self.last_idx = -1

class Scheduler:
    """Scheduler.

    Has a :obj:`list` of :class:`Threads <schedsi.threads.Thread>`.
    """

    def __init__(self, module, rcu_storage=None):
        """Create a :class:`Scheduler`.

        Optionally takes a `rcu_storage` for which to create the :attr:`_rcu` for.
        It should be a subclass of :class:`SchedulerData`.
        """
        if rcu_storage is None:
            rcu_storage = SchedulerData()
        self._rcu = rcu.RCU(rcu_storage)
        self.module = module

    def num_threads(self):
        return self._rcu.look(lambda d:
                              sum(len(x) for x in
                                  [d.ready_threads, d.waiting_threads, d.finished_threads]))

    def add_threads(self, new_threads):
        """Add threads to schedule."""
        def appliance(data):
            """Append new threads to the waiting and finished queue."""
            for thread in new_threads:
                if thread.remaining == 0:
                    data.finished_threads.append(thread)
                else:
                    data.waiting_threads.append(thread)
        self._rcu.apply(appliance)

    def _update_ready_threads(self, time, rcu_data):
        """Moves threads becoming ready to the ready threads list."""
        for i in range(-len(rcu_data.waiting_threads), 0):
            if rcu_data.waiting_threads[i].ready_time <= time:
                rcu_data.ready_threads.append(rcu_data.waiting_threads.pop(i))

        #do a sanity check while we're here
        assert not (0, -1) in ((t.remaining, t.ready_time) for t in rcu_data.ready_threads)
        assert all(t.remaining == 0 for t in rcu_data.finished_threads)

    def _start_schedule(self, _prev_run_time):
        """Prepare making a scheduling decision.

        Moves ready threads to the ready queue
        and finished ones to the finished queue.

        Returns a tuple (
            * RCUCopy of :attr:`_rcu`
            * list where previously scheduled thread ended up
                * (`rcu_copy_{ready,waiting,finished}_threads`)
            * index of previously scheduled thread
                * as passed to :meth:`_schedule`
                * *not* necessarily the index into the list where the thread ended up
        ).

        Yields an idle or execute :class:`Request <schedsi.cpu.Request>`.
        Consumes the current time.
        """
        current_time = yield cpu.Request.current_time()
        while True:
            rcu_copy = self._rcu.copy()
            rcu_data = rcu_copy.data

            #check if the last scheduled thread is done now
            #move to a different queue is necessary
            dest = None
            last_idx = None
            if rcu_data.last_idx != -1:
                last_idx = rcu_data.last_idx
                last_thread = rcu_data.ready_threads[last_idx]

                if last_thread.remaining == 0:
                    dest = rcu_data.finished_threads
                elif last_thread.ready_time > current_time:
                    dest = rcu_data.waiting_threads
                else:
                    assert last_thread.ready_time != -1

                if dest is None:
                    dest = rcu_data.ready_threads
                else:
                    dest.append(rcu_data.ready_threads.pop(last_idx))
                    #if not self._rcu.update(rcu_copy):
                    #    #current_time = yield cpu.Request.execute(1)
                    #    continue

                rcu_data.last_idx = -1

            self._update_ready_threads(current_time, rcu_data)

            return rcu_copy, dest, last_idx

    @staticmethod
    def _get_last_thread(rcu_data, last_thread_queue, last_thread_idx):
        """Return the last scheduled thread."""
        if last_thread_queue is rcu_data.ready_threads:
            return rcu_data.ready_threads[last_thread_idx]
        elif not last_thread_queue is None:
            return last_thread_queue[-1]
        return None

    def _schedule(self, idx, rcu_copy):
        """Update :attr:`_rcu` and schedule the thread at `idx`.

        If `idx` is -1, yield an idle request.

        Yields a :class:`Request <schedsi.cpu.Request>`.
        """
        rcu_copy.data.last_idx = idx
        if not self._rcu.update(rcu_copy):
            return

        if idx == -1:
            yield cpu.Request.idle()
            return

        yield cpu.Request.switch_thread(rcu_copy.data.ready_threads[idx])

    def schedule(self, thread, prev_run_time):
        """Schedule the next :class:`Thread <schedsi.threads.Thread>`.

        This simply calls :meth:`_start_schedule`, :meth:`_sched_loop` and
        :meth:`_schedule_` in a loop, passing appropriate arguments.

        Yields a :class:`Request <schedsi.cpu.Request>`.
        Consumes the current time.
        """
        while True:
            rcu_copy, *rest = yield from self._start_schedule(prev_run_time)
            idx = yield from self._sched_loop(rcu_copy, *rest)

            yield from self._schedule(idx, rcu_copy)

            prev_run_time = thread.last_bg_time

    @staticmethod
    def _sched_loop(rcu_copy, _last_thread_queue, _last_thread_idx):
        """Schedule the next :class:`Thread <schedsi.threads.Thread>`.

        This :class:`Scheduler` is a base class.
        This function will only deal with a single :class:`Thread <schedsi.threads.Thread>`.
        If more are present, a :exc:`RuntimeError` is raised.

        Returns the selected thread index, or -1 if none.
        Yields a :class:`Request <schedsi.cpu.Request>`.
        Consumes the current time.
        """
        num_threads = len(rcu_copy.data.ready_threads)
        idx = 0
        if num_threads == 0:
            idx = -1
        if num_threads != 1:
            raise RuntimeError('Scheduler cannot make scheduling decision.')
        return idx
        #needs to be a coroutine
        yield # pylint: disable=unreachable

class SchedulerAddonBase():
    """Scheduler addon base-class.

    Scheduler addons should use this as their baseclass.
    The :class:`SchedulerAddon` will call these functions
    like hooks.
    """

    def __init__(self, scheduler):
        """Create a :class:`SchedulerAddonBase`."""
        self.scheduler = scheduler

    def transmute_rcu_data(self, original, *addon_data): # pylint: disable=no-self-use
        """Transmute a :class:`SchedulerData`.

        This should be called like `super().transmute_rcu_data(original, MyAddonData, *addon_data)`.
        `MyAddonData` should not inherit from :class:`SchedulerData`.

        The result is that the scheduler's rcu_data will be merged with `MyAddonData`.
        """
        if len(addon_data) == 0:
            return
        class AddonData(*addon_data): # pylint: disable=too-few-public-methods
            pass
        original.__class__ = AddonData
        for data in addon_data:
            data.__init__(original)

    def _get_last_thread(self, rcu_data, last_thread_queue, last_thread_idx):
        """Return the last scheduled thread of :attr:`scheduler`.

        See :meth:`Scheduler._get_last_thread`.
        """
        return self.scheduler._get_last_thread(rcu_data, last_thread_queue, last_thread_idx) # pylint: disable=protected-access

    def start_schedule(self, _prev_run_time, _rcu_data, _last_thread_queue, _last_thread_idx): # pylint: disable=no-self-use
        """Hook for :meth:`_start_schedule`."""
        pass

    def schedule(self, _idx, _rcu_data): # pylint: disable=no-self-use
        """Hook for :meth:`_schedule`.

        Return True to proceed or False to schedule another thread.
        Care should be taken for the case the same thread is selected again.
        """
        return True

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
        :attr:`addon`'s :meth:`start_schedule <SchedulerAddonBase.schedule>` hook.
        """
        rcu_copy, *rest = yield from super()._start_schedule(prev_run_time)

        self.addon.start_schedule(prev_run_time, rcu_copy.data, *rest)

        return (rcu_copy, *rest)

    def _schedule(self, idx, rcu_copy):
        """See :meth:`Scheduler._schedule`.

        This will also call the :attr:`addon`'s :meth:`schedule <SchedulerAddonBase.schedule>`.
        """
        schedule = super()._schedule(idx, rcu_copy)
        if self.addon.schedule(idx, rcu_copy.data):
            yield from schedule
        else:
            #TODO: ideally we would avoid creating a new rcu_copy for the next schedule() call
            for request in schedule:
                if request.rtype != cpu.RequestType.switch_thread:
                    assert request.rtype != cpu.RequestType.idle
                    yield request
